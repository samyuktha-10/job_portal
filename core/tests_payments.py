"""Tests for the hardened Razorpay payment flow.

Key guarantees:
- the activated plan comes from the server-side Payment row, never the body
- unknown / replayed / cross-user orders are rejected
- amount and payment ownership are confirmed with Razorpay itself
- CSRF protection is active on /plans/verify/
- the free tier is a one-time trial
"""
import json
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import views as core_views
from .models import EmployerSubscription, Payment, Profile, SubscriptionPlan


def make_employer(username='payemp'):
    user = User.objects.create_user(username=username, email=f'{username}@co.com',
                                    password='pass12345')
    Profile.objects.create(user=user, is_employer=True, company_name=f'{username} Co')
    return user


class PaymentFlowTests(TestCase):
    def setUp(self):
        self.user = make_employer()
        self.client.login(username='payemp', password='pass12345')
        self.free = SubscriptionPlan.objects.create(
            name='Free', price=0, duration_days=30, job_post_limit=2, resume_view_limit=5)
        self.basic = SubscriptionPlan.objects.create(
            name='Basic', price=499, duration_days=30, job_post_limit=10, resume_view_limit=50)
        self.premium = SubscriptionPlan.objects.create(
            name='Premium', price=1499, duration_days=30, job_post_limit=50, resume_view_limit=500)

    # ---- free tier -------------------------------------------------------
    def test_free_plan_is_one_time(self):
        r = self.client.post(reverse('create_razorpay_order', args=[self.free.id]))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['free'])
        self.assertTrue(EmployerSubscription.objects.filter(user=self.user).exists())

        r = self.client.post(reverse('create_razorpay_order', args=[self.free.id]))
        self.assertEqual(r.status_code, 403)
        self.assertIn('once', r.json()['error'])

    # ---- paid orders without credentials ---------------------------------
    def test_paid_order_requires_razorpay_keys(self):
        r = self.client.post(reverse('create_razorpay_order', args=[self.basic.id]))
        self.assertEqual(r.status_code, 503)
        self.assertIn('not configured', r.json()['error'])

    # ---- verify: rejection cases -----------------------------------------
    def post_verify(self, payload, client=None):
        return (client or self.client).post(
            reverse('verify_payment'), data=json.dumps(payload),
            content_type='application/json')

    def test_unknown_order_rejected(self):
        r = self.post_verify({'razorpay_order_id': 'order_nope',
                              'razorpay_payment_id': 'pay_x', 'razorpay_signature': 's'})
        self.assertEqual(r.status_code, 400)

    def test_replayed_payment_rejected(self):
        Payment.objects.create(user=self.user, plan=self.basic, order_id='order_1',
                               payment_id='pay_1', amount_paise=49900, status='paid')
        r = self.post_verify({'razorpay_order_id': 'order_1',
                              'razorpay_payment_id': 'pay_1', 'razorpay_signature': 's'})
        self.assertEqual(r.status_code, 400)

    def test_other_users_order_rejected(self):
        other = make_employer('otheremp')
        Payment.objects.create(user=other, plan=self.premium, order_id='order_2',
                               amount_paise=149900)
        r = self.post_verify({'razorpay_order_id': 'order_2',
                              'razorpay_payment_id': 'pay_2', 'razorpay_signature': 's'})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(EmployerSubscription.objects.filter(user=self.user).exists())

    def test_verify_requires_csrf(self):
        Payment.objects.create(user=self.user, plan=self.basic, order_id='order_3',
                               amount_paise=49900)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        r = strict.post(reverse('verify_payment'),
                        data=json.dumps({'razorpay_order_id': 'order_3'}),
                        content_type='application/json')
        self.assertEqual(r.status_code, 403)

    # ---- verify: happy path with Razorpay mocked --------------------------
    @override_settings(RAZORPAY_KEY_ID='rzp_test_key', RAZORPAY_KEY_SECRET='rzp_test_secret')
    def _verify_with_mocks(self, order_status='paid', order_amount=49900,
                           order_payments=('pay_ok',), expect_success=True):
        Payment.objects.create(user=self.user, plan=self.basic, order_id='order_ok',
                               amount_paise=49900)
        rpc = core_views.razorpay_client
        with mock.patch.object(rpc.utility, 'verify_payment_signature') as sig, \
             mock.patch.object(rpc.order, 'fetch',
                               return_value={'status': order_status, 'amount': order_amount}), \
             mock.patch.object(rpc.order, 'payments',
                               return_value={'items': [{'id': p} for p in order_payments]}):
            r = self.post_verify({
                # attacker-style body: claims Premium while the order was Basic
                'plan_id': self.premium.id,
                'razorpay_order_id': 'order_ok',
                'razorpay_payment_id': 'pay_ok',
                'razorpay_signature': 'fakesig',
            })
            sig.assert_called_once()
        return r

    def test_success_activates_server_side_plan_not_body_plan(self):
        r = self._verify_with_mocks()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['success'])
        sub = EmployerSubscription.objects.get(user=self.user)
        self.assertEqual(sub.plan, self.basic)          # NOT premium
        self.assertTrue(sub.is_active())
        payment = Payment.objects.get(order_id='order_ok')
        self.assertEqual(payment.status, 'paid')
        self.assertEqual(payment.payment_id, 'pay_ok')
        self.assertIsNotNone(payment.captured_at)

    def test_amount_mismatch_rejected(self):
        r = self._verify_with_mocks(order_amount=99900)   # paid less than plan price
        self.assertEqual(r.status_code, 400)
        self.assertFalse(EmployerSubscription.objects.filter(user=self.user).exists())
        self.assertEqual(Payment.objects.get(order_id='order_ok').status, 'failed')

    def test_unpaid_order_rejected(self):
        r = self._verify_with_mocks(order_status='created')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(EmployerSubscription.objects.filter(user=self.user).exists())

    def test_payment_from_other_order_rejected(self):
        r = self._verify_with_mocks(order_payments=('pay_someother',))
        self.assertEqual(r.status_code, 400)
        self.assertFalse(EmployerSubscription.objects.filter(user=self.user).exists())
