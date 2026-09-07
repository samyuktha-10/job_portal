"""Tests for address & employment document-type verification."""
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import Job, JobApplication, JobSeekerProfile, Profile
from .models import (
    VerificationRequest, VerificationStep, VerificationDocument, VerifierProfile,
    MAX_DOCUMENT_BYTES,
)


def small_pdf(name="proof.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4 fake", content_type="application/pdf")


class DocTypeUploadTests(TestCase):
    def setUp(self):
        self.emp = User.objects.create_user("boss@x.com", "boss@x.com", "pw")
        Profile.objects.create(user=self.emp, is_employer=True, company_name="Acme")
        self.job = Job.objects.create(
            posted_by=self.emp, job_title="UI/UX", job_description="d",
            experience_required="fresher", job_type="full-time", location="R",
            approval_status="approved",
        )
        self.seeker = User.objects.create_user("candidate1", "c1@x.com", "pw")
        prof = JobSeekerProfile.objects.create(user=self.seeker, full_name="Sam", phone="9")
        self.app = JobApplication.objects.create(job=self.job, job_seeker_profile=prof)
        self.bgv = VerificationRequest.objects.create(
            application=self.app, requested_by=self.emp, candidate_consent_given=True)
        for st in ("identity", "education", "employment", "address", "criminal"):
            VerificationStep.objects.create(request=self.bgv, step_type=st)
        self.client.login(username="candidate1", password="pw")
        self.url = reverse("verification:candidate_upload", args=[self.bgv.id])

    def _step(self, t):
        return VerificationStep.objects.get(request=self.bgv, step_type=t)

    def _post(self, step, doc_type, f):
        return self.client.post(self.url, {
            "upload_step_id": step.id, "doc_type": doc_type, "document": f,
        })

    def test_address_accepts_utility_bill(self):
        r = self._post(self._step("address"), "utility_bill", small_pdf())
        self.assertEqual(r.status_code, 302)
        doc = VerificationDocument.objects.get(step=self._step("address"))
        self.assertEqual(doc.doc_type, "utility_bill")
        self.assertEqual(self._step("address").status, "in_review")

    def test_address_accepts_passport(self):
        self._post(self._step("address"), "passport", small_pdf("passport.pdf"))
        self.assertEqual(VerificationDocument.objects.get(step=self._step("address")).doc_type, "passport")

    def test_address_rejects_employment_doc_type(self):
        self._post(self._step("address"), "payslip", small_pdf())
        self.assertEqual(VerificationDocument.objects.filter(step=self._step("address")).count(), 0)
        r = self.client.get(self.url)
        self.assertContains(r, "not an accepted document type")

    def test_employment_accepts_payslip(self):
        self._post(self._step("employment"), "payslip", small_pdf())
        self.assertEqual(VerificationDocument.objects.get(step=self._step("employment")).doc_type, "payslip")

    def test_employment_accepts_pf_statement(self):
        self._post(self._step("employment"), "pf_statement", small_pdf("pf.pdf"))
        self.assertEqual(VerificationDocument.objects.get(step=self._step("employment")).doc_type, "pf_statement")

    def test_bad_extension_rejected(self):
        self._post(self._step("address"), "passport",
                   SimpleUploadedFile("evil.exe", b"MZ", content_type="application/octet-stream"))
        self.assertEqual(VerificationDocument.objects.count(), 0)

    def test_oversized_rejected(self):
        big = SimpleUploadedFile("big.pdf", b"x" * (MAX_DOCUMENT_BYTES + 1), content_type="application/pdf")
        self._post(self._step("address"), "passport", big)
        self.assertEqual(VerificationDocument.objects.count(), 0)

    def test_generic_step_still_accepts_plain_document(self):
        # identity/education/criminal keep the generic fallback
        self._post(self._step("education"), "document", small_pdf("cert.pdf"))
        self.assertEqual(VerificationDocument.objects.get(step=self._step("education")).doc_type, "document")

    def test_candidate_saves_declared_address(self):
        r = self.client.post(self.url, {
            "save_address": "1", "candidate_address": "12, Anna Street, Chennai 600002"})
        self.assertEqual(r.status_code, 302)
        self.bgv.refresh_from_db()
        self.assertIn("Anna Street", self.bgv.candidate_address)
        self.assertContains(self.client.get(self.url), "Anna Street")

    def test_verifier_sees_declared_address(self):
        self.bgv.candidate_address = "12, Anna Street, Chennai"
        self.bgv.save()
        ver = User.objects.create_user("demo_verifier2", "v2@x.com", "pw")
        VerifierProfile.objects.create(user=ver, role="verifier")
        self.bgv.assigned_verifier = ver.verifier_profile
        self.bgv.save()
        self.client.login(username="demo_verifier2", password="pw")
        r = self.client.get(reverse(
            "verification:verifier_step_detail", args=[self._step("address").id]))
        self.assertContains(r, "Anna Street")

    def test_candidate_page_shows_doc_type_options(self):
        r = self.client.get(self.url)
        html = r.content.decode()
        self.assertIn('name="doc_type"', html)
        self.assertIn("Passport", html)
        self.assertIn("Utility bill", html)
        self.assertIn("Payslips", html)

    def test_verifier_sees_doc_type_label(self):
        self._post(self._step("address"), "utility_bill", small_pdf())
        ver = User.objects.create_user("demo_verifier", "v@x.com", "pw")
        VerifierProfile.objects.create(user=ver, role="verifier")
        self.bgv.assigned_verifier = ver.verifier_profile
        self.bgv.save()
        self.client.login(username="demo_verifier", password="pw")
        r = self.client.get(reverse(
            "verification:verifier_step_detail", args=[self._step("address").id]))
        self.assertContains(r, "Utility bill")


class EmployerBGVUITests(TestCase):
    def setUp(self):
        self.emp = User.objects.create_user("boss@x.com", "boss@x.com", "pw")
        Profile.objects.create(user=self.emp, is_employer=True, company_name="Acme")
        self.job = Job.objects.create(
            posted_by=self.emp, job_title="UI/UX", job_description="d",
            experience_required="fresher", job_type="full-time", location="R",
            approval_status="approved",
        )
        seeker = User.objects.create_user("candidate1", "c1@x.com", "pw")
        prof = JobSeekerProfile.objects.create(user=seeker, full_name="Sam", phone="9")
        self.app = JobApplication.objects.create(job=self.job, job_seeker_profile=prof)
        self.client.login(username="boss@x.com", password="pw")

    def test_shortlist_autocreates_and_page_shows_bgv_link(self):
        self.client.post(reverse("update_application_status", args=[self.app.id]),
                         {"status": "shortlisted"})
        r = self.client.get(reverse("manage_candidates"))
        self.assertContains(r, "BGV: Not Started")

    def test_request_bgv_button_and_manual_request(self):
        # queryset update() bypasses the post_save signal, so no BGV exists yet
        JobApplication.objects.filter(id=self.app.id).update(status="shortlisted")
        self.assertContains(self.client.get(reverse("manage_candidates")), "Request BGV")
        r = self.client.post(reverse("verification:request_bgv", args=[self.app.id]))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(VerificationRequest.objects.filter(application_id=self.app.id).exists())
        self.assertContains(self.client.get(reverse("manage_candidates")), "BGV: Not Started")

    def test_request_bgv_requires_shortlist(self):
        r = self.client.post(reverse("verification:request_bgv", args=[self.app.id]))
        self.assertEqual(r.status_code, 400)

    def test_employer_nav_has_verification_link(self):
        self.assertContains(self.client.get(reverse("jobs_list")), "Verification")
