"""AI mock interview: eligibility gating, typed + voice answers, scoring,
completion, employer notification, review access and private audio streaming."""
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import (Job, JobApplication, JobSeekerProfile,
                     MockInterviewSession, Notification, Profile)


class MockInterviewBase(TestCase):
    def setUp(self):
        self.employer = User.objects.create_user('employer', 'e@x.com', 'pass1234')
        Profile.objects.create(user=self.employer, is_employer=True, company_name='Deploynix')
        self.candidate = User.objects.create_user('cand', 'c@x.com', 'pass1234')
        self.js_profile = JobSeekerProfile.objects.create(
            user=self.candidate, full_name='Test Candidate', phone='9876543210')
        self.other = User.objects.create_user('other', 'o@x.com', 'pass1234')
        self.other_profile = JobSeekerProfile.objects.create(
            user=self.other, full_name='Other Candidate', phone='9876543211')
        self.stranger_emp = User.objects.create_user('stranger', 's@x.com', 'pass1234')
        Profile.objects.create(user=self.stranger_emp, is_employer=True, company_name='Stranger Co')

        self.job = Job.objects.create(
            posted_by=self.employer, job_title='Python Developer',
            job_description='We need Python and Django skills for backend APIs.',
            company_name='Deploynix', location='Chennai', job_type='full-time',
            salary_range='8-15 LPA', experience_required='1-3',
            skills_required='Python, Django, REST APIs, Unit Testing',
            approval_status='approved')
        self.app = JobApplication.objects.create(
            job=self.job, job_seeker_profile=self.js_profile, status='shortlisted')

    def _answer(self, text='I used Python and Django to build REST APIs with tests.',
                audio=None, extra=None):
        session = self.app.mock_interview
        current = session.answers.filter(answered_at__isnull=True).first()
        data = {'index': current.order, 'answer_text': text}
        if extra:
            data.update(extra)
        if audio:
            data['answer_audio'] = audio
        return self.client.post(
            reverse('mock_interview_run', args=[self.app.id]), data, follow=True)

    def _session(self):
        return MockInterviewSession.objects.get(application_id=self.app.id)

    def _complete_session(self, with_audio=False):
        self.client.force_login(self.candidate)
        self._start(self.client)
        for i in range(5):
            kwargs = {}
            if with_audio and i == 0:
                kwargs = {'audio': SimpleUploadedFile(
                    'answer.webm', b'RIFFaudio', content_type='audio/webm')}
            self._answer(
                text=f'Answer {i}: Python Django REST APIs testing teamwork ownership.',
                **kwargs)
        return self.app.mock_interview

    def _start(self, client, application=None):
        application = application or self.app
        return client.get(reverse('mock_interview_start',
                                  args=[application.id]), follow=True)



class MockInterviewFlowTests(MockInterviewBase):
    # ---------------- eligibility ----------------

    def test_start_blocked_before_shortlist(self):
        self.app.status = 'applied'
        self.app.save()
        self.client.force_login(self.candidate)
        response = self._start(self.client)
        self.assertRedirects(response, reverse('my_applications'))
        self.assertFalse(MockInterviewSession.objects.exists())

    def test_start_creates_session_with_five_questions(self):
        self.client.force_login(self.candidate)
        response = self._start(self.client)
        self.assertEqual(response.status_code, 200)
        session = self.app.mock_interview
        self.assertEqual(session.status, 'in_progress')
        self.assertEqual(session.answers.count(), 5)
        self.assertContains(response, 'Start recording')
        self.assertContains(response, 'Python')  # questions derive from the job

    def test_start_rejects_foreign_application(self):
        foreign = JobApplication.objects.create(
            job=self.job, job_seeker_profile=self.other_profile, status='shortlisted')
        self.client.force_login(self.candidate)
        response = self._start(self.client, application=foreign)
        self.assertRedirects(response, reverse('my_applications'))
        self.assertFalse(MockInterviewSession.objects.filter(application=foreign).exists())

    def test_start_is_idempotent(self):
        self.client.force_login(self.candidate)
        self._start(self.client)
        first = self.app.mock_interview.id
        self._start(self.client)
        self.assertEqual(self.app.mock_interview.id, first)
        self.assertEqual(MockInterviewSession.objects.count(), 1)

    # ---------------- answering ----------------


    def test_typed_answer_is_scored(self):
        self.client.force_login(self.candidate)
        self._start(self.client)
        response = self._answer()
        answered = self.app.mock_interview.answers.filter(
            answered_at__isnull=False).first()
        self.assertIsNotNone(answered.score)
        self.assertTrue(answered.feedback)
        self.assertIn('python', answered.matched_keywords)
        self.assertFalse(answered.used_mic)
        self.assertContains(response, 'Question 2 of 5')

    def test_empty_answer_rejected(self):
        self.client.force_login(self.candidate)
        self._start(self.client)
        self._answer(text='')
        self.assertEqual(
            self.app.mock_interview.answers.filter(answered_at__isnull=True).count(), 5)

    def test_voice_answer_saves_recording_and_transcript(self):
        self.client.force_login(self.candidate)
        self._start(self.client)
        audio = SimpleUploadedFile('answer.webm', b'RIFFaudio', content_type='audio/webm')
        self._answer(
            text='I have three years experience with Python Django and testing.',
            audio=audio, extra={'used_mic': '1', 'audio_duration_sec': '42'})
        answered = self.app.mock_interview.answers.filter(
            answered_at__isnull=False).first()
        self.assertTrue(answered.answer_audio)
        self.assertTrue(answered.used_mic)
        self.assertEqual(answered.audio_duration_sec, 42.0)

    def test_invalid_audio_extension_rejected(self):
        self.client.force_login(self.candidate)
        self._start(self.client)
        audio = SimpleUploadedFile('answer.exe', b'MZ', content_type='application/octet-stream')
        self._answer(text='Some answer about Python and Django.', audio=audio)
        self.assertEqual(
            self.app.mock_interview.answers.filter(answered_at__isnull=True).count(), 5)

    def test_oversized_audio_rejected(self):
        self.client.force_login(self.candidate)
        self._start(self.client)
        big = SimpleUploadedFile('answer.webm', b'x' * (11 * 1024 * 1024),
                                 content_type='audio/webm')
        self._answer(text='Some answer about Python and Django.', audio=big)
        self.assertEqual(
            self.app.mock_interview.answers.filter(answered_at__isnull=True).count(), 5)

    # ---------------- completion ----------------

    def test_completing_all_questions_scores_and_notifies_employer(self):
        self.client.force_login(self.candidate)
        self._start(self.client)
        for i in range(4):
            self._answer(text=f'Answer {i}: I worked with Python, Django, REST APIs and unit testing in teams.')
        session = self.app.mock_interview
        self.assertEqual(session.status, 'in_progress')
        response = self._answer(text='Final answer: I led a Python Django project with API testing and mentoring.')
        session.refresh_from_db()
        self.assertEqual(session.status, 'completed')
        self.assertIsNotNone(session.completed_at)
        self.assertTrue(0 <= session.overall_score <= 100)
        self.assertTrue(session.summary)
        self.assertContains(response, 'AI Mock Interview Report')
        self.assertContains(response, f'{session.overall_score}')

        notification = Notification.objects.filter(user=self.employer).first()
        self.assertIsNotNone(notification)
        self.assertIn('mock interview', notification.message)
        self.assertIn(str(session.overall_score), notification.message)
        self.assertEqual(notification.link,
                         reverse('mock_interview_review', args=[self.app.id]))

    def test_completed_session_redirects_run_to_result(self):
        self.client.force_login(self.candidate)
        self._start(self.client)
        for i in range(5):
            self._answer(text=f'Answer {i}: Python Django REST APIs testing teamwork ownership delivery.')
        response = self.client.get(reverse('mock_interview_run', args=[self.app.id]))
        self.assertRedirects(
            response, reverse('mock_interview_result', args=[self.app.id]))

    # ---------------- employer review + audio streaming ----------------


    def test_employer_review_shows_scores_and_transcript(self):
        self._complete_session()
        self.client.force_login(self.employer)
        response = self.client.get(
            reverse('mock_interview_review', args=[self.app.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Candidate')
        self.assertContains(response, '/100')
        self.assertContains(response, 'Python')

    def test_employer_review_blocked_for_other_employer(self):
        self._complete_session()
        self.client.force_login(self.stranger_emp)
        response = self.client.get(
            reverse('mock_interview_review', args=[self.app.id]))
        self.assertRedirects(response, reverse('manage_candidates'))

    def test_candidate_detail_links_review_when_taken(self):
        self._complete_session()
        self.client.force_login(self.employer)
        response = self.client.get(reverse('candidate_detail', args=[self.app.id]))
        self.assertContains(response, 'Review Mock Interview')

    def test_audio_stream_access_control(self):
        session = self._complete_session(with_audio=True)
        answer = session.answers.filter(answer_audio__isnull=False).first()
        self.assertIsNotNone(answer)
        url = reverse('mock_interview_audio', args=[answer.id])

        # candidate themselves
        self.client.force_login(self.candidate)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # job's employer
        self.client.force_login(self.employer)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # unrelated user
        self.client.force_login(self.other)
        response = self.client.get(url)
        self.assertRedirects(response, reverse('home'))


class MockInterviewRetakeTests(MockInterviewBase):
    RETAKE_TEXT = ('Retake answer: I led Python Django REST API delivery with unit '
                   'testing, mentored juniors and improved results because of it.')

    def _retake(self):
        return self.client.post(
            reverse('mock_interview_retake', args=[self.app.id]), follow=True)

    def _complete_attempt(self):
        for i in range(5):
            self._answer(text=f'{self.RETAKE_TEXT} Point {i}.')

    def test_retake_archives_history_and_resets_session(self):
        self._complete_session()
        first_score = self._session().overall_score
        self.client.force_login(self.candidate)
        response = self._retake()
        session = self._session()
        self.assertEqual(session.status, 'in_progress')
        self.assertEqual(session.current_attempt, 2)
        self.assertEqual(len(session.history), 1)
        self.assertEqual(session.history[0]['attempt'], 1)
        self.assertEqual(session.history[0]['overall_score'], first_score)
        self.assertEqual(session.best_overall_score, first_score)
        self.assertIsNone(session.overall_score)
        self.assertIsNone(session.completed_at)
        self.assertEqual(session.answers.count(), 5)
        self.assertEqual(session.answers.filter(answered_at__isnull=True).count(), 5)
        self.assertContains(response, 'Attempt 2 of 3')

    def test_retake_blocked_before_completion(self):
        self.client.force_login(self.candidate)
        self._start(self.client)
        response = self._retake()
        self.assertRedirects(
            response, reverse('mock_interview_run', args=[self.app.id]))
        self.assertEqual(self._session().current_attempt, 1)
        self.assertEqual(self._session().answers.count(), 5)

    def test_retake_blocked_for_other_candidate(self):
        self._complete_session()
        self.client.force_login(self.other)
        response = self.client.post(
            reverse('mock_interview_retake', args=[self.app.id]))
        self.assertRedirects(response, reverse('my_applications'))
        self.assertEqual(self._session().current_attempt, 1)
        self.assertEqual(self._session().status, 'completed')

    def test_max_three_attempts_enforced(self):
        self._complete_session()
        self.client.force_login(self.candidate)
        for _ in range(2):
            self._retake()
            self._complete_attempt()
        session = self._session()
        self.assertEqual(session.current_attempt, 3)
        self.assertEqual(len(session.history), 2)

        response = self._retake()  # 4th attempt must be refused
        session = self._session()
        self.assertEqual(session.current_attempt, 3)
        self.assertEqual(session.status, 'completed')
        self.assertContains(response, 'final')
        self.assertNotContains(response, 'Retake the interview')

    def test_best_score_tracked_and_employer_sees_history(self):
        self._complete_session()
        self.client.force_login(self.candidate)
        self._retake()
        self._complete_attempt()
        session = self._session()
        self.assertEqual(session.current_attempt, 2)
        self.assertEqual(
            session.best_overall_score,
            max(session.overall_score, session.history[0]['overall_score']))

        note = Notification.objects.filter(user=self.employer).latest('id')
        self.assertIn('attempt 2 of 3', note.message)

        self.client.force_login(self.employer)
        response = self.client.get(
            reverse('mock_interview_review', args=[self.app.id]))
        self.assertContains(response, 'ATTEMPT HISTORY')
        self.assertContains(response, 'Best:')

    def test_result_page_offers_retake_only_when_attempts_remain(self):
        self._complete_session()
        self.client.force_login(self.candidate)
        response = self.client.get(
            reverse('mock_interview_result', args=[self.app.id]))
        self.assertContains(response, 'Retake the interview')
        self._retake()
        self._complete_attempt()
        self._retake()
        self._complete_attempt()
        response = self.client.get(
            reverse('mock_interview_result', args=[self.app.id]))
        self.assertNotContains(response, 'Retake the interview')
        self.assertContains(response, 'this report is final')
