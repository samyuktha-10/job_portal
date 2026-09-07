from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST
from django.contrib.auth.models import User

from .decorators import admin_required
from .models import Job, Inquiry


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
