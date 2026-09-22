"""Fill the portal with realistic demo employers and job seekers so the
Control Panel lists look populated ("huge").

Creates:
  - 40 job seekers (full profiles: name, phone, city, education, skills)
  - 12 employer companies, of which 9 are on PAID plans (5 Premium, 4 Basic;
    2 of the paid ones are expired so both badges show) and 3 on Free
  - The Free/Basic/Premium plans if missing

Idempotent: everything is keyed by username, re-running updates instead of
duplicating. All demo accounts use password: demo1234

Usage:  python manage.py seed_demo_data [--seekers 40 --employers 12]
"""
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify

from core.models import (
    EmployerSubscription, JobSeekerProfile, Profile, SubscriptionPlan,
)

SEEKER_PASSWORD = "demo1234"
EMPLOYER_PASSWORD = "demo1234"

FIRST = ["Anita", "Rahul", "Priyanka", "Vikram", "Sneha", "Arjun", "Divya",
         "Karthik", "Meera", "Sanjay", "Lakshmi", "Rohit", "Pooja", "Aditya",
         "Kavya", "Manish", "Deepa", "Suresh", "Nisha", "Varun", "Anjali",
         "Harish", "Swati", "Nikhil", "Revathi", "Ashok", "Janani", "Prakash",
         "Shalini", "Ganesh", "Ramya", "Vivek", "Ishita", "Mohan", "Aparna",
         "Rajesh", "Sunita", "Dinesh", "Farhan", "Ayesha", "Joseph", "Mary",
         "Imran", "Fatima", "Gurpreet", "Simran", "Amit", "Neha", "Rakesh", "Sita"]

LAST = ["Sharma", "Iyer", "Reddy", "Patel", "Nair", "Gupta", "Kumar", "Menon",
        "Rao", "Choudhary", "Verma", "Das", "Mukherjee", "Singh", "Khan",
        "Thomas", "George", "Pillai", "Naidu", "Joshi", "Mehta", "Shah",
        "Bose", "Kapoor", "Malhotra", "Bhat", "Kulkarni", "Deshpande",
        "Chopra", "Saxena"]

CITIES = ["Chennai", "Bengaluru", "Hyderabad", "Coimbatore", "Mumbai", "Pune",
          "Delhi", "Kochi", "Madurai", "Trichy", "Vellore", "Salem",
          "Gurgaon", "Noida", "Ahmedabad", "Kolkata", "Jaipur", "Lucknow",
          "Indore", "Chandigarh"]

EDUCATION = ["B.E. Computer Science", "B.Tech Information Technology",
             "B.Sc. Data Science", "MBA Marketing", "B.Com Finance",
             "MCA", "B.E. Mechanical Engineering", "B.A. English",
             "M.Sc. Mathematics", "BCA"]

SKILLS = ["Python, Django, SQL", "Java, Spring Boot, MySQL",
          "React, JavaScript, CSS", "Excel, Power BI, SQL",
          "Digital Marketing, SEO", "Tally, GST, Accounting",
          "AutoCAD, SolidWorks", "Communication, MS Office",
          "AWS, Docker, Linux", "Figma, UI/UX Design"]

JOB_TYPES = ["full-time", "part-time", "internship", "remote"]

COMPANIES = [
    ("Zenith Softworks", "IT Services"),
    ("Kaveri Technologies", "Software Product"),
    ("BlueLotus IT Services", "IT Services"),
    ("Arjun Systems", "Hardware & Networking"),
    ("Veda Analytics", "Data & Analytics"),
    ("GreenLeaf BPO", "BPO / KPO"),
    ("Sunrise Manufacturing", "Manufacturing"),
    ("Chola Fintech", "Fintech"),
    ("Nilgiri Retail Group", "Retail"),
    ("Agni Aerospace Labs", "Aerospace"),
    ("Mango Digital Media", "Digital Media"),
    ("Temple City Healthcare", "Healthcare"),
]

PLANS = [
    {'name': 'Free', 'price': 0, 'duration_days': 30, 'job_post_limit': 2, 'resume_view_limit': 5},
    {'name': 'Basic', 'price': 499, 'duration_days': 30, 'job_post_limit': 10, 'resume_view_limit': 50},
    {'name': 'Premium', 'price': 1499, 'duration_days': 30, 'job_post_limit': 50, 'resume_view_limit': 500},
]


def _ensure_plans():
    by_name = {}
    for p in PLANS:
        obj, _ = SubscriptionPlan.objects.update_or_create(name=p['name'], defaults=p)
        by_name[p['name']] = obj
    return by_name


class Command(BaseCommand):
    help = "Seed lots of demo employers and job seekers so admin pages look populated."

    def add_arguments(self, parser):
        parser.add_argument("--seekers", type=int, default=40)
        parser.add_argument("--employers", type=int, default=12)

    def handle(self, *args, **options):
        n_seekers = max(1, min(options["seekers"], 200))
        n_employers = max(1, min(options["employers"], len(COMPANIES)))
        now = timezone.now()

        # ---- Job seekers --------------------------------------------------
        for i in range(1, n_seekers + 1):
            first = FIRST[i % len(FIRST)]
            last = LAST[(i * 7) % len(LAST)]
            username = "%s.%s%d" % (first.lower(), last.lower(), i)
            email = "%s@deploynix.local" % username
            user, _ = User.objects.update_or_create(
                username=username,
                defaults={"email": email, "is_staff": False, "is_superuser": False},
            )
            user.set_password(SEEKER_PASSWORD)
            user.save()
            JobSeekerProfile.objects.update_or_create(
                user=user,
                defaults={
                    "full_name": "%s %s" % (first, last),
                    "phone": "9%09d" % (100000000 + i * 137),
                    "location": CITIES[i % len(CITIES)],
                    "education": EDUCATION[i % len(EDUCATION)],
                    "skills": SKILLS[i % len(SKILLS)],
                    "preferred_job_type": JOB_TYPES[i % len(JOB_TYPES)],
                    "is_experienced": (i % 3 != 0),
                    "experience": "%d years" % (i % 6) if i % 3 != 0 else "",
                    "whatsapp_opted_in": True,
                },
            )

        # ---- Employers ------------------------------------------------------
        plans = _ensure_plans()
        paid_created = 0
        for i in range(n_employers):
            company, industry = COMPANIES[i]
            slug = slugify(company)
            email = "hr@%s.in" % slug.replace("-", "")
            user, _ = User.objects.update_or_create(
                username=slug,
                defaults={"email": email, "is_staff": False, "is_superuser": False},
            )
            user.set_password(EMPLOYER_PASSWORD)
            user.save()
            Profile.objects.update_or_create(
                user=user,
                defaults={"is_employer": True, "company_name": company,
                          "phone": "8%09d" % (200000000 + i * 511),
                          "company_id": "U72900MH2021PTC%06d" % (200000 + i),
                          "trust_status": "verified"},
            )

            # Plan assignment: first 5 Premium, next 4 Basic, rest Free.
            if i < 5:
                plan = plans["Premium"]
                expires = now + timezone.timedelta(days=20 - i)
            elif i < 9:
                plan = plans["Basic"]
                # Two expired paid members so the admin page shows both states.
                expires = now + timezone.timedelta(days=25 if i < 7 else -5)
            else:
                plan = plans["Free"]
                expires = now + timezone.timedelta(days=30)

            sub, created = EmployerSubscription.objects.update_or_create(
                user=user,
                defaults={"plan": plan, "expires_at": expires},
            )
            if plan.price > 0:
                paid_created += 1

        self.stdout.write(self.style.SUCCESS(
            "Demo data ready: %d job seekers, %d employers (%d on paid plans). "
            "Password for all demo accounts: %s"
            % (n_seekers, n_employers, paid_created, SEEKER_PASSWORD)))
