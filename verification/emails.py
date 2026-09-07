"""Best-effort email delivery of the candidate consent + upload link."""
from django.conf import settings
from django.core.mail import send_mail


def upload_link_url(bgv):
    return f"{settings.SITE_URL.rstrip('/')}/bgv/candidate/{bgv.id}/upload/"


def send_upload_link_email(bgv):
    """
    Email the candidate the consent + document-upload link for this BGV.
    Returns True if the mail was handed to the backend, False otherwise.
    Never raises: a mail failure must not break the BGV flow.
    """
    email = bgv.candidate_email
    if not email:
        return False

    company = bgv.application.job.company_name or bgv.application.job.posted_by.username
    url = upload_link_url(bgv)
    sent = send_mail(
        subject="Action needed: background verification for your application",
        message=(
            f"Hi {bgv.candidate_name},\n\n"
            f"{company} has requested a background verification for your application "
            f"for {bgv.application.job.job_title}.\n\n"
            f"Open this link, give your consent and upload your documents:\n{url}\n\n"
            f"The link works while you are logged into your Deploynix account.\n\n"
            "Team Deploynix"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=True,
    )
    return bool(sent)
