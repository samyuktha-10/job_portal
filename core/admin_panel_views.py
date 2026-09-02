from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST

from .decorators import admin_required
from .models import Job, JobApplication, Inquiry, Profile, JobSeekerProfile


@admin_required
def admin_dashboard(request):
    context = {
        'total_job_seekers': JobSeekerProfile.objects.count(),
        'total_employers': Profile.objects.filter(is_employer=True).count(),
        'total_jobs': Job.objects.count(),
        'pending_jobs': Job.objects.filter(is_approved=False).count(),
        'total_applications': JobApplication.objects.count(),
        'open_inquiries': Inquiry.objects.exclude(status__in=['Closed', 'Replied']).count(),
    }
    return render(request, 'core/admin_panel/dashboard.html', context)


@admin_required
def admin_jobs_list(request):
    jobs = Job.objects.select_related('posted_by').order_by('-posted_at')

    status = request.GET.get('status')
    if status == 'approved':
        jobs = jobs.filter(is_approved=True)
    elif status == 'pending':
        jobs = jobs.filter(is_approved=False)

    paginator = Paginator(jobs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'core/admin_jobs_list.html', {'page_obj': page_obj, 'status': status})

@admin_required
@require_POST
def admin_job_toggle_approval(request, job_id):
    job = get_object_or_404(Job, id=job_id)
    job.is_approved = not job.is_approved
    job.save(update_fields=['is_approved'])
    messages.success(request, f"'{job.job_title}' is now {'approved' if job.is_approved else 'pending'}.")
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
def admin_users_list(request):
    role = request.GET.get('role', 'seekers')

    if role == 'employers':
        users = Profile.objects.filter(is_employer=True).select_related('user').order_by('-created_at')
    else:
        users = JobSeekerProfile.objects.select_related('user').order_by('-created_at')

    paginator = Paginator(users, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'core/admin_panel/users_list.html', {'page_obj': page_obj, 'role': role})


@admin_required
@require_POST
def admin_user_toggle_active(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if user.is_superuser:
        messages.error(request, "Can't ban a superuser account.")
        return redirect('admin_users_list')

    user.is_active = not user.is_active
    user.save(update_fields=['is_active'])
    messages.success(request, f"{user.username} is now {'active' if user.is_active else 'banned'}.")
    return redirect('admin_users_list')


@admin_required
def admin_inquiries_list(request):
    inquiries = Inquiry.objects.order_by('-created_at')
    paginator = Paginator(inquiries, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'core/admin_panel/admin_inquiries_list.html', {'page_obj': page_obj})


@admin_required
@require_POST
def admin_inquiry_update_status(request, inquiry_id):
    inquiry = get_object_or_404(Inquiry, id=inquiry_id)
    new_status = request.POST.get('status')
    if new_status in dict(Inquiry.STATUS_CHOICES):
        inquiry.status = new_status
        inquiry.save(update_fields=['status'])
        messages.success(request, "Inquiry status updated.")
    return redirect('admin_inquiries_list')