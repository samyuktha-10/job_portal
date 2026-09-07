"""Full-app cross-check: public, candidate, employer, super-admin, verifier/BGV-admin."""
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Job, JobApplication, JobSeekerProfile, Profile, SavedJob, SubscriptionPlan,
    EmployerSubscription, ResumeUnlock, Notification,
)
from verification.models import (
    VerificationRequest, VerificationStep, VerifierProfile, VerificationDocument,
)


def pdf(name="r.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4 x", content_type="application/pdf")


class PublicSmokeTests(TestCase):
    def test_public_pages(self):
        for url in ("/", "/vacancies/", "/internships/", "/walk-in-jobs/",
                    "/signup/", "/job-seeker-login/", "/employer-login/", "/super-admin/login/",
                    "/bgv/staff/login/", "/password-reset/"):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
        # ATS checker is job-seeker-only by design
        r = self.client.get("/ats-checker/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("job-seeker-login", r.url)

    def test_protected_pages_redirect_anonymous(self):
        for url in ("/employer-dashboard/", "/my-applications/", "/notifications/",
                    "/control-panel/", "/bgv/staff/verifier/"):
            r = self.client.get(url)
            self.assertIn(r.status_code, (301, 302), url)


class CandidateSmokeTests(TestCase):
    def setUp(self):
        self.emp = User.objects.create_user("boss@x.com", "boss@x.com", "pw")
        Profile.objects.create(user=self.emp, is_employer=True, company_name="Acme")
        self.job = Job.objects.create(
            posted_by=self.emp, job_title="UI/UX", job_description="design things",
            experience_required="fresher", job_type="full-time", location="Chennai",
            approval_status="approved", company_name="Acme")

    def test_job_seeker_signup_otp_flow(self):
        r = self.client.post("/job-seeker-login/", {
            "username": "newseeker", "email": "ns@x.com", "password": "Str0ngPass!"})
        self.assertEqual(r.status_code, 302)
        from core.models import JobSeekerSignupOTP
        otp_row = JobSeekerSignupOTP.objects.get(username="newseeker")
        r = self.client.post("/verify-signup-otp/", {"otp_code": otp_row.otp_code})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(User.objects.filter(username="newseeker").exists())

    def test_apply_manage_notify_and_bgv(self):
        User.objects.create_user("candidate1", "c1@x.com", "pw")
        prof = JobSeekerProfile.objects.create(user=User.objects.get(username="candidate1"),
                                               full_name="Sam", phone="9")
        self.client.login(username="candidate1", password="pw")

        # apply
        r = self.client.post(reverse("apply_job", args=[self.job.id]), {"resume": pdf()})
        self.assertEqual(r.status_code, 302)
        app = JobApplication.objects.get(job=self.job)

        # pages
        for name in ("my_applications", "saved_jobs_list", "notifications_list", "ats_checker"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        self.assertEqual(self.client.get(reverse("unread_notification_count")).status_code, 200)

        # save job
        self.client.post(reverse("toggle_save_job", args=[self.job.id]))
        self.assertTrue(SavedJob.objects.filter(job=self.job).exists())

        # shortlist happens employer-side; then candidate sees BGV notification + upload page
        self.client.logout()
        self.client.login(username="boss@x.com", password="pw")
        self.client.post(reverse("update_application_status", args=[app.id]), {"status": "shortlisted"})
        bgv = VerificationRequest.objects.get(application=app)
        self.assertTrue(Notification.objects.filter(
            user=prof.user, link__contains="/bgv/candidate/").exists())

        self.client.logout()
        self.client.login(username="candidate1", password="pw")
        up = reverse("verification:candidate_upload", args=[bgv.id])
        self.assertEqual(self.client.get(up).status_code, 200)
        self.assertEqual(self.client.post(up, {"give_consent": "1"}).status_code, 302)
        self.assertEqual(self.client.post(up, {
            "upload_step_id": bgv.steps.get(step_type="address").id,
            "doc_type": "utility_bill", "document": pdf("bill.pdf")}).status_code, 302)
        self.assertEqual(
            VerificationDocument.objects.get(step__request=bgv, step__step_type="address").doc_type,
            "utility_bill")

        # withdraw application
        self.client.post(reverse("delete_application", args=[app.id]))
        self.assertFalse(JobApplication.objects.filter(id=app.id).exists())

    def test_candidate_blocked_from_employer_area(self):
        User.objects.create_user("candidate1", "c1@x.com", "pw")
        JobSeekerProfile.objects.create(user=User.objects.get(username="candidate1"),
                                        full_name="Sam", phone="9")
        self.client.login(username="candidate1", password="pw")
        r = self.client.get(reverse("employer_dashboard"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("home"))


class EmployerSmokeTests(TestCase):
    def setUp(self):
        SubscriptionPlan.objects.create(name="Free", price=0, duration_days=30,
                                        job_post_limit=2, resume_view_limit=5,
                                        includes_bgv_access=True)

    def test_employer_journey(self):
        r = self.client.post(reverse("employer_login"), {
            "email": "newco@x.com", "password": "Str0ngPass!", "company_name": "NewCo"})
        self.assertEqual(r.status_code, 302)
        emp = User.objects.get(email="newco@x.com")
        self.assertTrue(Profile.objects.filter(user=emp, is_employer=True).exists())
        self.assertTrue(EmployerSubscription.objects.filter(user=emp).exists())

        self.client.login(username=emp.username, password="Str0ngPass!")
        for name in ("employer_dashboard", "jobs_list", "company_profile",
                     "employer_settings", "employer_reports", "new_applicants",
                     "manage_candidates", "shortlisted", "search_resume",
                     "add_candidate", "add_interview", "inquiries", "subscription_plans"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

        # post a job
        r = self.client.post("/post-job/full-time/", {
            "job_title": "Backend Dev", "company_name": "NewCo",
            "job_description": "build APIs", "experience_required": "fresher",
            "job_type": "full-time", "location": "Remote",
            "number_of_openings": 1, "salary_range": "", "skills_required": ""})
        self.assertEqual(r.status_code, 302)
        job = Job.objects.get(job_title="Backend Dev")

        # walk-in candidate
        r = self.client.post(reverse("add_candidate"), {
            "job": job.id, "full_name": "Walk In", "email": "w@x.com", "phone": "1",
            "education": "", "skills": "", "experience": "", "status": "applied",
            "source": "other"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(JobApplication.objects.filter(full_name="Walk In").exists())

        # candidate applies, employer shortlists -> BGV, resume unlock, status page
        seeker = User.objects.create_user("seek@x.com", "seek@x.com", "pw")
        prof = JobSeekerProfile.objects.create(user=seeker, full_name="Seek", phone="2")
        JobApplication.objects.create(job=job, job_seeker_profile=prof)
        app = JobApplication.objects.get(job_seeker_profile=prof)
        self.client.post(reverse("update_application_status", args=[app.id]),
                         {"status": "shortlisted"})
        self.assertTrue(VerificationRequest.objects.filter(application=app).exists())
        self.assertEqual(self.client.get(
            reverse("verification:company_bgv_status", args=[app.id])).status_code, 200)
        self.assertEqual(self.client.get(
            reverse("verification:company_bgv_overview")).status_code, 200)
        self.client.post(reverse("unlock_resume", args=[app.id]))
        self.assertTrue(ResumeUnlock.objects.filter(employer=emp, application=app).exists())
        self.assertEqual(self.client.get(reverse("candidate_detail", args=[app.id])).status_code, 200)

        # free-plan order endpoint
        plan = SubscriptionPlan.objects.get(name="Free")
        r = self.client.post(reverse("create_razorpay_order", args=[plan.id]))
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"free", r.content)

        # delete job
        self.client.post(reverse("delete_job", args=[job.id]))
        self.assertFalse(Job.objects.filter(id=job.id).exists())

    def test_bgv_gated_by_plan(self):
        SubscriptionPlan.objects.filter(name="Free").update(includes_bgv_access=False)
        r = self.client.post(reverse("employer_login"), {
            "email": "poor@x.com", "password": "Str0ngPass!", "company_name": "PoorCo"})
        emp = User.objects.get(email="poor@x.com")
        self.client.login(username=emp.username, password="Str0ngPass!")
        r = self.client.get(reverse("verification:company_bgv_overview"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("subscription_plans"))


class SuperAdminSmokeTests(TestCase):
    def setUp(self):
        self.su = User.objects.create_superuser("admin@gmail.com", "admin@gmail.com", "admin@123")

    @override_settings(DEBUG=True)
    def test_debug_bypass_only_in_dev(self):
        r = self.client.post("/super-admin/login/", {
            "email": "admin@gmail.com", "password": "admin@123"})
        self.assertEqual(r.status_code, 302)  # straight in, no OTP
        self.assertEqual(r.url, reverse("control_panel"))

    def test_control_panel_pages(self):
        # Test runner forces DEBUG=False, so log in via the OTP path
        self.client.post("/super-admin/login/", {
            "email": "admin@gmail.com", "password": "admin@123"})
        otp = self.client.session.get("sa_otp")
        r = self.client.post("/super-admin/verify/", {"otp": otp})
        self.assertEqual(r.status_code, 302)
        for url in ("/control-panel/", "/control-panel/jobs/",
                    "/control-panel/employers/", "/control-panel/job-seekers/",
                    "/control-panel/subscriptions/", "/control-panel/plans/",
                    "/control-panel/inquiries/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_django_admin(self):
        self.client.login(username="admin@gmail.com", password="admin@123")
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    @override_settings(DEBUG=False)
    def test_otp_required_in_production(self):
        r = self.client.post("/super-admin/login/", {
            "email": "admin@gmail.com", "password": "admin@123"})
        self.assertEqual(r.status_code, 200)  # verify step, not logged in
        otp = self.client.session.get("sa_otp")
        self.assertIsNotNone(otp)
        r = self.client.post("/super-admin/verify/", {"otp": otp})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("control_panel"))


class VerifierSmokeTests(TestCase):
    def setUp(self):
        self.emp = User.objects.create_user("boss@x.com", "boss@x.com", "pw")
        Profile.objects.create(user=self.emp, is_employer=True, company_name="Acme")
        self.job = Job.objects.create(
            posted_by=self.emp, job_title="UI/UX", job_description="d",
            experience_required="fresher", job_type="full-time", location="R",
            approval_status="approved", company_name="Acme")
        seeker = User.objects.create_user("c1@x.com", "c1@x.com", "pw")
        prof = JobSeekerProfile.objects.create(user=seeker, full_name="Sam", phone="9")
        self.app = JobApplication.objects.create(job=self.job, job_seeker_profile=prof)
        self.bgv = VerificationRequest.objects.create(application=self.app, requested_by=self.emp)
        for st in ("identity", "education", "employment", "address", "criminal"):
            VerificationStep.objects.create(request=self.bgv, step_type=st)
        self.ver = User.objects.create_user("demo_verifier", "v@x.com", "pw")
        VerifierProfile.objects.create(user=self.ver, role="verifier")
        self.adm = User.objects.create_user("bgv_admin", "a@x.com", "pw")
        VerifierProfile.objects.create(user=self.adm, role="admin")

    def test_verifier_login_and_loop(self):
        r = self.client.post("/bgv/staff/login/", {"username": "demo_verifier", "password": "pw"})
        self.assertEqual(r.status_code, 302)
        self.bgv.assigned_verifier = self.ver.verifier_profile
        self.bgv.save()
        self.assertEqual(self.client.get(reverse("verification:verifier_dashboard")).status_code, 200)
        step = self.bgv.steps.get(step_type="identity")
        r = self.client.post(reverse("verification:verifier_step_detail", args=[step.id]),
                             {"status": "verified", "remarks": "ok"})
        self.assertEqual(r.status_code, 302)
        step.refresh_from_db()
        self.assertEqual(step.status, "verified")

    def test_admin_queue_and_assign(self):
        self.client.login(username="bgv_admin", password="pw")
        self.assertEqual(self.client.get(reverse("verification:admin_assignment_queue")).status_code, 200)
        r = self.client.post(reverse("verification:admin_assign_verifier", args=[self.bgv.id]),
                             {"verifier_id": self.ver.verifier_profile.id})
        self.assertEqual(r.status_code, 302)
        self.bgv.refresh_from_db()
        self.assertEqual(self.bgv.assigned_verifier, self.ver.verifier_profile)

    def test_segregation_of_duties(self):
        # the employer who requested the BGV becomes a verifier -> cannot verify own case
        VerifierProfile.objects.create(user=self.emp, role="verifier")
        self.bgv.assigned_verifier = self.emp.verifier_profile
        self.bgv.save()
        self.client.login(username="boss@x.com", password="pw")
        step = self.bgv.steps.get(step_type="address")
        r = self.client.post(reverse("verification:verifier_step_detail", args=[step.id]),
                             {"status": "verified"})
        self.assertEqual(r.status_code, 403)

    def test_candidate_upload_forbidden_for_others(self):
        other = User.objects.create_user("other@x.com", "other@x.com", "pw")
        self.client.login(username="other@x.com", password="pw")
        r = self.client.get(reverse("verification:candidate_upload", args=[self.bgv.id]))
        self.assertEqual(r.status_code, 403)
