from core.models import SupportContact


def support_contact(request):
    """Make the admin-assigned support contact available to every template."""
    return {"support_contact": SupportContact.current()}
