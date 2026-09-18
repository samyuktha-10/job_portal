from functools import wraps
from urllib.parse import quote
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import reverse


def admin_required(view_func):
    """Control Panel pages: platform super admins only.

    Anyone else is sent to the super-admin login with a ?next= back to the
    page they wanted, instead of a bare "no access" dead end."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            if request.user.is_authenticated:
                messages.info(
                    request,
                    "The Control Panel is only for the platform super admin. "
                    "Sign in with the super admin account to continue.")
            return redirect(
                reverse('super_admin_login') + '?next=' + quote(request.path))
        return view_func(request, *args, **kwargs)
    return wrapper


def employer_required(view_func):
    """Logged in AND has an employer Profile; job seekers are turned away."""
    @wraps(view_func)
    @login_required(login_url='employer_login')
    def wrapper(request, *args, **kwargs):
        profile = getattr(request.user, 'profile', None)
        if profile is None or not profile.is_employer:
            messages.error(request, "That page is for employer accounts. Log in with a job seeker account to use candidate features.")
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return wrapper
