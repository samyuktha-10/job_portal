"""Create (or reset) the standard Deploynix demo accounts.

Idempotent: existing accounts keep their data but their passwords are reset
to the documented demo values, and any missing profile rows are created.

Usage:  python manage.py seed_demo_users

Accounts after running:
  Job seeker   candidate1      / demo1234   -> /job-seeker-login/   (username)
  Job seeker   candidate2      / demo1234   -> /job-seeker-login/   (username)
  Employer     demo_employer@deploynix.local / demo1234 -> /employer-login/ (email)
  Super admin  superadmin@deploynix.local    / admin@123 -> /super-admin/login/ (email)
  BGV verifier demo_verifier   / demo1234   -> /bgv/staff/login/    (username)
  BGV admin    bgv_admin       / demo1234   -> /bgv/staff/login/    (username)
"""
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from core.models import JobSeekerProfile, Profile
from verification.models import VerifierProfile

DEMO = "demo1234"

SEEKERS = [
    dict(username="candidate1", email="candidate1@deploynix.local",
         full_name="Demo Candidate One", phone="9000000001"),
    dict(username="candidate2", email="candidate2@deploynix.local",
         full_name="Demo Candidate Two", phone="9000000002"),
]

EMPLOYER = dict(username="demo_employer", email="demo_employer@deploynix.local",
                company_name="Demo Company")

SUPERADMIN = dict(username="superadmin", email="superadmin@deploynix.local",
                  password="admin@123")

VERIFIERS = [
    dict(username="demo_verifier", email="demo_verifier@deploynix.local", role="verifier"),
    dict(username="bgv_admin", email="bgv_admin@deploynix.local", role="admin"),
]


class Command(BaseCommand):
    help = "Create or reset the demo accounts (seekers, employer, super admin, BGV staff)."

    def handle(self, *args, **options):
        # --- Job seekers -------------------------------------------------
        for data in SEEKERS:
            user, _ = User.objects.update_or_create(
                username=data["username"],
                defaults={"email": data["email"], "is_staff": False, "is_superuser": False},
            )
            user.set_password(DEMO)
            user.save()
            if not hasattr(user, "jobseeker_profile"):
                JobSeekerProfile.objects.create(
                    user=user, full_name=data["full_name"], phone=data["phone"])
            self.stdout.write("  seeker    %s / %s" % (data["username"], DEMO))

        # --- Employer ----------------------------------------------------
        user, _ = User.objects.update_or_create(
            username=EMPLOYER["username"],
            defaults={"email": EMPLOYER["email"], "is_staff": False, "is_superuser": False},
        )
        user.set_password(DEMO)
        user.save()
        profile = Profile.objects.filter(user=user).first()
        if profile is None:
            profile = Profile.objects.create(user=user, is_employer=True,
                                             company_name=EMPLOYER["company_name"])
        else:
            profile.is_employer = True
            if not profile.company_name:
                profile.company_name = EMPLOYER["company_name"]
        # Demo employers ship pre-verified so the posting flow is usable out
        # of the box; real signups still start at 'unverified'.
        profile.company_id = "U72900MH2020PTC%06d" % (100000 + user.id)
        profile.trust_status = "verified"
        profile.save()
        self.stdout.write("  employer  %s / %s  (log in with EMAIL)" %
                          (EMPLOYER["email"], DEMO))

        # --- Super admin ---------------------------------------------------
        user, _ = User.objects.update_or_create(
            username=SUPERADMIN["username"],
            defaults={"email": SUPERADMIN["email"], "is_staff": True, "is_superuser": True},
        )
        # Ensure the flags even if the user already existed.
        user.is_staff = True
        user.is_superuser = True
        user.set_password(SUPERADMIN["password"])
        user.save()
        self.stdout.write("  admin     %s / %s  (log in with EMAIL)" %
                          (SUPERADMIN["email"], SUPERADMIN["password"]))

        # --- BGV staff -----------------------------------------------------
        for data in VERIFIERS:
            user, _ = User.objects.update_or_create(
                username=data["username"],
                defaults={"email": data["email"], "is_staff": False, "is_superuser": False},
            )
            user.set_password(DEMO)
            user.save()
            VerifierProfile.objects.update_or_create(
                user=user,
                defaults={"role": data["role"], "is_active": True},
            )
            self.stdout.write("  bgv %-5s %s / %s" % (data["role"], data["username"], DEMO))

        self.stdout.write(self.style.SUCCESS(
            "Done. All demo accounts are ready."))
