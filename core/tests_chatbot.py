"""Tests for the support chatbot widget, its JSON endpoint, and the admin contact settings."""
import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import JobSeekerProfile, Profile, SupportContact


class ChatbotEndpointTests(TestCase):
    def post_msg(self, message, lang="en-IN"):
        r = self.client.post(
            reverse("support_chat"),
            data=json.dumps({"message": message, "lang": lang}),
            content_type="application/json")
        self.assertEqual(r.status_code, 200)
        return r.json()

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(reverse("support_chat")).status_code, 405)

    def test_anonymous_greeting_and_fallback(self):
        data = self.post_msg("hello there")
        self.assertEqual(data["intent"], "greeting")
        self.assertIn("Deploynix", data["reply"])
        data = self.post_msg("asdf qwerty")
        self.assertEqual(data["intent"], "fallback")

    def test_tamil_and_hindi_replies(self):
        data = self.post_msg("vanakkam", lang="ta-IN")
        self.assertEqual(data["lang"], "ta")
        self.assertIn("டிப்ளாய்னிக்ஸ்", data["reply"])
        data = self.post_msg("namaste", lang="hi-IN")
        self.assertEqual(data["lang"], "hi")
        self.assertIn("डिप्लॉयनिक्स", data["reply"])

    def test_unsupported_locale_falls_back_to_english(self):
        data = self.post_msg("hi", lang="xx-YY")
        self.assertEqual(data["lang"], "en")

    def test_candidate_live_answers(self):
        user = User.objects.create_user("c@x.com", "c@x.com", "pw")
        prof = JobSeekerProfile.objects.create(user=user, full_name="C", phone="9")
        self.client.login(username=user.username, password="pw")
        data = self.post_msg("show my applications")
        self.assertEqual(data["intent"], "my_applications")
        self.assertIn("0 application", data["reply"])
        data = self.post_msg("my saved jobs")
        self.assertIn("0 saved", data["reply"])

    def test_employer_live_answers(self):
        emp = User.objects.create_user("e@x.com", "e@x.com", "pw")
        Profile.objects.create(user=emp, is_employer=True, company_name="Co")
        self.client.login(username=emp.username, password="pw")
        data = self.post_msg("how many applicants do I have?")
        self.assertEqual(data["intent"], "my_jobs_stats")
        self.assertIn("0 job post", data["reply"])

    def test_role_mismatch_message(self):
        self.client.login(username=User.objects.create_user(
            "n@x.com", "n@x.com", "pw").username, password="pw")
        data = self.post_msg("my applications")
        self.assertEqual(data["intent"], "my_applications")
        self.assertIn("job seeker", data["reply"])

    def test_contact_intent_includes_hours(self):
        SupportContact.objects.create(pk=1, support_hours="Mon - Fri, 10 AM - 6 PM")
        data = self.post_msg("I want to contact support")
        self.assertEqual(data["intent"], "contact")
        self.assertIn("Mon - Fri, 10 AM - 6 PM", data["reply"])


class SupportContactAdminTests(TestCase):
    def setUp(self):
        self.su = User.objects.create_superuser("su@x.com", "su@x.com", "pw")

    def test_requires_superuser(self):
        r = self.client.get(reverse("admin_support_settings"))
        self.assertEqual(r.status_code, 302)  # redirected to super admin login

    def test_admin_saves_contact_and_widget_renders_it(self):
        self.client.login(username="su@x.com", password="pw")
        r = self.client.post(reverse("admin_support_settings"), {
            "phone_number": "+91 98765 43210",
            "whatsapp_number": "919876543210",
            "email": "help@deploynix.com",
            "support_hours": "Mon - Sat, 9 AM - 7 PM",
            "is_call_enabled": "on",
            "is_message_enabled": "on",
        })
        self.assertEqual(r.status_code, 200)
        c = SupportContact.current()
        self.assertEqual(c.phone_number, "+91 98765 43210")
        self.assertEqual(c.tel_link, "tel:+919876543210")
        self.assertEqual(c.wa_link, "https://wa.me/919876543210")

        # the widget on the home page now carries the admin-assigned contact
        home = self.client.get(reverse("home"))
        html = home.content.decode()
        self.assertIn("dnx-chat-btn", html)
        self.assertIn("tel:+919876543210", html)
        self.assertIn("wa.me/919876543210", html)

    def test_disabled_channels_hidden(self):
        self.client.login(username="su@x.com", password="pw")
        self.client.post(reverse("admin_support_settings"), {
            "phone_number": "+91 11111 11111",
            "whatsapp_number": "911111111111",
            "email": "",
            "support_hours": "24x7",
        })  # both checkboxes unchecked
        html = self.client.get(reverse("home")).content.decode()
        self.assertNotIn("tel:+911111111111", html)
        self.assertNotIn("wa.me/911111111111", html)
        self.assertIn("dnx-chat-btn", html)
