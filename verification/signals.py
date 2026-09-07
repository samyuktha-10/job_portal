from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import JobApplication, Notification
from .models import VerificationRequest, VerificationStep


@receiver(post_save, sender=JobApplication)
def create_verification_request_on_shortlist(sender, instance, created, **kwargs):
    """
    NOTE: This auto-creates a BGV the instant status becomes 'shortlisted'.
    If you'd rather the company click a 'Request BGV' button manually (recommended,
    since BGV likely costs money), remove this signal and rely only on the
    `request_bgv` view instead.
    """
    if instance.status != "shortlisted":
        return

    if hasattr(instance, "verification_request"):
        return  # already exists, do nothing

    request = VerificationRequest.objects.create(
        application=instance,
        requested_by=instance.job.posted_by,
    )

    for step_type, _label in VerificationStep.StepType.choices:
        method = (
            VerificationStep.Method.API
            if step_type == VerificationStep.StepType.IDENTITY
            else VerificationStep.Method.MANUAL
        )
        VerificationStep.objects.create(request=request, step_type=step_type, method=method)

    # Tell the candidate to give consent and upload documents.
    if instance.job_seeker_profile:
        Notification.objects.create(
            user=instance.job_seeker_profile.user,
            notification_type="general",
            message=(
                f"{instance.job.company_name or instance.job.posted_by.username} has requested "
                f"background verification. Please upload your documents."
            ),
            link=f"/bgv/candidate/{request.id}/upload/",
        )
        # Best-effort email with the same link (never breaks the flow).
        from .emails import send_upload_link_email
        send_upload_link_email(request)