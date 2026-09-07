import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


# ---------- Accepted evidence types per check ----------
# Address: passport or any utility bill (plus common alternatives).
# Employment: document-based verification (my chosen design) - no external vendor,
# so it is fully testable offline and can later be swapped for an API if desired.
STEP_DOC_TYPES = {
    "address": [
        ("passport", "Passport"),
        ("utility_bill", "Utility bill (electricity / water / gas)"),
        ("bank_statement", "Bank statement (last 3 months)"),
        ("rental_agreement", "Rental agreement"),
        ("aadhaar", "Aadhaar card"),
    ],
    "employment": [
        ("offer_letter", "Offer / appointment letter"),
        ("payslip", "Payslips (last 3 months)"),
        ("pf_statement", "PF / EPF statement"),
        ("relieving_letter", "Relieving / experience letter"),
        ("employment_contract", "Current employment contract"),
    ],
}
GENERIC_DOC_TYPE = ("document", "Supporting document")

ALL_DOC_TYPES = sorted(
    {GENERIC_DOC_TYPE} | {t for lst in STEP_DOC_TYPES.values() for t in lst},
    key=lambda t: t[0],
)

ALLOWED_FILE_EXTENSIONS = ("pdf", "jpg", "jpeg", "png")
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024  # 5MB, consistent with the resume rule


class VerifierProfile(models.Model):
    """Extends a Django User to be part of the internal BGV team."""
    ROLE_CHOICES = [
        ("verifier", "Verifier"),
        ("admin", "BGV Admin"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="verifier_profile")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="verifier")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.get_username()} ({self.role})"

    @property
    def active_case_count(self):
        return self.assigned_requests.exclude(
            overall_status__in=[VerificationRequest.Status.PASSED, VerificationRequest.Status.FAILED]
        ).count()


class VerificationRequest(models.Model):
    """One BGV request per shortlisted candidate, created by a company."""

    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Not Started"
        IN_PROGRESS = "in_progress", "In Progress"
        PASSED = "passed", "Passed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    application = models.OneToOneField(
        "core.JobApplication", on_delete=models.CASCADE, related_name="verification_request"
    )

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="verification_requests_made"
    )
    assigned_verifier = models.ForeignKey(
        VerifierProfile, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="assigned_requests"
    )

    overall_status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOT_STARTED)
    candidate_consent_given = models.BooleanField(default=False)
    candidate_consent_at = models.DateTimeField(null=True, blank=True)
    candidate_address = models.TextField(
        blank=True, help_text="Declared residential address, matched against the address proof document."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"BGV {self.id} - {self.application.display_full_name} @ {self.application.job.job_title}"

    @property
    def candidate_name(self):
        return self.application.display_full_name

    @property
    def candidate_email(self):
        return self.application.display_email

    @property
    def company_user(self):
        """The employer who posted the job - used for permission checks."""
        return self.application.job.posted_by

    def recalculate_overall_status(self):
        """Call this after any step changes to keep overall_status in sync."""
        steps = self.steps.all()
        statuses = set(steps.values_list("status", flat=True))

        if statuses == {VerificationStep.Status.VERIFIED}:
            self.overall_status = self.Status.PASSED
            self.completed_at = timezone.now()
        elif VerificationStep.Status.REJECTED in statuses:
            self.overall_status = self.Status.FAILED
            self.completed_at = timezone.now()
        elif statuses & {VerificationStep.Status.IN_REVIEW, VerificationStep.Status.VERIFIED}:
            self.overall_status = self.Status.IN_PROGRESS
        else:
            self.overall_status = self.Status.NOT_STARTED
        self.save(update_fields=["overall_status", "completed_at", "updated_at"])


class VerificationStep(models.Model):
    """One of the 5 fixed checks under a VerificationRequest."""

    class StepType(models.TextChoices):
        IDENTITY = "identity", "Identity Verification"
        EDUCATION = "education", "Education Verification"
        EMPLOYMENT = "employment", "Employment History Verification"
        ADDRESS = "address", "Address Verification"
        CRIMINAL = "criminal", "Criminal Record Check"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_REVIEW = "in_review", "In Review"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"

    class Method(models.TextChoices):
        MANUAL = "manual", "Manual Review"
        API = "api", "Automated API"

    request = models.ForeignKey(VerificationRequest, on_delete=models.CASCADE, related_name="steps")
    step_type = models.CharField(max_length=20, choices=StepType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    method = models.CharField(max_length=10, choices=Method.choices, default=Method.MANUAL)

    remarks = models.TextField(blank=True)
    external_reference_id = models.CharField(max_length=100, blank=True)
    raw_api_response = models.JSONField(null=True, blank=True)

    verified_by = models.ForeignKey(
        VerifierProfile, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="steps_verified"
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("request", "step_type")
        ordering = ["step_type"]

    def __str__(self):
        return f"{self.get_step_type_display()} - {self.status}"

    @property
    def allowed_doc_types(self):
        """Accepted evidence types for this check; generic fallback otherwise."""
        return STEP_DOC_TYPES.get(self.step_type, [GENERIC_DOC_TYPE])

    def mark(self, status, actor: VerifierProfile, remarks=""):
        """Segregation-of-duties enforced: actor cannot verify their own request."""
        if actor and self.request.requested_by_id == actor.user_id:
            raise PermissionError("A requester cannot verify their own BGV request.")
        old_status = self.status
        self.status = status
        self.remarks = remarks
        self.verified_by = actor
        self.verified_at = timezone.now()
        self.save()
        self.request.recalculate_overall_status()
        VerificationAuditLog.objects.create(
            request=self.request,
            actor=actor.user if actor else None,
            action=f"step_{self.step_type}_marked_{status}",
            old_status=old_status,
            new_status=status,
        )


def document_upload_path(instance, filename):
    return f"bgv_documents/{instance.step.request_id}/{instance.step.step_type}/{filename}"


class VerificationDocument(models.Model):
    """Uploaded evidence file per step. Store in a private bucket, never public media."""

    step = models.ForeignKey(VerificationStep, on_delete=models.CASCADE, related_name="documents")
    file = models.FileField(upload_to=document_upload_path)
    doc_type = models.CharField(max_length=30, choices=ALL_DOC_TYPES, default="document", blank=True)
    file_hash = models.CharField(max_length=64, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        import hashlib
        if self.file and hasattr(self.file, "read"):
            try:
                hasher = hashlib.sha256()
                for chunk in self.file.chunks():
                    hasher.update(chunk)
                self.file_hash = hasher.hexdigest()
            except (ValueError, OSError):
                pass
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Doc for {self.step}"


class VerificationAuditLog(models.Model):
    """Immutable trail. Never update or delete rows here."""

    request = models.ForeignKey(VerificationRequest, on_delete=models.CASCADE, related_name="audit_logs")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=100)
    old_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("Audit log entries are immutable and cannot be edited.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Audit log entries cannot be deleted.")