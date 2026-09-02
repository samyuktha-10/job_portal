from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import JobApplication
from .models import VerificationRequest, VerificationStep


@receiver(post_save, sender=JobApplication)
def create_verification_request_on_shortlist(sender, instance, created, **kwargs):
    """
    NOTE: This auto-creates a BGV the instant status becomes 'shortlisted'.
    If you'd rather the company click a 'Request BGV' button manually (recommended,
    since BGV likely costs money), remove this signal and rely only on the
    `request_bgv` view instead. Keeping this here as an optional auto-trigger path.
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

    # TODO: send Notification (you already have a Notification model in core!)
    # to the candidate's user account asking them to give consent + upload docs.
