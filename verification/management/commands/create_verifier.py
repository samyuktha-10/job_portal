from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from verification.models import VerifierProfile


class Command(BaseCommand):
    help = "Create a background-verification staff account (verifier or BGV admin)."

    def add_arguments(self, parser):
        parser.add_argument("username", help="Login username for the verifier")
        parser.add_argument("--password", dest="password", default=None,
                            help="Password (if omitted, you will be prompted)")
        parser.add_argument("--email", dest="email", default="",
                            help="Optional email address")
        parser.add_argument("--role", dest="role", default="verifier",
                            choices=["verifier", "admin"],
                            help="Role: 'verifier' or 'admin' (BGV admin)")

    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"]
        role = options["role"]
        email = options["email"]

        if User.objects.filter(username=username).exists():
            raise CommandError(f"A user named '{username}' already exists.")

        user = User.objects.create_user(username=username, email=email, password=password)
        user.is_staff = False
        user.save()
        VerifierProfile.objects.create(user=user, role=role, is_active=True)

        self.stdout.write(self.style.SUCCESS(
            f"Created {role} account '{username}' — they can now log in at /bgv/staff/login/"
        ))