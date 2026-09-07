from functools import wraps
from django.http import HttpResponseForbidden
from django.contrib.auth.decorators import login_required


def admin_required(view_func):
    @wraps(view_func)
    @login_required(login_url='super_admin_login')
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            return HttpResponseForbidden("You don't have access to this page.")
        return view_func(request, *args, **kwargs)
    return wrapper
