"""Tests for login UX extras: remember-me, password toggle, mobile login,
paid-members admin page and the bulk demo-data seeder."""
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from .models import (
    EmployerSubscription, JobSeekerProfile, Profile, SubscriptionPlan,
)


def make_seeker(username="seeker_x", phone="9876543210", password="demo1234"):
    user = User.objects.create_user(username=username,
                                    email="%s@x.com" % username, password=password)
    JobSeekerProfile.objects.create(user=user, full_name="Seeker X", phone=phone)
    return user


class RememberMeTests(TestCase):
    def setUp(self):
        make_seeker()

    def _login(self, **extra):
        data = {"username": "seeker_x", "password": "demo1234"}
        data.update(extra)
        return self.client.post("/job-seeker-login/", data)

    def test_remember_me_checked_keeps_session(self):
        r = self._login(remember_me="1")
        self.assertEqual(r.status_code, 302)
        self.assertFalse(self.client.session.get_expire_at_browser_close())
        self.assertGreater(self.client.session.get_expiry_age(), 60 * 60 * 24)

    def test_remember_me_unchecked_session_only(self):
        r = self._login()  # checkbox absent = unchecked
        self.assertEqual(r.status_code, 302)
        self.assertTrue(self.client.session.get_expire_at_browser_close())


class MobileLoginTests(TestCase):
    def setUp(self):
        make_seeker(phone="9876543210")

    def test_login_with_plain_mobile(self):
        r = self.client.post("/job-seeker-login/",
                             {"username": "9876543210", "password": "demo1234"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]),
                         User.objects.get(username="seeker_x").pk)

    def test_login_with_plus91_and_spaces(self):
        r = self.client.post("/job-seeker-login/",
                             {"username": "+91 98765 43210", "password": "demo1234"})
        self.assertEqual(r.status_code, 302)

    def test_login_with_leading_zero(self):
        r = self.client.post("/job-seeker-login/",
                             {"username": "09876543210", "password": "demo1234"})
        self.assertEqual(r.status_code, 302)

    def test_unknown_mobile_does_not_start_signup(self):
        r = self.client.post("/job-seeker-login/",
                             {"username": "9111111111", "password": "whatever"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "No job seeker account found for this mobile number")
        from .models import JobSeekerSignupOTP
        self.assertEqual(JobSeekerSignupOTP.objects.count(), 0)

    def test_wrong_password_via_mobile(self):
        r = self.client.post("/job-seeker-login/",
                             {"username": "9876543210", "password": "nope"})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_username_login_still_works(self):
        r = self.client.post("/job-seeker-login/",
                             {"username": "seeker_x", "password": "demo1234"})
        self.assertEqual(r.status_code, 302)


class PasswordToggleTests(TestCase):
    def test_toggle_script_on_login_pages(self):
        for url in ("/job-seeker-login/", "/employer-login/", "/super-admin/login/",
                    "/signup/", "/bgv/staff/login/"):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
            self.assertContains(r, "Password show/hide toggle", msg_prefix=url)

    def test_remember_me_checkbox_on_login_pages(self):
        for url in ("/job-seeker-login/", "/employer-login/", "/super-admin/login/",
                    "/bgv/staff/login/"):
            r = self.client.get(url)
            self.assertContains(r, 'name="remember_me"', msg_prefix=url)


class PaidMembersAdminTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_user(
            "boss", "boss@x.com", "pw", is_superuser=True, is_staff=True)
        self.free_plan = SubscriptionPlan.objects.create(
            name="Free", price=0, job_post_limit=2)
        self.premium = SubscriptionPlan.objects.create(
            name="Premium", price=1499, job_post_limit=50)

        self.paid_user = User.objects.create_user("paidco", "hr@paidco.in", "pw")
        Profile.objects.create(user=self.paid_user, is_employer=True,
                               company_name="Paid Co Pvt Ltd")
        EmployerSubscription.objects.create(
            user=self.paid_user, plan=self.premium,
            expires_at=timezone.now() + timezone.timedelta(days=10))

        self.free_user = User.objects.create_user("freeco", "hr@freeco.in", "pw")
        Profile.objects.create(user=self.free_user, is_employer=True,
                               company_name="Free Co")
        EmployerSubscription.objects.create(
            user=self.free_user, plan=self.free_plan,
            expires_at=timezone.now() + timezone.timedelta(days=10))

    def test_paid_page_lists_only_paying_companies(self):
        self.client.force_login(self.superuser)
        r = self.client.get("/control-panel/paid-members/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Paid Co Pvt Ltd")
        self.assertContains(r, "₹1499")
        self.assertNotContains(r, "Free Co")

    def test_paid_page_search(self):
        self.client.force_login(self.superuser)
        r = self.client.get("/control-panel/paid-members/", {"search": "zzz"})
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "Paid Co Pvt Ltd")

    def test_paid_page_requires_superuser(self):
        r = self.client.get("/control-panel/paid-members/")
        self.assertIn(r.status_code, (301, 302))
        seeker = make_seeker(username="plainuser")
        self.client.force_login(seeker)
        r = self.client.get("/control-panel/paid-members/")
        self.assertIn(r.status_code, (301, 302))


class SeedDemoDataTests(TestCase):
    def test_seed_idempotent_and_counts(self):
        call_command("seed_demo_data", verbosity=0)
        users_first = User.objects.count()
        seekers_first = JobSeekerProfile.objects.count()
        paid_first = EmployerSubscription.objects.exclude(plan__price=0).count()
        self.assertGreaterEqual(seekers_first, 40)
        self.assertEqual(paid_first, 9)

        call_command("seed_demo_data", verbosity=0)
        self.assertEqual(User.objects.count(), users_first)
        self.assertEqual(JobSeekerProfile.objects.count(), seekers_first)
        self.assertEqual(EmployerSubscription.objects.exclude(plan__price=0).count(),
                         paid_first)

    def test_seeded_accounts_can_login(self):
        call_command("seed_demo_data", verbosity=0)
        profile = JobSeekerProfile.objects.order_by("id").first()
        r = self.client.post("/job-seeker-login/",
                             {"username": profile.user.username,
                              "password": "demo1234"})
        self.assertEqual(r.status_code, 302)
        # ...and via mobile number too
        self.client.logout()
        r = self.client.post("/job-seeker-login/",
                             {"username": profile.phone, "password": "demo1234"})
        self.assertEqual(r.status_code, 302)

    def test_admin_pages_show_the_crowd(self):
        call_command("seed_demo_data", verbosity=0)
        su = User.objects.create_user("root2", "root2@x.com", "pw",
                                      is_superuser=True, is_staff=True)
        self.client.force_login(su)
        r = self.client.get("/control-panel/job-seekers/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Joseph Verma")   # seeker #40, first row of page 1
        self.assertContains(r, "Page 1 of 2")    # enough rows to paginate
        r = self.client.get("/control-panel/job-seekers/", {"page": "2"})
        self.assertContains(r, "Rahul Menon")    # seeker #1 on page 2
        r = self.client.get("/control-panel/employers/")
        self.assertContains(r, "Zenith Softworks")
        r = self.client.get("/control-panel/paid-members/")
        self.assertContains(r, "Zenith Softworks")
