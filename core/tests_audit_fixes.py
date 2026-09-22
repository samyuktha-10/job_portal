"""Regression tests for fixes from the 2026-09-05 repository audit.

- BGV staff pages must render their own dark navbar (base.html now declares
  navbar/footer blocks; previously the child blocks were silently dropped).
- Interview.__str__ must use the dual-path safe display name.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Interview, Job, JobApplication, JobSeekerProfile
from verification.models import VerifierProfile


class BgvNavbarTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('verif1', password='pass12345')
        VerifierProfile.objects.create(user=self.user, role='verifier')
        self.client.force_login(self.user)

    def test_verifier_dashboard_uses_bgv_navbar(self):
        body = self.client.get(reverse('verification:verifier_dashboard')).content.decode()
        self.assertIn('<nav style="background:#030619', body)
        self.assertNotIn('Job Vacancy', body)  # public marketing nav must be gone

    def test_admin_queue_uses_bgv_navbar(self):
        admin = User.objects.create_user('verifadmin', password='pass12345')
        VerifierProfile.objects.create(user=admin, role='admin')
        self.client.force_login(admin)
        body = self.client.get(reverse('verification:admin_assignment_queue')).content.decode()
        self.assertIn('<nav style="background:#030619', body)
        self.assertNotIn('Job Vacancy', body)


class InterviewStrTests(TestCase):
    def test_str_uses_display_name_for_linked_applications(self):
        seeker = User.objects.create_user('seek1', password='pass12345')
        profile = JobSeekerProfile.objects.create(user=seeker, full_name='Priya Raghavan',
                                                  phone='9000000001')
        employer = User.objects.create_user('emp1', password='pass12345')
        job = Job.objects.create(posted_by=employer, job_title='Dev', job_description='d',
                                 experience_required='fresher', job_type='full-time',
                                 location='Chennai')
        app = JobApplication.objects.create(job=job, job_seeker_profile=profile)
        iv = Interview.objects.create(application=app,
                                      scheduled_at=timezone.now() + timedelta(days=1))
        self.assertIn('Priya Raghavan', str(iv))

    def test_str_uses_full_name_for_walkin_applications(self):
        employer = User.objects.create_user('emp2', password='pass12345')
        job = Job.objects.create(posted_by=employer, job_title='Ops', job_description='d',
                                 experience_required='fresher', job_type='walk-in',
                                 location='Chennai')
        app = JobApplication.objects.create(job=job, full_name='Walk In Person')
        iv = Interview.objects.create(application=app,
                                      scheduled_at=timezone.now() + timedelta(days=1))
        self.assertIn('Walk In Person', str(iv))
