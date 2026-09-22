import mimetypes
import os

from django.db.models import Case, IntegerField, When
from django.http import FileResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.contrib.auth.models import User

from .decorators import admin_required
from .models import Job, Inquiry, Profile
from .views import create_notification


@admin_required
def admin_jobs_list(request):
    jobs = Job.objects.select_related('posted_by').order_by('-posted_at')

    status = request.GET.get('status')
    if status in ('pending', 'approved', 'rejected'):
        jobs = jobs.filter(approval_status=status)

    paginator = Paginator(jobs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'core/admin_jobs_list.html', {
        'page_obj': page_obj,
        'status': status,
    })


@admin_required
@require_POST
def admin_job_set_status(request, job_id, status):
    if status not in ('pending', 'approved', 'rejected'):
        messages.error(request, 'Invalid status.')
        return redirect('admin_jobs_list')
    job = get_object_or_404(Job, id=job_id)
    job.approval_status = status
    job.save(update_fields=['approval_status'])
    messages.success(request, f"'{job.job_title}' marked as {job.get_approval_status_display()}.")
    return redirect('admin_jobs_list')


@admin_required
@require_POST
def admin_job_delete(request, job_id):
    job = get_object_or_404(Job, id=job_id)
    title = job.job_title
    job.delete()
    messages.success(request, f"Deleted job posting '{title}'.")
    return redirect('admin_jobs_list')


@admin_required
def admin_inquiries_list(request):
    inquiries = Inquiry.objects.order_by('-created_at')

    status = request.GET.get('status')
    if status in ('Unread', 'Read', 'Replied', 'Closed'):
        inquiries = inquiries.filter(status=status)

    paginator = Paginator(inquiries, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'core/admin_inquiries_list.html', {
        'page_obj': page_obj,
        'status': status,
    })


@admin_required
@require_POST
def admin_inquiry_update_status(request, inquiry_id):
    inquiry = get_object_or_404(Inquiry, id=inquiry_id)
    new_status = request.POST.get('status')
    if new_status in ('Unread', 'Read', 'Replied', 'Closed'):
        inquiry.status = new_status
        inquiry.save(update_fields=['status'])
        messages.success(request, f"Inquiry status updated to {inquiry.get_status_display()}.")
    else:
        messages.error(request, 'Invalid status.')
    return redirect('admin_inquiries_list')


@admin_required
@require_POST
def admin_user_toggle_active(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if user.is_superuser:
        messages.error(request, 'You cannot deactivate a superuser account.')
    else:
        user.is_active = not user.is_active
        user.save(update_fields=['is_active'])
        messages.success(request, f"{user.username} is now {'active' if user.is_active else 'banned'}.")
    return redirect(request.POST.get('next') or 'admin_job_seekers_list')


# ---------------------------------------------------------------------------
# Company trust verification (KYC) review queue
# ---------------------------------------------------------------------------
_TRUST_ORDER = Case(
    When(trust_status='pending', then=0),
    When(trust_status='rejected', then=1),
    When(trust_status='unverified', then=2),
    default=3,
    output_field=IntegerField(),
)


@admin_required
def admin_company_verification(request):
    """Review queue: companies that submitted a registration ID + corporate ID card."""
    profiles = (
        Profile.objects.filter(is_employer=True)
        .select_related('user', 'trust_reviewed_by')
        .order_by(_TRUST_ORDER, '-trust_submitted_at', 'company_name')
    )

    status = request.GET.get('status')
    if status in ('pending', 'rejected', 'verified', 'unverified'):
        profiles = profiles.filter(trust_status=status)

    return render(request, 'core/admin_company_verification.html', {
        'profiles': profiles,
        'status': status,
        'pending_count': Profile.objects.filter(is_employer=True, trust_status='pending').count(),
    })


@admin_required
@require_POST
def admin_company_trust_set(request, profile_id, action):
    if action not in ('verify', 'reject'):
        raise Http404('Unknown trust action.')

    profile = get_object_or_404(Profile, pk=profile_id, is_employer=True)

    if action == 'verify':
        profile.trust_status = 'verified'
        profile.trust_rejection_reason = ''
        create_notification(
            user=profile.user,
            message='Your company has been verified as Trusted & Valid. You can now post jobs.',
            notification_type='general',
            link='/company-profile/',
        )
        messages.success(request, f"{profile.company_name or profile.user.username} marked Trusted & Valid.")
    else:
        reason = request.POST.get('reason', '').strip()
        if not reason:
            messages.error(request, 'A rejection reason is required so the employer knows what to fix.')
            return redirect('admin_company_verification')
        profile.trust_status = 'rejected'
        profile.trust_rejection_reason = reason[:300]
        create_notification(
            user=profile.user,
            message=f'Company verification rejected: {reason[:200]}',
            notification_type='general',
            link='/company-profile/',
        )
        messages.success(request, f"{profile.company_name or profile.user.username} rejected.")

    profile.trust_reviewed_at = timezone.now()
    profile.trust_reviewed_by = request.user
    profile.save()
    return redirect('admin_company_verification')


@admin_required
def company_id_document_download(request, profile_id):
    """Stream a company's corporate ID document. Super admins only.

    The file lives in PROTECTED_MEDIA_ROOT (never served as public media), so
    this view is the single controlled access point.
    """
    profile = get_object_or_404(Profile, pk=profile_id, is_employer=True)
    if not profile.company_id_document:
        raise Http404('No corporate ID document on file for this company.')

    name = os.path.basename(profile.company_id_document.name)
    content_type = mimetypes.guess_type(name)[0] or 'application/octet-stream'
    return FileResponse(
        profile.company_id_document.open('rb'),
        as_attachment=True,
        filename=name,
        content_type=content_type,
    )
