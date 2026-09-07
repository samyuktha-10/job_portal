import razorpay
import json
import re
import random
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash, get_user_model
from django.contrib import messages
from django.contrib.messages import get_messages
from django.contrib.auth.decorators import login_required, user_passes_test
from .decorators import employer_required
from django.db.models import Q, F, Sum, Count
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from django.core.paginator import Paginator
from django.core.mail import send_mail
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from pypdf import PdfReader
from django.db.models.functions import TruncMonth
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.hashers import make_password
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.forms import PasswordChangeForm
from .models import (
    Job, JobApplication, Inquiry, Interview,
    JobSeekerProfile, SubscriptionPlan, EmployerSubscription, ResumeUnlock, Profile,
    Notification, SavedJob, JobSeekerSignupOTP, SupportContact,
)
from .forms import (
    SignUpForm, EmployerLoginForm, JobSeekerLoginForm, JobPostForm,
    JobApplicationForm, EmployerAddCandidateForm, InterviewForm, JobSeekerProfileForm,
    OTPVerifyForm,
)
razorpay_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

SERVICES_DATA = {
    'premium-membership': {
        'title': 'Premium Membership',
        'description': 'Increase Your Chances of Getting Shortlisted',
        'image': 'member.jpg',
        'details': 'With Premium Membership, your profile gets priority visibility to recruiters, early access to job postings, and personalized career guidance to help you stand out from other applicants.',
    },
    'placement-paper': {
        'title': 'Placement Paper',
        'description': 'Practice & improve your skills',
        'image': 'member1.png',
        'details': 'Access a curated library of previous placement papers and mock tests from top companies to sharpen your technical and aptitude skills before your next interview.',
    },
    'interview-grooming': {
        'title': 'Interview Grooming',
        'description': 'Attend interviews confidently',
        'image': 'member2.png',
        'details': 'Get one-on-one mock interview sessions, feedback from industry experts, and tips on body language, communication, and technical presentation to walk into your interview with confidence.',
    },
}

#Utility function to generate a unique username for employers based on their company name ------------------------------
def _generate_employer_username(company_name):
    """Turns a company name into a unique, username-safe slug."""
    base = re.sub(r'[^a-zA-Z0-9]+', '-', company_name).strip('-').lower()
    if not base:
        base = 'employer'
    username = base
    counter = 1
    while User.objects.filter(username=username).exists():
        counter += 1
        username = f"{base}-{counter}"
    return username
def create_notification(user, message, notification_type='general', link=''):
    Notification.objects.create(
        user=user,
        message=message,
        notification_type=notification_type,
        link=link,
    )

def service_detail(request, slug):
    service = SERVICES_DATA.get(slug)
    return render(request, 'core/service_detail.html', {'service': service, 'slug': slug})

def home(request):
    query = request.GET.get('q', '').strip()
    location = request.GET.get('location', '').strip()

    searched = bool(query or location)
    if searched:
        jobs = Job.objects.filter(approval_status='approved').order_by('-posted_at')
        if query:
            jobs = jobs.filter(Q(job_title__icontains=query) | Q(skills_required__icontains=query))
        if location:
            jobs = jobs.filter(location__icontains=location)
        jobs = jobs[:12]
    else:
        jobs = Job.objects.none()

    applied_job_ids = set()
    if request.user.is_authenticated and hasattr(request.user, 'jobseeker_profile'):
        applied_job_ids = set(
            JobApplication.objects.filter(job_seeker_profile=request.user.jobseeker_profile)
            .values_list('job_id', flat=True)
        )
    return render(request, 'core/home.html', {
        'jobs': jobs,
        'query': query,
        'location': location,
        'searched': searched,
        'applied_job_ids': applied_job_ids,
    })

#Job Vacancies view ---------------------------------------------------------------------------------------------------------
def job_vacancies(request):
    query = request.GET.get('q', '').strip()
    location = request.GET.get('location', '').strip()

    jobs = Job.objects.filter(approval_status='approved').order_by('-posted_at')

    if query:
        jobs = jobs.filter(Q(job_title__icontains=query) | Q(skills_required__icontains=query))
    if location:
        jobs = jobs.filter(location__icontains=location)

    applied_job_ids = set()
    if request.user.is_authenticated and hasattr(request.user, 'jobseeker_profile'):
        applied_job_ids = set(
            JobApplication.objects.filter(job_seeker_profile=request.user.jobseeker_profile)
            .values_list('job_id', flat=True)
        )

    return render(request, 'core/job_vacancies.html', {
        'jobs': jobs,
        'query': query,
        'location': location,
        'searched': bool(query or location),
        'applied_job_ids': applied_job_ids,
    })

#Signup view ---------------------------------------------------------------------------------------------------------
def signup(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            user = User.objects.create_user(username=username, email=email, password=password)
            user.save()

            free_plan = SubscriptionPlan.objects.filter(name='Free').first()
            if free_plan:
                EmployerSubscription.objects.create(
                    user=user,
                    plan=free_plan,
                    expires_at=timezone.now() + timedelta(days=free_plan.duration_days),
                )

            return redirect('home')
    else:
        form = SignUpForm()
    return render(request, 'core/signup.html', {'form': form})
from django.views.decorators.cache import never_cache

#Employer Login view ---------------------------------------------------------------------------------------------------------
@never_cache
def employer_login(request):
    if request.method == 'POST':
        form = EmployerLoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email'].strip()
            password = form.cleaned_data['password']
            company_name = form.cleaned_data['company_name']

            user_obj = User.objects.filter(email__iexact=email).first()

            if user_obj is None:
                # No account yet — create one automatically
                username = _generate_employer_username(company_name)
                user_obj = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                )
                Profile.objects.create(
                    user=user_obj,
                    is_employer=True,
                    company_name=company_name,
                )

                free_plan = SubscriptionPlan.objects.filter(name='Free').first()
                if free_plan:
                    EmployerSubscription.objects.create(
                        user=user_obj,
                        plan=free_plan,
                        expires_at=timezone.now() + timedelta(days=free_plan.duration_days),
                    )

                user = authenticate(request, username=username, password=password)
                login(request, user)

                if user_obj.email:
                    send_verification_email(request, user_obj)

                return redirect('employer_dashboard')

            # Existing account — verify password
            user = authenticate(request, username=user_obj.username, password=password)
            if user is not None:
                # A job seeker account must never be turned into an employer account.
                if hasattr(user_obj, 'jobseeker_profile'):
                    messages.error(
                        request,
                        "This email is registered as a job seeker account. "
                        "Employer accounts need a different email.",
                    )
                    return render(request, 'core/employer_login.html', {'form': form})

                login(request, user)

                profile, created = Profile.objects.get_or_create(
                    user=user,
                    defaults={'is_employer': True, 'company_name': company_name}
                )
                if not created:
                    changed = False
                    if not profile.is_employer:
                        profile.is_employer = True
                        changed = True
                    if company_name:
                        profile.company_name = company_name
                        changed = True
                    if changed:
                        profile.save()

                return redirect('employer_dashboard')
            else:
                messages.error(request, 'Incorrect password. If this is a new company, use a different email.')
    else:
        storage = get_messages(request)
        for _ in storage:
            pass
        form = EmployerLoginForm()

    return render(request, 'core/employer_login.html', {'form': form})

#Employer Dashboard view ---------------------------------------------------------------------------------------------------------
@employer_required
def employer_dashboard(request):
    jobs = Job.objects.filter(posted_by=request.user)
    applications = JobApplication.objects.filter(job__posted_by=request.user).order_by('-applied_at')
    interviews = Interview.objects.filter(application__job__posted_by=request.user).order_by('scheduled_at')
    upcoming_interviews = interviews.filter(status='scheduled')[:5]

    # Paginate recent candidates (5 per page)
    paginator = Paginator(applications, 5)
    page_number = request.GET.get('page', 1)
    recent_candidates = paginator.get_page(page_number)

    context = {
        'jobs_posted_count': jobs.count(),
        'applicants_total': applications.count(),
        'applicants_pending': applications.filter(status='applied').count(),
        'interview_list': interviews.count(),
        'inquiries_total': Inquiry.objects.count(),
        'inquiries_unread': Inquiry.objects.exclude(status__in=['Read', 'Replied', 'Closed']).count(),
        'upcoming_interviews': upcoming_interviews,
        'recent_candidates': recent_candidates,
    }
    return render(request, 'core/employer_dashboard.html', context)


#Company Profile view ---------------------------------------------------------------------------------------------------------
@employer_required
def company_profile(request):
    profile, created = Profile.objects.get_or_create(
        user=request.user,
        defaults={'is_employer': True}
    )

    if request.method == 'POST':
        profile.company_name = request.POST.get('company_name', '')
        profile.phone = request.POST.get('phone', '')
        profile.about = request.POST.get('about', '')
        profile.industry = request.POST.get('industry', '')
        profile.website = request.POST.get('website', '')
        profile.company_size = request.POST.get('company_size', '')
        founded_year = request.POST.get('founded_year', '')
        profile.founded_year = founded_year if founded_year else None
        profile.address = request.POST.get('address', '')
        profile.city = request.POST.get('city', '')
        profile.state = request.POST.get('state', '')

        if request.POST.get('remove_logo') == 'true':
            profile.logo.delete(save=False)
            profile.logo = None
        elif request.FILES.get('logo'):
            profile.logo = request.FILES['logo']

        profile.save()
        messages.success(request, 'Company profile updated.')
        return redirect('company_profile')

    return render(request, 'core/company_profile.html', {'profile': profile})


#Job Seeker Options view ---------------------------------------------------------------------------------------------------------
def job_seeker_options(request):
    return render(request, 'core/job_seeker_options.html')

@login_required(login_url='job_seeker_login')
def my_applications(request):
    applications = JobApplication.objects.filter(
        job_seeker_profile__user=request.user
    ).order_by('-applied_at')
    return render(request, 'core/my_applications.html', {'applications': applications})

#OTP Generation and Verification for Job Seeker Signup ---------------------------------------------------------------------------------------------------------
def _generate_otp():
    return f"{random.randint(0, 999999):06d}"

#Send OTP email for job seeker signup ---------------------------------------------------------------------------------------------------------
def _send_signup_otp_email(pending):
    """Emails the OTP for a pending job-seeker signup. Returns True on success."""
    try:
        send_mail(
            subject='Your Deploynix verification code',
            message=(
                f"Hi {pending.username},\n\n"
                f"Your one-time verification code is: {pending.otp_code}\n\n"
                "Enter this code to finish creating your Deploynix account. "
                "This code expires in 10 minutes.\n\n"
                "If you didn't try to create a Deploynix account, you can ignore this email.\n\n"
                "Best,\nTeam Deploynix"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[pending.email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        print("OTP EMAIL ERROR:", e)
        return False

#Job Seeker Login view ---------------------------------------------------------------------------------------------------------
def job_seeker_login(request):
    next_url = request.POST.get('next') or request.GET.get('next') or 'home'
    if request.method == 'POST':
        form = JobSeekerLoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username'].strip()
            email = form.cleaned_data.get('email', '').strip()
            password = form.cleaned_data['password']

            user_obj = User.objects.filter(username__iexact=username).first()

            if user_obj is None:
                if not email:
                    form.add_error('email', 'Email is required the first time you log in, so we can verify it.')
                elif User.objects.filter(email__iexact=email).exists():
                    form.add_error('email', 'An account with this email already exists. Try logging in instead.')
                else:
                    otp_code = _generate_otp()
                    pending, _created = JobSeekerSignupOTP.objects.update_or_create(
                        username=username,
                        defaults={
                            'email': email,
                            'password_hash': make_password(password),
                            'otp_code': otp_code,
                            'attempts': 0,
                            'expires_at': timezone.now() + timedelta(minutes=10),
                        }
                    )
                    if _send_signup_otp_email(pending):
                        request.session['pending_signup_username'] = username
                        request.session['pending_signup_next'] = 'create_profile'
                        messages.info(request, f'We sent a 6-digit verification code to {email}. Enter it below to finish creating your account.')
                        return redirect('verify_signup_otp')
                    else:
                        pending.delete()
                        messages.error(request, 'Could not send the verification email right now. Please try again in a moment.')
            else:
                user = authenticate(request, username=user_obj.username, password=password)
                if user is not None:
                    login(request, user)
                    return redirect(next_url)
                else:
                    messages.error(request, 'Incorrect password. If this is a new account, use a different username.')
    else:
        storage = get_messages(request)
        for _ in storage:
            pass
        form = JobSeekerLoginForm()

    return render(request, 'core/job_seeker_login.html', {'form': form, 'next': next_url})

#OTP Verification view for Job Seeker Signup ---------------------------------------------------------------------------------------------------------
def verify_signup_otp(request):
    username = request.session.get('pending_signup_username')
    pending = JobSeekerSignupOTP.objects.filter(username=username).first() if username else None

    if pending is None:
        messages.error(request, 'No pending signup found. Please log in again to get a new code.')
        return redirect('job_seeker_login')

    next_url = request.session.get('pending_signup_next') or 'create_profile'

    if request.method == 'POST':
        form = OTPVerifyForm(request.POST)
        if form.is_valid():
            entered_code = form.cleaned_data['otp_code']

            if pending.is_expired():
                pending.delete()
                request.session.pop('pending_signup_username', None)
                request.session.pop('pending_signup_next', None)
                messages.error(request, 'That code expired. Please log in again to get a new one.')
                return redirect('job_seeker_login')

            if pending.attempts >= 5:
                pending.delete()
                request.session.pop('pending_signup_username', None)
                request.session.pop('pending_signup_next', None)
                messages.error(request, 'Too many incorrect attempts. Please log in again to get a new code.')
                return redirect('job_seeker_login')

            if entered_code == pending.otp_code:
                if User.objects.filter(username__iexact=pending.username).exists():
                    pending.delete()
                    request.session.pop('pending_signup_username', None)
                    request.session.pop('pending_signup_next', None)
                    messages.info(request, 'That account already exists. Please log in.')
                    return redirect('job_seeker_login')

                user_obj = User(username=pending.username, email=pending.email)
                user_obj.password = pending.password_hash
                user_obj.save()

                JobSeekerProfile.objects.create(
                    user=user_obj,
                    full_name=pending.username,
                    phone='',
                    is_email_verified=True,
                )

                user_obj.backend = 'django.contrib.auth.backends.ModelBackend'
                login(request, user_obj)

                pending.delete()
                request.session.pop('pending_signup_username', None)
                request.session.pop('pending_signup_next', None)

                try:
                    send_mail(
                        subject='Welcome to Deploynix!',
                        message=(
                            f"Hi {user_obj.username},\n\n"
                            "Your email is verified and your Deploynix account is ready.\n"
                            "Complete your profile to start applying for jobs and internships.\n\n"
                            "Best,\nTeam Deploynix"
                        ),
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[user_obj.email],
                        fail_silently=True,
                    )
                except Exception as e:
                    print("EMAIL ERROR:", e)

                messages.success(request, 'Email verified! Your account has been created.')
                return redirect(next_url)
            else:
                pending.attempts += 1
                pending.save(update_fields=['attempts'])
                remaining = max(0, 5 - pending.attempts)
                messages.error(request, f'Incorrect code. {remaining} attempt(s) left before you\'ll need a new code.')
    else:
        form = OTPVerifyForm()

    return render(request, 'core/verify_signup_otp.html', {
        'form': form,
        'email': pending.email,
        'username': pending.username,
    })

#Resend OTP view for Job Seeker Signup ---------------------------------------------------------------------------------------------------------
def resend_signup_otp(request):
    username = request.session.get('pending_signup_username')
    pending = JobSeekerSignupOTP.objects.filter(username=username).first() if username else None

    if pending is None:
        messages.error(request, 'No pending signup found. Please log in again to get a new code.')
        return redirect('job_seeker_login')

    pending.otp_code = _generate_otp()
    pending.attempts = 0
    pending.expires_at = timezone.now() + timedelta(minutes=10)
    pending.save(update_fields=['otp_code', 'attempts', 'expires_at'])

    if _send_signup_otp_email(pending):
        messages.info(request, f'A new verification code has been sent to {pending.email}.')
    else:
        messages.error(request, 'Could not send the verification email right now. Please try again in a moment.')

    return redirect('verify_signup_otp')


JOB_TYPE_CATEGORIES = [
    ('full-time', 'Full-Time', '💼'),
    ('internship', 'Internship', '🎓'),
    ('walk-in', 'Walk-in', '🚶'),
]

#Job Posting Selection view ---------------------------------------------------------------------------------------------------------
@employer_required
def post_job_select(request):
    if settings.SUBSCRIPTION_ENABLED:
        subscription = getattr(request.user, 'subscription', None)
        if not subscription or not subscription.can_post_job():
            messages.warning(request, "You've reached your job posting limit for this plan. Upgrade to post more jobs.")
            return redirect('subscription_plans')

    categories = []
    for job_type, label, icon in JOB_TYPE_CATEGORIES:
        jobs_qs = Job.objects.filter(posted_by=request.user, job_type=job_type)
        jobs_count = jobs_qs.count()
        views_total = jobs_qs.aggregate(total=Sum('views_count'))['total'] or 0
        applications_total = JobApplication.objects.filter(
            job__posted_by=request.user, job__job_type=job_type
        ).count()

        categories.append({
            'job_type': job_type,
            'label': label,
            'icon': icon,
            'jobs_count': jobs_count,
            'views_total': views_total,
            'applications_total': applications_total,
        })

    return render(request, 'core/post_job_select.html', {'categories': categories})

#Job Posting view ---------------------------------------------------------------------------------------------------------
@employer_required
def post_job(request, job_type):
    valid_types = dict((jt, label) for jt, label, icon in JOB_TYPE_CATEGORIES)
    if job_type not in valid_types:
        messages.error(request, 'Invalid job category.')
        return redirect('post_job_select')

    if settings.SUBSCRIPTION_ENABLED:
        subscription = getattr(request.user, 'subscription', None)
        if not subscription or not subscription.can_post_job():
            storage = get_messages(request)
            for _ in storage:
                pass
            messages.warning(request, "You've reached your job posting limit for this plan. Upgrade to post more jobs.")
            return redirect('subscription_plans')

    if request.method == 'POST':
        form = JobPostForm(request.POST)
        if form.is_valid():
            job = form.save(commit=False)
            job.posted_by = request.user
            job.job_type = job_type
            job.save()
            return redirect('job_detail', job_id=job.id)
    else:
        form = JobPostForm(initial={'job_type': job_type})

    return render(request, 'core/post_job.html', {
        'form': form,
        'job_type': job_type,
        'job_type_label': valid_types[job_type],
    })

#Job Detail view ---------------------------------------------------------------------------------------------------------
def job_detail(request, job_id):
    job = Job.objects.get(id=job_id)
    is_owner = request.user.is_authenticated and request.user == job.posted_by
    base_template = 'core/dashboard_base.html' if is_owner else 'core/base.html'

    if not is_owner:
        Job.objects.filter(id=job.id).update(views_count=F('views_count') + 1)
        job.refresh_from_db(fields=['views_count'])

    is_saved = False
    if request.user.is_authenticated and hasattr(request.user, 'jobseeker_profile'):
        is_saved = SavedJob.objects.filter(user=request.user, job=job).exists()

    return render(request, 'core/job_detail.html', {
        'job': job,
        'is_owner': is_owner,
        'base_template': base_template,
        'is_saved': is_saved,
    })

#Employer Dashboard view ---------------------------------------------------------------------------------------------------------
@employer_required
def employer_reports(request):
    jobs = Job.objects.filter(posted_by=request.user)
    job_ids = jobs.values_list('id', flat=True)
    applications = JobApplication.objects.filter(job_id__in=job_ids)

    jobs_posted = jobs.count()
    total_applications = applications.count()
    total_job_views = jobs.aggregate(total=Sum('views_count'))['total'] or 0
    resumes_unlocked = ResumeUnlock.objects.filter(employer=request.user).count()

    funnel_counts = dict(applications.values_list('status').annotate(count=Count('id')))
    candidate_funnel = [
        {'label': label, 'count': funnel_counts.get(value, 0)}
        for value, label in JobApplication.STATUS_CHOICES
    ]

    six_months_ago = timezone.now() - timedelta(days=180)
    jobs_over_time = (
        jobs.filter(posted_at__gte=six_months_ago)
        .annotate(month=TruncMonth('posted_at'))
        .values('month')
        .annotate(count=Count('id'))
        .order_by('month')
    )

    job_performance = jobs.annotate(
        application_count=Count('applications')
    ).order_by('-posted_at')

    context = {
        'jobs_posted': jobs_posted,
        'total_applications': total_applications,
        'total_job_views': total_job_views,
        'resumes_unlocked': resumes_unlocked,
        'candidate_funnel': candidate_funnel,
        'jobs_over_time': jobs_over_time,
        'job_performance': job_performance,
    }
    return render(request, 'core/employer_reports.html', context)

#Employer Settings view ---------------------------------------------------------------------------------------------------------
@employer_required
def employer_settings(request):
    profile, created = Profile.objects.get_or_create(
        user=request.user, defaults={'is_employer': True}
    )
    subscription = getattr(request.user, 'subscription', None)

    if request.method == 'POST':
        if 'save_account' in request.POST:
            new_email = request.POST.get('email', '').strip()
            if new_email:
                request.user.email = new_email
                request.user.save(update_fields=['email'])
                messages.success(request, "Account details updated.")
            return redirect('employer_settings')

        elif 'change_password' in request.POST:
            form = PasswordChangeForm(request.user, request.POST)
            if form.is_valid():
                user = form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Password changed successfully.")
            else:
                for field_errors in form.errors.values():
                    for error in field_errors:
                        messages.error(request, error)
            return redirect('employer_settings')

    context = {
        'profile': profile,
        'subscription': subscription,
    }
    return render(request, 'core/employer_settings.html', context)

#Job List view ---------------------------------------------------------------------------------------------------------
@employer_required
def jobs_list(request):
    jobs = Job.objects.filter(posted_by=request.user).order_by('-posted_at')
    return render(request, 'core/jobs_list.html', {'jobs': jobs})

#Apply Job view ---------------------------------------------------------------------------------------------------------
@login_required(login_url='job_seeker_login')
def apply_job(request, job_id):
    job = get_object_or_404(Job, id=job_id)

    if not hasattr(request.user, 'jobseeker_profile'):
        messages.info(
            request,
            'Please complete your profile before applying.'
        )
        return redirect(
            f"{reverse('create_profile')}?next={reverse('apply_job', args=[job_id])}"
        )

    profile = request.user.jobseeker_profile

    already_applied = JobApplication.objects.filter(
        job=job,
        job_seeker_profile=profile
    ).exists()

    if request.method == "POST":

        if already_applied:
            messages.warning(request, "You have already applied for this job.")
            return redirect("job_detail", job_id=job.id)

        application = JobApplication.objects.create(
            job=job,
            job_seeker_profile=profile,
        )

        create_notification(
            user=job.posted_by,
            message=f"{profile.full_name} applied for {job.job_title}",
            notification_type='new_applicant',
            link=reverse('manage_candidates'),
        )

        if request.user.email:
            try:
                result = send_mail(
                    subject=f"Application Submitted: {job.job_title}",
                    message=(
                        f"Hi {profile.full_name},\n\n"
                        f"Your application for '{job.job_title}' has been received successfully.\n\n"
                        f"Location : {job.location}\n"
                        f"Job Type : {job.job_type}\n\n"
                        "The employer will review your application and "
                        "contact you if you are shortlisted.\n\n"
                        "Thank you for using Deploynix.\n\n"
                        "Regards,\n"
                        "Team Deploynix"
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[request.user.email],
                    fail_silently=False,
                )

                messages.success(
                    request,
                    "Application submitted successfully. Confirmation email sent."
                )

            except Exception as e:
                print("EMAIL ERROR:", str(e))
                messages.error(
                    request,
                    f"Application saved, but email could not be sent: {e}"
                )

        else:
            messages.warning(
                request,
                "Application submitted, but no email address is associated with your account."
            )

        return redirect("application_success", job_id=job.id)

    return render(
        request,
        "core/apply_job.html",
        {
            "job": job,
            "profile": profile,
            "already_applied": already_applied,
        },
    )

#Application Success view ---------------------------------------------------------------------------------------------------------
def application_success(request, job_id):
    job = Job.objects.get(id=job_id)
    return render(request, 'core/application_success.html', {'job': job})

#Delete Application view ---------------------------------------------------------------------------------------------------------
@login_required(login_url='job_seeker_login')
@require_POST
def delete_application(request, application_id):
    application = JobApplication.objects.get(id=application_id)

    if application.job_seeker_profile.user != request.user:
        messages.error(request, 'You are not authorized to do that.')
        return redirect('my_applications')

    application.delete()
    messages.success(request, 'Application withdrawn successfully.')
    return redirect('my_applications')

# ---- Candidate list helper ----
def _candidate_list_context(request, applications, page_title, show_search=False, search_values=None):
    subscription = getattr(request.user, 'subscription', None)
    unlocked_ids = set(
        ResumeUnlock.objects.filter(employer=request.user, application__in=applications)
        .values_list('application_id', flat=True)
    )

    for app in applications:
        app.ats_score = compute_ats_score_for_application(app)

    context = {
        'applications': applications,
        'page_title': page_title,
        'unlocked_ids': unlocked_ids,
        'subscription': subscription,
        'show_search': show_search,
    }
    if search_values is not None:
        context['search_values'] = search_values
    return context

@employer_required
def new_applicants(request):
    applications = JobApplication.objects.filter(job__posted_by=request.user, status='applied').order_by('-applied_at')
    context = _candidate_list_context(request, applications, 'New Applicants')
    return render(request, 'core/candidates_list.html', context)


@employer_required
def manage_candidates(request):
    applications = JobApplication.objects.filter(job__posted_by=request.user).order_by('-applied_at')
    context = _candidate_list_context(request, applications, 'Manage Candidates')
    return render(request, 'core/candidates_list.html', context)


@employer_required
def shortlisted(request):
    applications = JobApplication.objects.filter(job__posted_by=request.user, status='shortlisted').order_by('-applied_at')
    context = _candidate_list_context(request, applications, 'Shortlisted Candidates')
    return render(request, 'core/candidates_list.html', context)


@employer_required
def search_resume(request):
    name = request.GET.get('name', '')
    skills = request.GET.get('skills', '')
    experience = request.GET.get('experience', '')
    education = request.GET.get('education', '')
    location = request.GET.get('location', '')
    job_description = request.GET.get('job_description', '').strip()

    applications = JobApplication.objects.filter(job__posted_by=request.user)

    if name:
        applications = applications.filter(
            Q(full_name__icontains=name) | Q(job_seeker_profile__full_name__icontains=name)
        )
    if skills:
        applications = applications.filter(
            Q(skills__icontains=skills) | Q(job_seeker_profile__skills__icontains=skills)
        )
    if experience:
        applications = applications.filter(
            Q(experience__icontains=experience) | Q(job_seeker_profile__experience__icontains=experience)
        )
    if education:
        applications = applications.filter(
            Q(education__icontains=education) | Q(job_seeker_profile__education__icontains=education)
        )
    if location:
        applications = applications.filter(
            Q(job__location__icontains=location) | Q(job_seeker_profile__location__icontains=location)
        )

    applications = list(applications.order_by('-applied_at'))

    if job_description:
        jd_keywords = extract_keywords(job_description)
        for app in applications:
            profile = app.job_seeker_profile
            candidate_text = ' '.join(filter(None, [
                getattr(profile, 'skills', '') if profile else '',
                getattr(app, 'skills', '') or '',
                getattr(profile, 'certificates', '') if profile else '',
            ]))
            candidate_keywords = extract_keywords(candidate_text)
            if jd_keywords:
                overlap = jd_keywords & candidate_keywords
                app.jd_match_score = round((len(overlap) / len(jd_keywords)) * 100)
            else:
                app.jd_match_score = 0
        applications.sort(key=lambda a: a.jd_match_score, reverse=True)
    else:
        for app in applications:
            app.jd_match_score = None

    context = _candidate_list_context(
        request, applications, 'Search Resume',
        show_search=True,
        search_values={
            'name': name, 'skills': skills, 'experience': experience,
            'education': education, 'location': location,
            'job_description': job_description,
        },
    )
    return render(request, 'core/candidates_list.html', context)
def send_verification_email(request, user):
    if not user.email:
        return
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    verify_url = request.build_absolute_uri(
        reverse('verify_email', kwargs={'uidb64': uid, 'token': token})
    )
    try:
        send_mail(
            subject='Verify your Deploynix email',
            message=(
                f"Hi {user.username},\n\n"
                "Please verify your email address to activate all features of your Deploynix account.\n\n"
                f"Click here to verify: {verify_url}\n\n"
                "If you didn't create this account, you can ignore this email.\n\n"
                "Best,\nTeam Deploynix"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception as e:
        print("VERIFICATION EMAIL ERROR:", e)


def verify_email(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        if hasattr(user, 'jobseeker_profile'):
            user.jobseeker_profile.is_email_verified = True
            user.jobseeker_profile.save()
        if hasattr(user, 'profile'):
            user.profile.is_email_verified = True
            user.profile.save()
        messages.success(request, 'Your email has been verified!')
    else:
        messages.error(request, 'This verification link is invalid or has expired.')

    return redirect('home')


@login_required(login_url='job_seeker_login')
def resend_verification(request):
    send_verification_email(request, request.user)
    messages.info(request, 'Verification email sent. Please check your inbox.')
    return redirect(request.META.get('HTTP_REFERER', 'home'))

@employer_required
@require_POST
def unlock_resume(request, application_id):
    application = JobApplication.objects.get(id=application_id)

    if application.job.posted_by != request.user:
        messages.error(request, 'You are not authorized to do that.')
        return redirect('manage_candidates')

    already_unlocked = ResumeUnlock.objects.filter(employer=request.user, application=application).exists()
    if already_unlocked:
        return redirect(request.META.get('HTTP_REFERER', 'manage_candidates'))

    if settings.SUBSCRIPTION_ENABLED:
        subscription = getattr(request.user, 'subscription', None)
        if not subscription or not subscription.can_view_resume():
            messages.warning(request, "You've hit your resume view limit. Upgrade your plan to view more candidates.")
            return redirect('subscription_plans')

    ResumeUnlock.objects.create(employer=request.user, application=application)

    if settings.SUBSCRIPTION_ENABLED:
        subscription.resumes_viewed_count += 1
        subscription.save()

    return redirect(request.META.get('HTTP_REFERER', 'manage_candidates'))

@employer_required
def update_application_status(request, application_id):
    application = JobApplication.objects.get(id=application_id)

    if application.job.posted_by != request.user:
        messages.error(request, 'You are not authorized to do that.')
        return redirect('manage_candidates')

    new_status = request.POST.get('status')
    if new_status in dict(JobApplication.STATUS_CHOICES):
        application.status = new_status
        application.save()

        if application.job_seeker_profile:
            create_notification(
                user=application.job_seeker_profile.user,
                message=f"Your application for {application.job.job_title} is now {application.get_status_display()}",
                notification_type='application_status',
                link=reverse('my_applications'),
            )

    return redirect(request.META.get('HTTP_REFERER', 'manage_candidates'))

def inquiries(request):
    inquiries = Inquiry.objects.all().order_by('-created_at')
    return render(request, 'core/inquiries.html', {'inquiries': inquiries})


@employer_required
def add_candidate(request):
    if request.method == 'POST':
        form = EmployerAddCandidateForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Candidate added successfully.')
            return redirect('manage_candidates')
    else:
        form = EmployerAddCandidateForm(user=request.user)
    return render(request, 'core/add_candidate.html', {'form': form})


@employer_required
def add_interview(request):
    if request.method == 'POST':
        form = InterviewForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Interview scheduled successfully.')
            return redirect('employer_dashboard')
    else:
        form = InterviewForm(user=request.user)
    return render(request, 'core/add_interview.html', {'form': form})


@login_required(login_url='job_seeker_login')
def create_profile(request):
    if hasattr(request.user, 'jobseeker_profile'):
        return redirect('edit_profile')

    if request.method == 'POST':
        form = JobSeekerProfileForm(request.POST, request.FILES)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.user = request.user
            profile.save()
            messages.success(request, 'Profile created successfully.')
            next_url = request.GET.get('next', 'home')
            return redirect(next_url)
    else:
        form = JobSeekerProfileForm()

    return render(request, 'core/create_profile.html', {'form': form})

@login_required(login_url='job_seeker_login')
def edit_profile(request):
    profile, created = JobSeekerProfile.objects.get_or_create(
        user=request.user, defaults={'full_name': request.user.username, 'phone': ''}
    )

    if request.method == 'POST':
        form = JobSeekerProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()

            new_email = request.POST.get('email', '').strip()
            if new_email:
                request.user.email = new_email
                request.user.save()

            messages.success(request, 'Profile updated successfully.')

            next_url = request.POST.get('next') or request.GET.get('next')
            if next_url:
                return redirect(next_url)
            return redirect('job_vacancies')
    else:
        form = JobSeekerProfileForm(instance=profile)

    return render(request, 'core/edit_profile.html', {
        'form': form,
        'next': request.GET.get('next', ''),
        'current_email': request.user.email,
    })


# ---- Subscription plans / Razorpay payment ----

@employer_required
def subscription_plans(request):
    plans = SubscriptionPlan.objects.all().order_by('price')
    current_sub = getattr(request.user, 'subscription', None)
    jobs_posted_live = Job.objects.filter(posted_by=request.user).count()
    return render(request, 'core/subscription_plans.html', {
        'plans': plans,
        'current_sub': current_sub,
        'jobs_posted_live': jobs_posted_live,
        'razorpay_key_id': settings.RAZORPAY_KEY_ID,
    })


@employer_required
@require_POST
def create_razorpay_order(request, plan_id):
    plan = SubscriptionPlan.objects.get(id=plan_id)

    if plan.price == 0:
        EmployerSubscription.objects.update_or_create(
            user=request.user,
            defaults={
                'plan': plan,
                'expires_at': timezone.now() + timedelta(days=plan.duration_days),
                'jobs_posted_count': 0,
                'resumes_viewed_count': 0,
            }
        )
        return JsonResponse({'free': True, 'redirect': reverse('employer_dashboard')})

    amount_paise = plan.price * 100
    order = razorpay_client.order.create({
        'amount': amount_paise,
        'currency': 'INR',
        'payment_capture': 1,
        'notes': {'plan_id': plan.id, 'user_id': request.user.id},
    })

    return JsonResponse({
        'free': False,
        'order_id': order['id'],
        'amount': amount_paise,
        'key_id': settings.RAZORPAY_KEY_ID,
        'plan_name': plan.name,
        'user_email': request.user.email,
    })


@csrf_exempt
@employer_required
@require_POST
def verify_payment(request):
    data = json.loads(request.body)
    plan_id = data.get('plan_id')

    params_dict = {
        'razorpay_order_id': data.get('razorpay_order_id'),
        'razorpay_payment_id': data.get('razorpay_payment_id'),
        'razorpay_signature': data.get('razorpay_signature'),
    }

    try:
        razorpay_client.utility.verify_payment_signature(params_dict)
    except razorpay.errors.SignatureVerificationError:
        return JsonResponse({'success': False, 'error': 'Signature verification failed'}, status=400)

    plan = SubscriptionPlan.objects.get(id=plan_id)
    EmployerSubscription.objects.update_or_create(
        user=request.user,
        defaults={
            'plan': plan,
            'expires_at': timezone.now() + timedelta(days=plan.duration_days),
            'jobs_posted_count': 0,
            'resumes_viewed_count': 0,
        }
    )

    return JsonResponse({'success': True, 'redirect': reverse('employer_dashboard')})


def logout_view(request):
    logout(request)
    return redirect('home')


@employer_required
@require_POST
def delete_job(request, job_id):
    job = Job.objects.get(id=job_id)

    if job.posted_by != request.user:
        messages.error(request, 'You are not authorized to do that.')
        return redirect('jobs_list')

    job.delete()
    messages.success(request, 'Job posting removed.')
    return redirect('jobs_list')

@employer_required
def candidate_detail(request, application_id):
    application = JobApplication.objects.get(id=application_id)

    if application.job.posted_by != request.user:
        messages.error(request, 'You are not authorized to view that.')
        return redirect('employer_dashboard')

    if not application.is_viewed:
        application.is_viewed = True
        application.save()

    return render(request, 'core/candidate_detail.html', {'application': application})


def internships(request):
    query = request.GET.get('q', '').strip()
    location = request.GET.get('location', '').strip()

    jobs = Job.objects.filter(job_type='internship').order_by('-posted_at')

    if query:
        jobs = jobs.filter(Q(job_title__icontains=query) | Q(skills_required__icontains=query))
    if location:
        jobs = jobs.filter(location__icontains=location)

    applied_job_ids = set()
    if request.user.is_authenticated and hasattr(request.user, 'jobseeker_profile'):
        applied_job_ids = set(
            JobApplication.objects.filter(job_seeker_profile=request.user.jobseeker_profile)
            .values_list('job_id', flat=True)
        )

    return render(request, 'core/internships.html', {
        'jobs': jobs,
        'query': query,
        'location': location,
        'applied_job_ids': applied_job_ids,
    })


# Common words to ignore when extracting "skills" from a job description
ATS_STOPWORDS = {
    'the','and','for','with','you','your','are','will','have','has','this','that',
    'from','our','who','can','all','any','into','out','not','but','they','their',
    'work','experience','years','year','strong','good','excellent','ability',
    'skills','skill','required','requirement','requirements','job','role','team',
    'looking','candidate','candidates','knowledge','understanding','proficient',
    'proficiency','familiarity','plus','preferred','including','etc','using',
    'we','a','an','in','on','of','to','is','be','as','or','at',
}


def extract_text_from_resume(resume_file):
    text = ''
    try:
        reader = PdfReader(resume_file)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + ' '
    except Exception:
        return ''
    return text


def extract_keywords(text):
    words = re.findall(r'[a-zA-Z][a-zA-Z0-9+#./-]{1,}', text.lower())
    keywords = set()
    for w in words:
        w = w.strip('.,-/')
        if len(w) > 2 and w not in ATS_STOPWORDS:
            keywords.add(w)
    return keywords


@login_required(login_url='job_seeker_login')
def ats_checker(request):
    result = None

    if request.method == 'POST':
        job_description = request.POST.get('job_description', '').strip()
        profile = getattr(request.user, 'jobseeker_profile', None)

        resume_file = request.FILES.get('resume')
        if not resume_file and profile and profile.resume:
            resume_file = profile.resume.open('rb')

        if not job_description:
            messages.error(request, 'Please paste a job description.')
        elif not resume_file:
            messages.error(request, 'Please upload a resume or add one to your profile first.')
        else:
            resume_text = extract_text_from_resume(resume_file)

            if not resume_text.strip():
                messages.error(request, 'Could not read text from that resume. Make sure it is a text-based PDF, not a scanned image.')
            else:
                jd_keywords = extract_keywords(job_description)
                resume_keywords = extract_keywords(resume_text)

                matched = sorted(jd_keywords & resume_keywords)
                missing = sorted(jd_keywords - resume_keywords)

                score = round((len(matched) / len(jd_keywords)) * 100) if jd_keywords else 0

                result = {
                    'score': score,
                    'matched': matched,
                    'missing': missing,
                    'total_keywords': len(jd_keywords),
                }

    return render(request, 'core/ats_checker.html', {'result': result})


#ats score checker ---------------------------------------------------------------------------------------------------------
def compute_ats_score_for_application(application):
    job = application.job
    profile = application.job_seeker_profile

    jd_text = f"{job.job_title} {getattr(job, 'job_description', '')} {getattr(job, 'skills_required', '')}"
    jd_keywords = extract_keywords(jd_text)

    if not jd_keywords:
        return None
    
    resume_text = ''
    if profile and getattr(profile, 'resume', None):
        try:
            resume_text = extract_text_from_resume(profile.resume.open('rb'))
        except Exception:
            resume_text = ''

    if not resume_text.strip():
        return None

    resume_keywords = extract_keywords(resume_text)
    matched = jd_keywords & resume_keywords
    score = round((len(matched) / len(jd_keywords)) * 100)
    return score


#to delete account view ---------------------------------------------------------------------------------------------------------
@login_required(login_url='job_seeker_login')
@require_POST
def delete_account(request):
    user = request.user

    if hasattr(user, 'jobseeker_profile'):
        JobApplication.objects.filter(job_seeker_profile=user.jobseeker_profile).delete()

    logout(request)
    user.delete()
    messages.success(request, 'Your account has been permanently deleted.')
    return redirect('home')


#notifications view ---------------------------------------------------------------------------------------------------------
@login_required
def notifications_list(request):
    notifications = request.user.notifications.all()[:30]
    request.user.notifications.filter(is_read=False).update(is_read=True)
    base_template = 'core/dashboard_base.html' if hasattr(request.user, 'profile') and request.user.profile.is_employer else 'core/base.html'
    return render(request, 'core/notifications.html', {
        'notifications': notifications,
        'base_template': base_template,
    })


@login_required
def unread_notification_count(request):
    count = request.user.notifications.filter(is_read=False).count()
    return JsonResponse({'count': count})

@login_required(login_url='job_seeker_login')
@require_POST
def toggle_save_job(request, job_id):
    job = get_object_or_404(Job, id=job_id)
    saved, created = SavedJob.objects.get_or_create(user=request.user, job=job)
    if not created:
        saved.delete()
        messages.info(request, 'Job removed from saved jobs.')
    else:
        messages.success(request, 'Job saved.')
    return redirect(request.META.get('HTTP_REFERER', 'job_vacancies'))


#saved jobs view ---------------------------------------------------------------------------------------------------------
@login_required(login_url='job_seeker_login')
def saved_jobs_list(request):
    saved = SavedJob.objects.filter(user=request.user).select_related('job')
    return render(request, 'core/saved_jobs.html', {'saved': saved})

def walkin_jobs(request):
    query = request.GET.get('q', '').strip()
    location = request.GET.get('location', '').strip()

    jobs = Job.objects.filter(job_type='walk-in').order_by('-posted_at')

    if query:
        jobs = jobs.filter(Q(job_title__icontains=query) | Q(skills_required__icontains=query))
    if location:
        jobs = jobs.filter(location__icontains=location)

    applied_job_ids = set()
    if request.user.is_authenticated and hasattr(request.user, 'jobseeker_profile'):
        applied_job_ids = set(
            JobApplication.objects.filter(job_seeker_profile=request.user.jobseeker_profile)
            .values_list('job_id', flat=True)
        )

    return render(request, 'core/walkin_jobs.html', {
        'jobs': jobs,
        'query': query,
        'location': location,
        'applied_job_ids': applied_job_ids,
    })

#edit job view ---------------------------------------------------------------------------------------------------------
@employer_required
def edit_job(request, job_id):
    job = get_object_or_404(Job, id=job_id)

    if job.posted_by != request.user:
        messages.error(request, 'You are not authorized to edit this job.')
        return redirect('jobs_list')

    if request.method == 'POST':
        form = JobPostForm(request.POST, instance=job)
        if form.is_valid():
            updated_job = form.save(commit=False)
            updated_job.approval_status = 'pending'
            updated_job.save()
            messages.success(request, 'Job updated. It will be re-reviewed by our admin team before it goes live again.')
            return redirect('jobs_list')
    else:
        form = JobPostForm(instance=job)

    return render(request, 'core/edit_job.html', {'form': form, 'job': job})

# ---------------------------------------------------------------------------
# Super Admin (platform admin) login -- separate flow with email OTP
# ---------------------------------------------------------------------------
def super_admin_login(request):
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        UserModel = get_user_model()

        user = None
        candidates = UserModel.objects.filter(email=email, is_superuser=True)
        for u in candidates:
            authed = authenticate(request, username=u.username, password=password)
            if authed is not None:
                user = authed
                break

        if user is not None and user.is_superuser:
            if settings.DEBUG:
                # Local development convenience: skip the email OTP.
                user.backend = 'django.contrib.auth.backends.ModelBackend'
                login(request, user)
                return redirect("control_panel")

            otp = str(random.randint(100000, 999999))
            request.session["sa_pending_user_id"] = user.id
            request.session["sa_otp"] = otp
            send_mail(
                subject="Your Deploynix admin verification code",
                message=f"Your verification code is: {otp}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )
            print(f"[DEV] Super admin OTP for {user.email}: {otp}")
            return render(request, "core/super_admin_login.html", {
                "step": "verify",
                "info": "Enter the verification code sent to your email.",
            })

        return render(request, "core/super_admin_login.html", {
            "error": "Invalid credentials or not authorized as a platform admin.",
        })

    return render(request, "core/super_admin_login.html", {})


def super_admin_verify(request):
    if request.method == "POST":
        entered = request.POST.get("otp", "").strip()
        expected = request.session.get("sa_otp")
        user_id = request.session.get("sa_pending_user_id")

        if not user_id or not expected:
            return redirect("super_admin_login")

        if entered == expected:
            UserModel = get_user_model()
            user = UserModel.objects.get(id=user_id)
            user.backend = 'django.contrib.auth.backends.ModelBackend'
            login(request, user)

            del request.session["sa_otp"]
            del request.session["sa_pending_user_id"]

            return redirect("control_panel")

        return render(request, "core/super_admin_login.html", {
            "step": "verify",
            "error": "Incorrect code. Please try again.",
        })

    return redirect("super_admin_login")


def _is_superuser(user):
    return user.is_authenticated and user.is_superuser


@user_passes_test(_is_superuser, login_url='super_admin_login')
def control_panel(request):
    now = timezone.now()
    month_ago = now - timedelta(days=30)
    week_from_now = now + timedelta(days=7)

    employers_total = Profile.objects.filter(is_employer=True).count()
    active_subscriptions = EmployerSubscription.objects.filter(expires_at__gt=now).count()
    expiring_soon = EmployerSubscription.objects.filter(
        expires_at__gt=now, expires_at__lte=week_from_now
    ).count()
    expired_subscriptions = EmployerSubscription.objects.filter(expires_at__lte=now).count()

    job_seekers_total = Profile.objects.filter(is_employer=False).count()
    job_seekers_new_month = Profile.objects.filter(
        is_employer=False, user__date_joined__gte=month_ago
    ).count()
    applications_total = JobApplication.objects.count()
    applications_hired = JobApplication.objects.filter(status='hired').count()

    jobs_total = Job.objects.count()
    jobs_views_total = sum(Job.objects.values_list('views_count', flat=True))
    inquiries_open = Inquiry.objects.exclude(status__in=['Read', 'Replied', 'Closed']).count()
    pending_approval = Job.objects.filter(approval_status='pending').count()

    recent_employers = EmployerSubscription.objects.select_related(
        'user', 'plan'
    ).order_by('-id')[:5]
    for sub in recent_employers:
        profile = Profile.objects.filter(user=sub.user).first()
        sub.company_name = profile.company_name if profile else sub.user.username
        sub.is_active = sub.expires_at > now

    recent_jobs = Job.objects.order_by('-posted_at')[:5]
    for job in recent_jobs:
        job.applications_count = JobApplication.objects.filter(job=job).count()

    context = {
        'employers_total': employers_total,
        'active_subscriptions': active_subscriptions,
        'expiring_soon': expiring_soon,
        'expired_subscriptions': expired_subscriptions,
        'job_seekers_total': job_seekers_total,
        'job_seekers_new_month': job_seekers_new_month,
        'applications_total': applications_total,
        'applications_hired': applications_hired,
        'jobs_total': jobs_total,
        'jobs_views_total': jobs_views_total,
        'inquiries_open': inquiries_open,
        'pending_approval': pending_approval,
        'recent_employers': recent_employers,
        'recent_jobs': recent_jobs,
    }
    return render(request, 'core/control_panel.html', context)


@user_passes_test(_is_superuser, login_url='super_admin_login')
def admin_employers_list(request):
    employers = Profile.objects.filter(is_employer=True).select_related('user').order_by('-user__date_joined')

    search = request.GET.get('search', '').strip()
    if search:
        employers = employers.filter(
            Q(company_name__icontains=search) | Q(user__email__icontains=search)
        )

    rows = []
    for profile in employers:
        subscription = EmployerSubscription.objects.filter(user=profile.user).select_related('plan').first()
        jobs_count = Job.objects.filter(posted_by=profile.user).count()
        rows.append({
            'user_id': profile.user.id,
            'company_name': profile.company_name or profile.user.username,
            'email': profile.user.email,
            'plan': subscription.plan.name if subscription else '—',
            'is_active': subscription.expires_at > timezone.now() if subscription else False,
            'jobs_count': jobs_count,
            'joined': profile.user.date_joined,
        })

    paginator = Paginator(rows, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'core/admin_employers_list.html', {
        'page_obj': page_obj,
        'search': search,
    })


@user_passes_test(_is_superuser, login_url='super_admin_login')
def admin_job_seekers_list(request):
    seekers = JobSeekerProfile.objects.select_related('user').order_by('-user__date_joined')

    search = request.GET.get('search', '').strip()
    if search:
        seekers = seekers.filter(
            Q(full_name__icontains=search) | Q(user__email__icontains=search)
        )

    rows = []
    for profile in seekers:
        applications_count = JobApplication.objects.filter(job_seeker_profile=profile).count()
        rows.append({
            'user_id': profile.user.id,
            'full_name': profile.full_name or profile.user.username,
            'email': profile.user.email,
            'location': profile.location or '—',
            'skills': profile.skills or '—',
            'applications_count': applications_count,
            'is_active': profile.user.is_active,
            'joined': profile.user.date_joined,
        })

    paginator = Paginator(rows, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'core/admin_job_seekers_list.html', {
        'page_obj': page_obj,
        'search': search,
    })


@user_passes_test(_is_superuser, login_url='super_admin_login')
def admin_subscriptions_list(request):
    now = timezone.now()
    subscriptions = EmployerSubscription.objects.select_related('user', 'plan').order_by('-expires_at')

    status_filter = request.GET.get('status', '').strip()
    if status_filter == 'active':
        subscriptions = subscriptions.filter(expires_at__gt=now)
    elif status_filter == 'expired':
        subscriptions = subscriptions.filter(expires_at__lte=now)

    search = request.GET.get('search', '').strip()
    if search:
        subscriptions = subscriptions.filter(
            Q(user__username__icontains=search) | Q(user__email__icontains=search)
        )

    rows = []
    for sub in subscriptions:
        profile = Profile.objects.filter(user=sub.user).first()
        rows.append({
            'company_name': profile.company_name if profile else sub.user.username,
            'email': sub.user.email,
            'plan_name': sub.plan.name if sub.plan else '—',
            'price': sub.plan.price if sub.plan else 0,
            'is_active': sub.expires_at > now,
            'expires_at': sub.expires_at,
            'jobs_posted_count': sub.jobs_posted_count,
            'resumes_viewed_count': sub.resumes_viewed_count,
        })

    paginator = Paginator(rows, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'core/admin_subscriptions_list.html', {
        'page_obj': page_obj,
        'search': search,
        'status_filter': status_filter,
    })


@user_passes_test(_is_superuser, login_url='super_admin_login')
def admin_plans_list(request):
    plans = SubscriptionPlan.objects.all().order_by('price')

    rows = []
    for plan in plans:
        active_subs_count = EmployerSubscription.objects.filter(
            plan=plan, expires_at__gt=timezone.now()
        ).count()
        rows.append({
            'id': plan.id,
            'name': plan.name,
            'price': plan.price,
            'duration_days': plan.duration_days,
            'job_post_limit': plan.job_post_limit,
            'resume_view_limit': plan.resume_view_limit,
            'active_subs_count': active_subs_count,
        })

    return render(request, 'core/admin_plans_list.html', {'plans': rows})

# Support chatbot + admin contact settings ----------------------------------------------------------------------------------------------------
def support_chat(request):
    """JSON endpoint powering the chatbot widget on every dashboard."""
    from .chatbot import bot_reply, SUPPORTED_LANGS
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body.decode('utf-8') or '{}')
    except (ValueError, UnicodeDecodeError):
        data = {}
    message = (data.get('message') or '').strip()
    lang = data.get('lang') or 'en-IN'
    if lang not in SUPPORTED_LANGS:
        lang = 'en-IN'
    if not message:
        return JsonResponse({'error': 'message is required'}, status=400)

    from django.contrib.auth.models import AnonymousUser
    user = request.user if request.user.is_authenticated else AnonymousUser()
    return JsonResponse(bot_reply(user, message, lang))


@user_passes_test(_is_superuser, login_url='super_admin_login')
def admin_support_settings(request):
    """Super admin assigns the customer-support call / message numbers."""
    contact = SupportContact.current()
    saved = False
    if request.method == 'POST':
        contact.phone_number = request.POST.get('phone_number', '').strip()
        contact.whatsapp_number = request.POST.get('whatsapp_number', '').strip()
        contact.email = request.POST.get('email', '').strip()
        contact.support_hours = request.POST.get('support_hours', '').strip()
        contact.is_call_enabled = request.POST.get('is_call_enabled') == 'on'
        contact.is_message_enabled = request.POST.get('is_message_enabled') == 'on'
        contact.save()
        saved = True
    return render(request, 'core/admin_support_settings.html', {
        'contact': contact,
        'saved': saved,
    })
