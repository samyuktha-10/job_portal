"""AI mock interview views.

Candidate side: start -> run (answer by typing or by mic) -> result.
Employer side: review page for the company that shortlisted the candidate.
Voice recordings live in protected storage and are streamed only through
``mock_interview_audio`` to the candidate themselves or the job's employer.
"""
import mimetypes
import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import mock_ai
from .decorators import employer_required
from .models import JobApplication, MockInterviewAnswer, MockInterviewSession
from .views import create_notification

ALLOWED_STATUSES = {'shortlisted', 'hired'}


def _candidate_application(request, application_id):
    """The application if it belongs to the logged-in job seeker, else None."""
    app = get_object_or_404(JobApplication, id=application_id)
    profile = app.job_seeker_profile
    if profile is None or profile.user_id != request.user.id:
        messages.error(request, 'That mock interview belongs to another candidate.')
        return None
    return app


@login_required(login_url='job_seeker_login')
def mock_interview_start(request, application_id):
    app = _candidate_application(request, application_id)
    if app is None:
        return redirect('my_applications')

    if app.status not in ALLOWED_STATUSES:
        messages.warning(
            request,
            'The AI mock interview unlocks once the company shortlists you '
            'for an interview.')
        return redirect('my_applications')

    if not hasattr(app, 'mock_interview'):
        session = MockInterviewSession.objects.create(application=app)
        for i, q in enumerate(mock_ai.generate_questions(app.job)):
            session.answers.create(
                order=i, question=q['question'], kind=q['kind'],
                focus_keywords=q['focus_keywords'])
        messages.info(request, 'Your AI mock interview is ready - 5 questions, '
                               'answer by typing or by mic.')
    return redirect('mock_interview_run', application_id=app.id)


@login_required(login_url='job_seeker_login')
def mock_interview_run(request, application_id):
    app = _candidate_application(request, application_id)
    if app is None:
        return redirect('my_applications')
    session = getattr(app, 'mock_interview', None)
    if session is None:
        return redirect('mock_interview_start', application_id=app.id)
    if session.status == 'completed':
        return redirect('mock_interview_result', application_id=app.id)

    if request.method == 'POST':
        try:
            index = int(request.POST.get('index', '-1'))
        except ValueError:
            index = -1
        answer = session.answers.filter(order=index, answered_at__isnull=True).first()
        if answer is None:
            messages.error(request, 'That question has already been answered.')
            return redirect('mock_interview_run', application_id=app.id)

        text = request.POST.get('answer_text', '').strip()
        audio = request.FILES.get('answer_audio')
        used_mic = request.POST.get('used_mic') == '1' or bool(audio)

        if not text and not audio:
            messages.error(request, 'Type your answer or record it with the mic first.')
            return redirect('mock_interview_run', application_id=app.id)

        if audio:
            try:
                MockInterviewAnswer._meta.get_field('answer_audio').run_validators(audio)
            except ValidationError as exc:
                for err in exc.messages:
                    messages.error(request, err)
                return redirect('mock_interview_run', application_id=app.id)
            answer.answer_audio = audio
            try:
                answer.audio_duration_sec = float(request.POST.get('audio_duration_sec', ''))
            except (TypeError, ValueError):
                answer.audio_duration_sec = None

        answer.answer_text = text
        answer.used_mic = used_mic
        result = mock_ai.evaluate_answer(
            {'focus_keywords': answer.focus_keywords}, text, app.job)
        answer.score = result['score']
        answer.feedback = result['feedback']
        answer.matched_keywords = result['matched_keywords']
        answer.missing_keywords = result['missing_keywords']
        answer.answered_at = timezone.now()
        answer.save()

        if not session.answers.filter(answered_at__isnull=True).exists():
            overall, summary = mock_ai.build_summary(list(session.answers.all()), app.job)
            session.overall_score = overall
            session.summary = summary
            session.status = 'completed'
            session.completed_at = timezone.now()
            session.save()
            create_notification(
                user=app.job.posted_by,
                message=(f"{app.display_full_name} completed an AI mock interview "
                         f"for {app.job.job_title} - scored {overall}/100."),
                notification_type='new_applicant',
                link=reverse('mock_interview_review', args=[app.id]),
            )
            messages.success(request, f'Mock interview complete - you scored {overall}/100.')
            return redirect('mock_interview_result', application_id=app.id)

        return redirect('mock_interview_run', application_id=app.id)

    current = session.answers.filter(answered_at__isnull=True).first()
    answered = session.answers.filter(answered_at__isnull=False).count()
    return render(request, 'core/mock_interview_run.html', {
        'app': app,
        'session': session,
        'current': current,
        'total': session.answers.count(),
        'answered': answered,
    })


@login_required(login_url='job_seeker_login')
def mock_interview_result(request, application_id):
    app = _candidate_application(request, application_id)
    if app is None:
        return redirect('my_applications')
    session = getattr(app, 'mock_interview', None)
    if session is None or session.status != 'completed':
        return redirect('mock_interview_run', application_id=app.id)
    return render(request, 'core/mock_interview_result.html', {
        'app': app,
        'session': session,
        'answers': session.answers.all(),
    })


@employer_required
def mock_interview_review(request, application_id):
    app = get_object_or_404(JobApplication, id=application_id)
    if app.job.posted_by != request.user:
        messages.error(request, 'You are not authorized to view this candidate.')
        return redirect('manage_candidates')
    session = getattr(app, 'mock_interview', None)
    return render(request, 'core/mock_interview_review.html', {
        'application': app,
        'session': session,
        'answers': session.answers.all() if session else [],
    })


@login_required
def mock_interview_audio(request, answer_id):
    """Stream a voice recording to the candidate themselves or the employer."""
    answer = get_object_or_404(MockInterviewAnswer, id=answer_id)
    if not answer.answer_audio:
        raise Http404('No recording for this answer.')

    app = answer.session.application
    is_candidate = (app.job_seeker_profile is not None
                    and app.job_seeker_profile.user_id == request.user.id)
    is_employer = app.job.posted_by_id == request.user.id
    if not (is_candidate or is_employer):
        messages.error(request, 'You are not authorized to play this recording.')
        return redirect('home')

    name = os.path.basename(answer.answer_audio.name)
    content_type = mimetypes.guess_type(name)[0] or 'audio/mpeg'
    return FileResponse(answer.answer_audio.open('rb'), content_type=content_type)
