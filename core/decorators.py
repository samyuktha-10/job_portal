from functools import wraps
from django.http import HttpResponseForbidden
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


def admin_required(view_func):
    @wraps(view_func)
    @login_required(login_url='super_admin_login')
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            return HttpResponseForbidden("You don't have access to this page.")
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
