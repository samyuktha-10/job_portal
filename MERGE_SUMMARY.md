# Deploynix Job Portal — Merged Project Summary

Two versions of the same Django job-portal project were merged into **one combined
codebase** that includes every feature from both. This file explains what was merged,
the decisions taken, and how to run/deploy it.

---

## What each person built

| | Friend (Devisanjai/job-portal-) | You (samyuktha-10/job_portal) |
|---|---|---|
| **Job approval** | `approval_status` (pending/approved/rejected) + admin approval workflow | `is_approved` boolean (simpler) |
| **Admin panel** | OTP admin login + dashboard, jobs/users/inquiries management | OTP super-admin login + rich control panel + employer/job-seeker/subscription/plan lists |
| **Background verification** | Built inside the `core` app (documents per profile, criminal-check flag, verifier role) | A dedicated `verification` app (5-step workflow, DigiLocker, audit log, verifier dashboard) |
| **WhatsApp alerts** | — | `whatsapp_opted_in` field + `core/whatsapp/client.py` |
| **Application source** | — | `source` field on applications |
| **Profile completion** | — | `completion_percentage` + `missing_fields` |

The two repos share a common history and then diverged. This merge keeps the best
of both and removes duplicate systems.

---

## Merge decisions (what was combined, and how)

### Kept from the friend's repo (the base)
- Job **approval workflow** (`approval_status` with pending/approved/rejected) — this is
  richer than a boolean, and the admin "Approve / Reject / Mark Pending / Delete" job list
  was rebuilt around it.
- Employer login **slug usernames** (`_generate_employer_username`) — cleaner than using
  the raw email as the username.
- Walk-in jobs, employer reports, employer settings (password change), job edit
  (re-submits for approval), ATS resume checker, subscriptions/Razorpay, resume unlock,
  saved jobs, notifications, email verification, password reset, signup OTP.
- `includes_bgv_access` on subscription plans (kept as a plan field).
- `is_experienced` on job-seeker profiles.

### Kept from your repo
- The entire **`verification` app** — this is the one, unified background-verification
  system (the friend's in-`core` verification was removed to avoid two competing systems).
  It provides:
  - 5 verification steps (identity, education, employment, address, criminal)
  - DigiLocker integration stub (`verification/services/digilocker.py`)
  - Immutable audit log, per-step documents with SHA-256 hashing, segregation of duties
  - Company overview/status pages, verifier dashboard, admin assignment queue, candidate upload
- **WhatsApp** opt-in field + API client (`core/whatsapp/client.py`).
- **`source`** field on job applications (website / LinkedIn / other).
- **Profile completion** bar (`completion_percentage`, `missing_fields`).
- **Super-admin panel**: `control_panel` dashboard + employer / job-seeker / subscription /
  plan / inquiry lists (all unified under `/control-panel/`).

### Unified (one system instead of two)
- **One admin login** → `/super-admin/login/` (email + OTP) → `/control-panel/`.
- **One background-verification system** → the `verification` app, mounted at `/bgv/`.
  The "Request Background Verification" button on a candidate's page now posts to
  `verification:request_bgv` and the status links to `verification:company_bgv_status`.
- **One job-approval flow** → `approval_status` everywhere (homepage & vacancies only show
  `approved` jobs; new posts default to `pending` until an admin approves them).

### Fixes applied while merging
- `VerificationStep.mark()` now records the correct `old_status` in the audit log.
- `VerificationDocument.save()` computes the SHA-256 file hash.
- `company_bgv_overview` status-filter counting was corrected.
- Two missing templates were created: `verification/company_overview.html` and
  `verification/step_detail.html`.
- Stale tests (written against an old pre-OTP login flow) were updated; **all 9 tests pass**.
- A committed WhatsApp access token was removed from settings (now read from env vars) —
  **rotate that token**, since it was public in a GitHub repo.
- Sample data (`datadump.json`) was patched so seeded jobs load as `approved`.

---

## Project layout (merged)

```
Deploynix_Job_Portal/
├── deploynix/            # settings (now includes 'verification' app + WhatsApp/DigiLocker)
├── core/                 # main app (merged models, views, forms, admin panel, templates)
│   └── whatsapp/         # WhatsApp Business API client
├── verification/         # background verification app (from your repo)
│   ├── models.py         # VerificationRequest / VerificationStep / Document / AuditLog / VerifierProfile
│   ├── views.py          # company + verifier + admin BGV views
│   ├── urls.py           # mounted at /bgv/
│   └── services/digilocker.py
├── datadump.json         # sample data (jobs, users, plans)
├── build.sh              # Render build script
├── manage.py
├── requirements.txt
├── .env.example          # all environment variables documented
└── MERGE_SUMMARY.md      # this file
```

---

## How to run locally

```bash
# 1. create + activate a virtualenv
python -m venv venv
venv\Scripts\activate        # Windows

# 2. install dependencies
pip install -r requirements.txt

# 3. set environment variables (copy .env.example to .env and fill in)
#    Windows PowerShell:
$env:SECRET_KEY="dev-key"; $env:DEBUG="True"
$env:DATABASE_URL="sqlite:///db.sqlite3"
$env:ALLOWED_HOSTS="*"

# 4. create tables + load sample data
python manage.py migrate
python manage.py loaddata datadump.json

# 5. create a superuser (for the admin panel) + a verifier (optional)
python manage.py createsuperuser

# 6. run
python manage.py runserver
```

Visit:
- Public site: `http://127.0.0.1:8000/`
- Admin panel: `http://127.0.0.1:8000/super-admin/login/`
- Django admin: `http://127.0.0.1:8000/admin/`

---

## How to host it

The repo is already set up for **Render** (has `build.sh`, `dj-database-url`, WhiteNoise).

1. Push this folder to a GitHub repo.
2. On Render → **New → Web Service** → connect the repo.
   - Build command: `./build.sh`
   - Start command: `gunicorn deploynix.wsgi:application`
3. Add environment variables (see `.env.example`): `SECRET_KEY`, `DATABASE_URL`
   (Render provides one automatically), `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`,
   `RAZORPAY_*`, `WHATSAPP_*`, `DIGILOCKER_API_KEY`.

Free alternatives: **PythonAnywhere** (Bash console → `pip install -r requirements.txt`,
`python manage.py migrate`, `loaddata`, set up the WSGI file) or **Railway**.

---

## Notes / next steps you may want

- **DigiLocker**: `verification/services/digilocker.py` uses a placeholder vendor URL.
  Replace `BASE_URL` and set `DIGILOCKER_API_KEY` to wire it to a real provider
  (Surepass / Cashfree / IDSPay).
- **WhatsApp**: the client is ready; add your Meta WhatsApp Business API credentials
  and an approved template name to start sending alerts.
- **Subscription gating**: `SUBSCRIPTION_ENABLED = True` in `deploynix/settings.py`
  (set to `False` to disable paid plans while developing).
