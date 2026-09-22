"""Tests for company trust verification (employer KYC).

Covers: the job-posting gate, KYC submission validation, the super-admin
review queue (verify / reject), protected document download, and the public
"Trusted & Valid" badge.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

import os
import shutil

from django.conf import settings
from django.test import TestCase

from .models import EmployerSubscription, Job, Profile, SubscriptionPlan


def cleanup_protected_uploads():
    """The protected store is a real directory (not per-test), so wipe it."""
    shutil.rmtree(os.path.join(settings.PROTECTED_MEDIA_ROOT, 'company_ids'),
                  ignore_errors=True)

PDF = SimpleUploadedFile
def pdf(name='corporate_id.pdf'):
    return PDF(name, b'%PDF-1.4 fake corporate id card', content_type='application/pdf')


class TrustBase(TestCase):
    def make_employer(self, username='employer1', trust_status='unverified'):
        user = User.objects.create_user(username=username, email=f'{username}@co.com',
                                        password='pass12345')
        profile = Profile.objects.create(user=user, is_employer=True,
                                         company_name=f'{username} Co')
        profile.trust_status = trust_status
        profile.save()
        return user, profile

    def make_admin(self):
        return User.objects.create_superuser('root', 'root@deploynix.in', 'admin12345')

    def give_subscription(self, user):
        plan = SubscriptionPlan.objects.create(name='T', price=499, duration_days=30,
                                               job_post_limit=5, resume_view_limit=5)
        return EmployerSubscription.objects.create(
            user=user, plan=plan, expires_at=timezone.now() + timedelta(days=30))


class PostingGateTests(TrustBase):
    def setUp(self):
        self.user, self.profile = self.make_employer()
        self.client.login(username='employer1', password='pass12345')

    def test_unverified_employer_cannot_reach_post_job_pages(self):
        for url in (reverse('post_job_select'), reverse('post_job', args=['full-time'])):
            r = self.client.get(url)
            self.assertRedirects(r, reverse('company_profile'))

    def test_unverified_employer_cannot_create_job(self):
        r = self.client.post(reverse('post_job', args=['full-time']), {
            'job_title': 'Dev', 'job_description': 'Desc', 'experience_required': 'fresher',
            'location': 'Chennai', 'number_of_openings': 1,
        })
        self.assertRedirects(r, reverse('company_profile'))
        self.assertEqual(Job.objects.count(), 0)

    def test_pending_employer_still_blocked(self):
        self.profile.trust_status = 'pending'
        self.profile.save()
        r = self.client.get(reverse('post_job_select'))
        self.assertRedirects(r, reverse('company_profile'))

    def test_verified_employer_can_post(self):
        self.profile.trust_status = 'verified'
        self.profile.save()
        self.give_subscription(self.user)
        r = self.client.post(reverse('post_job', args=['full-time']), {
            'job_title': 'Dev', 'job_description': 'Desc', 'experience_required': 'fresher',
            'job_type': 'full-time', 'location': 'Chennai', 'number_of_openings': 1,
        })
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Job.objects.count(), 1)
        self.assertEqual(Job.objects.first().approval_status, 'pending')


class SubmissionTests(TrustBase):
    def setUp(self):
        self.user, self.profile = self.make_employer()
        self.client.login(username='employer1', password='pass12345')

    def post_kyc(self, company_id='U72900MH2020PTC123456', doc=None):
        data = {'submit_trust': '1'}
        if company_id is not None:
            data['company_id'] = company_id
        if doc is not None:
            data['company_id_document'] = doc
        return self.client.post(reverse('company_profile'), data)

    def tearDown(self):
        cleanup_protected_uploads()

    def test_valid_submission_goes_pending(self):
        r = self.post_kyc(doc=pdf())
        self.assertRedirects(r, reverse('company_profile'))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.trust_status, 'pending')
        self.assertEqual(self.profile.company_id, 'U72900MH2020PTC123456')
        self.assertTrue(self.profile.company_id_document.name.startswith('company_ids/'))
        self.assertIsNotNone(self.profile.trust_submitted_at)

    def test_missing_company_id_rejected(self):
        self.post_kyc(company_id='', doc=pdf())
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.trust_status, 'unverified')

    def test_missing_document_rejected(self):
        self.post_kyc(doc=None)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.trust_status, 'unverified')

    def test_bad_extension_rejected(self):
        self.post_kyc(doc=SimpleUploadedFile('evil.exe', b'MZ\x90\x00'))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.trust_status, 'unverified')
        self.assertFalse(self.profile.company_id_document)

    def test_resubmit_after_rejection_clears_reason(self):
        self.profile.trust_status = 'rejected'
        self.profile.trust_rejection_reason = 'Blurry scan'
        self.profile.save()
        self.post_kyc(doc=pdf())
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.trust_status, 'pending')
        self.assertEqual(self.profile.trust_rejection_reason, '')


class AdminReviewTests(TrustBase):
    def setUp(self):
        self.user, self.profile = self.make_employer()
        self.admin = self.make_admin()
        self.profile.trust_status = 'pending'
        self.profile.company_id = 'U123'
        self.profile.save()

    def test_queue_requires_super_admin(self):
        seeker = User.objects.create_user('seeker1', password='pass12345')
        self.client.force_login(seeker)
        r = self.client.get(reverse('admin_company_verification'))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse('super_admin_login'), r.url)

    def test_verify_flows_to_employer(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse('admin_company_trust_set', args=[self.profile.id, 'verify']))
        self.assertRedirects(r, reverse('admin_company_verification'))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.trust_status, 'verified')
        self.assertEqual(self.profile.trust_reviewed_by, self.admin)
        self.assertTrue(self.profile.user.notifications.filter(
            message__contains='Trusted & Valid').exists())

    def test_reject_requires_reason_and_notifies(self):
        self.client.force_login(self.admin)
        url = reverse('admin_company_trust_set', args=[self.profile.id, 'reject'])
        r = self.client.post(url, {'reason': ''})
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.trust_status, 'pending')  # unchanged

        self.client.post(url, {'reason': 'Document expired'})
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.trust_status, 'rejected')
        self.assertEqual(self.profile.trust_rejection_reason, 'Document expired')
        self.assertTrue(self.profile.user.notifications.filter(
            message__contains='Document expired').exists())

    def test_unknown_action_404s(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse('admin_company_trust_set', args=[self.profile.id, 'nuke']))
        self.assertEqual(r.status_code, 404)


class DocumentDownloadTests(TrustBase):
    def setUp(self):
        self.user, self.profile = self.make_employer()
        self.admin = self.make_admin()
        self.profile.company_id_document = pdf()
        self.profile.trust_status = 'pending'
        self.profile.save()

    def tearDown(self):
        cleanup_protected_uploads()

    def test_anonymous_redirected(self):
        r = self.client.get(reverse('company_id_document_download', args=[self.profile.id]))
        self.assertEqual(r.status_code, 302)

    def test_seeker_and_owner_cannot_download(self):
        seeker = User.objects.create_user('seeker1', password='pass12345')
        self.client.force_login(seeker)
        r = self.client.get(reverse('company_id_document_download', args=[self.profile.id]))
        self.assertEqual(r.status_code, 302)  # admin_required bounce, not the file

        self.client.force_login(self.user)  # even the owner: admins-only by design
        r = self.client.get(reverse('company_id_document_download', args=[self.profile.id]))
        self.assertEqual(r.status_code, 302)

    def test_super_admin_downloads(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse('company_id_document_download', args=[self.profile.id]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertIn('attachment', r['Content-Disposition'])
        self.assertIn(b'%PDF-1.4', b''.join(r.streaming_content))

    def test_missing_document_404(self):
        cleanup_protected_uploads()
        self.profile.company_id_document = None
        self.profile.save()
        self.client.force_login(self.admin)
        r = self.client.get(reverse('company_id_document_download', args=[self.profile.id]))
        self.assertEqual(r.status_code, 404)


class BadgeTests(TrustBase):
    def _job_of(self, trust_status):
        user, profile = self.make_employer(username=f'emp-{trust_status}',
                                           trust_status=trust_status)
        return Job.objects.create(posted_by=user, job_title='Badged Role',
                                  company_name=profile.company_name,
                                  job_description='d', experience_required='fresher',
                                  job_type='full-time', location='Chennai',
                                  approval_status='approved')

    def test_verified_company_shows_badge(self):
        job = self._job_of('verified')
        body = self.client.get(reverse('job_detail', args=[job.id])).content.decode()
        self.assertIn('Trusted &amp; Valid', body)

    def test_unverified_company_shows_no_badge(self):
        job = self._job_of('unverified')
        body = self.client.get(reverse('job_detail', args=[job.id])).content.decode()
        self.assertNotIn('Trusted &amp; Valid', body)

    def test_vacancies_card_shows_badge_only_for_verified(self):
        good = self._job_of('verified')
        bad = self._job_of('pending')
        body = self.client.get(reverse('job_vacancies')).content.decode()
        self.assertEqual(body.count('Trusted &amp; Valid'), 1)
        self.assertIn(good.job_title, body)
        self.assertIn(bad.job_title, body)
