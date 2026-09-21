# Analysis: "Deploynix Job Portal — Complete Project Memory Capsule"

Analysed: 2026-09-21
Repo: `samyuktha-10/job_portal` @ `f0bbf89` (branch `arena/01a0c34a-job-portal`)
Method: every claim below was **executed or read against this checkout**, not inferred from the capsule.

Environment used: Python 3.11.2, Django 5.2.16, `DATABASE_URL=sqlite:///db.sqlite3`, `DEBUG=True`.

---

## 0. Bottom line

The capsule is a **good narrative overview but an unreliable reference**. Its architecture
story, role matrix and workflow diagrams are broadly right. Its **concrete details — URL
paths, model field names, choice values, and shell commands — are wrong often enough that
following it will break your work.**

Verified health of the tree itself (independent of the capsule):

| Check | Result |
|---|---|
| `manage.py check` | ✅ 0 issues |
| `manage.py migrate` | ✅ all migrations apply (core 3, verification 6, blog 2) |
| `manage.py loaddata datadump.json` | ✅ "Installed 74 object(s)" — capsule's count is **exactly right** |
| `manage.py seed_blog` | ✅ 13 posts, 3 authors |
| `manage.py test` | ✅ **134 tests, all pass** (165s) |
| `manage.py collectstatic` | ✅ 143 files, 128 post-processed |
| `manage.py runserver` | ✅ boots and serves |

So the code is in good shape. The problem is the **documentation**, and the capsule would
mislead a new contributor in ~30 places.

Accuracy scorecard by capsule section:

| Capsule section | Verdict |
|---|---|
| 1. Overview & architecture | 🟢 Mostly accurate |
| 2. Roles & permission matrix | 🟡 Right roles, **4 of 5 login routes wrong** |
| 3. Database schema | 🔴 **Seriously wrong** — invented fields, missing models |
| 4. Workflows | 🟢 Accurate (verified in code) |
| 5. Design system | 🟡 Half right — **FontAwesome is not used at all** |
| 6. URL directory | 🔴 **~60% of listed paths 404 or go somewhere else** |
| 7. Env vars | 🟢 Accurate |
| 8. Commands | 🟡 One documented command **fails verbatim** |

---

## 1. Errors that will actively break someone's work

### 1.1 A documented command does not run

Capsule §8 says:

```
python manage.py create_verifier --username verifier1 --password password123
```

Executed verbatim:

```
manage.py create_verifier: error: unrecognized arguments: --username
```

`username` is a **positional** argument (`verification/management/commands/create_verifier.py:10`).
Correct form, verified working:

```
python manage.py create_verifier verifier1 --password password123
# → Created verifier account 'verifier1' — they can now log in at /bgv/staff/login/
```

The command also supports `--role {verifier,admin}` and `--email`, which the capsule omits —
and `--role admin` is the only way to reach the BGV assignment queue.

### 1.2 The URL directory is wrong in both directions

Every path below was requested against a live server.

| Capsule claims | Actual | Live probe |
|---|---|---|
| `/jobs/` = "Job Vacancies search & filter" | `/jobs/` is the **employer's own listings** (`@employer_required`, filters `posted_by=request.user`) | `302` → employer login |
| *(not listed)* | **`/vacancies/`** is the real public job search | `200` |
| `/walkin-jobs/` | `/walk-in-jobs/` (hyphenated) | `/walkin-jobs/` → **`404`** |
| `/candidates/` | No such route. Real: `/candidates/new/`, `/candidates/manage/`, `/candidates/search/`, `/candidates/shortlisted/` | `/candidates/` → **`404`** |
| `/job-seeker/login/` | `/job-seeker-login/` | `200` at the real path |
| `/employer/login/` | `/employer-login/` | `200` at the real path |
| `/employer/dashboard/` | `/employer-dashboard/` | `302` (auth) |
| `/control-panel/employers/`, `/job-seekers/` | ✅ correct | `302` (auth) |
| `/bgv/staff/verifier/`, `/bgv/company/overview/`, `/bgv/candidate/upload/<id>/` | ✅ correct | `302` (auth) |

Two consequences beyond broken bookmarks:

- The capsule's **role table gives wrong login URLs for 4 of the 5 roles.** Only
  `/super-admin/login/` is correct. `LOGIN_URL = 'job_seeker_login'` (by *name*, so it still
  resolves), but anyone hardcoding the documented paths gets 404s.
- It implies `/jobs/` is public. It is not — it is employer-only. A newcomer wiring a public
  "browse jobs" link from this doc would produce a redirect loop to the employer login.

**Whole routes missing from the capsule:** password reset (4 routes), `verify-email/<uidb64>/<token>/`,
`resend-verification/`, `verify-signup-otp/`, `resend-signup-otp/`, `account-settings/`,
`delete-account/`, `notifications/`, `company-profile/`, `employer-reports/`, `employer-settings/`,
`job/<id>/edit/`, `job/<id>/save/`, `support/chat/`, `services/<slug>/`, `blog/search/`,
and all 6 DigiLocker routes (`/bgv/digilocker/connect|callback|documents|attach|demo-confirm/`),
plus the BGV admin queue (`/bgv/staff/admin/queue/`, `/bgv/staff/admin/assign/<uuid>/`) and
`/bgv/staff/resend/<uuid>/`.

Real counts: **74** routes in `core/urls.py`, **15** in `verification/urls.py`, **5** in `blog/urls.py`.

### 1.3 The schema section describes fields that do not exist

This is the most dangerous section, because it reads confidently and is used to write queries.

**`JobApplication.STATUS_CHOICES`** — capsule says 6 statuses:
`applied, reviewed, shortlisted, interviewed, rejected, hired`.
Actual (`core/models.py:88`) is **4**: `applied, shortlisted, rejected, hired`.
There is **no `reviewed` and no `interviewed`**. Any filter, migration or UI built on the
capsule's list will silently match nothing.

**`Interview`** — capsule says "interview_date, interview_time, mode, meeting_link".
Actual (`core/models.py:188`) has **none of those four**. The real model is:

```python
application  = ForeignKey(JobApplication, related_name='interviews')
scheduled_at = DateTimeField()          # one field, not date + time
status       = CharField(choices=[scheduled, hire, offer, reject, completed])
notes        = TextField()
```

Confirmed via `InterviewForm.Meta.fields = ['application', 'scheduled_at', 'status', 'notes']`.
It links to an **application**, not to "a candidate and employer". There is no meeting-link or
mode field anywhere — so no video-interview capability exists, contrary to the capsule.

**`EmployerSubscription`** — capsule says it "tracks ... Razorpay order_id / payment_id".
It does **not**. Real fields: `user, plan, started_at, expires_at, jobs_posted_count,
resumes_viewed_count`. No payment identifiers are persisted anywhere in the project
(`grep` for `order_id`/`payment_id` finds only the transient JSON response and the
signature-verification dict). See §2.2 — this is not just a doc error, it is the root of a
real payment bug.

**`Profile`** — capsule says "Employer profile". It is **dual-purpose for employers and job
seekers**, gated by `is_employer = BooleanField(default=False)` (the code comment says so
explicitly). There is **no `company_email` field** — it uses `user.email`. It also carries
`about, industry, company_size, founded_year, address, city, state, is_email_verified`,
none of which are mentioned. This matters because `employer_required` authorises on
`profile.is_employer`, so misreading `Profile` as employer-only leads to wrong permission logic.

**`JobSeekerProfile`** — capsule says "current role" and "profile photo". **Neither field
exists.** Real fields: `full_name, phone, whatsapp_opted_in, location, education, certificates,
skills, experience, preferred_job_type, is_experienced, resume, ats_score, is_email_verified`.
`completion_percentage` and `missing_fields` do exist ✅ but are **weighted**
(resume 25, skills 20, experience 15, education 15, location 10, preferred_job_type 10,
certificates 5), not a flat "filled fields" count.

**`SubscriptionPlan` tiers** — capsule says "Free, Silver, Gold, Platinum".
Actual seeded plans (`datadump.json`): **Free (₹0, 2 posts, 5 resumes), Basic (₹499, 10/50),
Premium (₹1499, 50/500)**. Also missing from the capsule: `includes_bgv_access`, which gates
whether an employer can see BGV status.

**`VerificationRequest`** — capsule says status lifecycle
`requested → documents_uploaded → in_progress → verified / rejected`.
Actual: `not_started → in_progress → passed / failed` (a `TextChoices` class). None of the
capsule's five values exist. It also links **OneToOne to `core.JobApplication`**, not to
"an employer and candidate" directly; the employer is derived via a `company_user` property
(`application.job.posted_by`). The segregation-of-duties field is `assigned_verifier`
(FK to `VerifierProfile`), not `assigned_to`, and it is enforced in `VerificationStep.mark()`.

**`VerificationAuditLog`** — capsule says it records "notes". There is no `notes` field; the
real ones are `action, old_status, new_status, ip_address, timestamp`. Immutability claim ✅
correct and genuinely enforced (`save()` raises if `pk` is set; `delete()` raises).

**Blog categories** — capsule says `career-guidance, interview-prep, resume-tips, salary,
industry-trends`. Actual (`blog/models.py`): `interview-questions, career-guidance,
job-application, resume-format, salary, internships, expert-edge`. **Only 2 of 5 capsule
categories are real**; 5 real ones are unlisted. Category slugs appear in URLs
(`/blog/category/<slug>/`), so the capsule's list generates 404s.

**"Markdown/HTML body"** — wrong, and the truth is a *security feature* worth not losing.
`BlogPost.content` is a **custom minimal markup** (`##` heading, `-` bullet, `>` quote,
`**bold**`) rendered by `blog/rendering.py`, which **escapes first, then wraps in tags**, so
stored content cannot inject HTML/JS. Treating it as Markdown/HTML (as the capsule instructs)
would invite someone to add a Markdown library with raw-HTML passthrough and reintroduce
stored XSS. `read_time` is also a computed property (200 wpm), not a stored field.

**Models the capsule never mentions:** `VerifierProfile` (role `verifier`/`admin`,
`active_case_count`), `DigiLockerAccount` (OAuth tokens, `is_demo`), `DigiLockerDocument`
(`doc_key`, `uri`, step mapping). Real totals: **22 project models** — 13 core, 7 verification,
2 blog. The capsule names ~15 and implies `verification` has 4.

---

## 2. Real defects the capsule obscures

These are live in the current tree. None are mentioned in the capsule, and in two cases the
capsule actively asserts the opposite.

### 2.1 🔴 Payment bypass — client-supplied `plan_id` is trusted (`core/views.py:1236`)

`verify_payment` verifies the Razorpay **signature** (proving a payment happened) but then
activates whatever `plan_id` arrived in the **request body**, with no binding to the order
that was actually paid:

```python
plan_id = data.get('plan_id')                       # ← attacker-controlled
razorpay_client.utility.verify_payment_signature(params_dict)   # proves *a* payment, not *this plan*
plan = SubscriptionPlan.objects.get(id=plan_id)
EmployerSubscription.objects.update_or_create(user=request.user, defaults={'plan': plan, ...})
```

`create_razorpay_order` does put `plan_id` in the order `notes`, but `verify_payment` never
fetches the order to compare. So: request an order for **Basic (₹499)**, pay it, then POST
`plan_id=<Premium>` with that valid signature → **Premium (₹1499) activated for ₹499**.

Two aggravating factors:

- **No payment status check.** The order is never fetched (`order.fetch()`) to confirm it is
  `paid`, so an unpaid/created order signature can be presented.
- **Replay.** Because `order_id`/`payment_id` are never persisted (the capsule wrongly says
  they are), there is no idempotency record. The same valid signature can be re-POSTed to
  renew the subscription and **reset `jobs_posted_count`/`resumes_viewed_count` to 0**
  indefinitely without paying again.

Minimum fix: persist `razorpay_order_id` + `razorpay_payment_id` (unique), fetch the order
server-side, assert `order['status'] == 'paid'`, `order['amount'] == plan.price * 100`, and
`order['notes']['plan_id'] == plan_id` — deriving the plan from the **order**, never from the
request body.

The free-plan branch in `create_razorpay_order` has the same reset side effect: any employer
can re-hit it to zero their counters and extend expiry by `duration_days`.

### 2.2 🟠 `{% block navbar %}` is silently discarded on BGV staff pages

`core/templates/core/base.html` declares only two blocks — `title` and `content`. It
**hard-includes** `core/navbar.html` and `core/footer.html`; there is **no `navbar` or
`footer` block**.

But `verification/templates/verification/verifier_dashboard.html:6` and `admin_queue.html`
both define `{% block navbar %}` containing a purpose-built dark BGV staff navbar. Django
drops child blocks that the parent never declares, so **that markup is dead**.

Probed by logging in as a `VerifierProfile(role='admin')` and fetching `/bgv/staff/verifier/`:

```
status 200
count of <nav> tags: 1
rendered <nav> → class="bg-black text-white ..." with "Job Vacancy", "Internships" links
```

Only **one** nav renders, and it is the **public marketing navbar**. (The `#030619` colour
does appear in the output, but from the page's content `<div>`, not from the nav.) Verifiers
and BGV admins therefore see candidate-facing shopping links instead of "My Cases /
Assignment Queue" — the navigation the template author wrote is invisible.

Note this **regressed**: `AUDIT_2026-09-05.md` §5 recorded "Only `navbar` exists". In the
current tree **neither** exists. Fix: add `{% block navbar %}{% include 'core/navbar.html' %}{% endblock %}`
(and the same for the footer) to `base.html`.

### 2.3 🟡 `Interview.__str__` renders blank for real applications

```python
return f"Interview: {self.application.full_name} - {self.scheduled_at.strftime('%d/%m/%Y')}"
```

`JobApplication.full_name` is only populated on the **walk-in/manual** path. For the normal
linked path (`job_seeker_profile` set) it is blank, so Django admin and any `str()` shows
`Interview:  - 21/09/2026`. The model already provides `display_full_name` for exactly this
dual-path case — it should be used here.

### 2.4 🟡 `DEBUG=True` skips super-admin OTP entirely

The capsule describes "Email + 6-digit terminal/console OTP". Reality (`core/views.py:1562`):

```python
if settings.DEBUG:
    # Local development convenience: skip the email OTP.
    login(request, user); return redirect(_sa_next(request))
```

In DEBUG there is **no second factor at all** — email + password logs straight in. Only when
`DEBUG=False` is a 6-digit OTP generated, and it is then sent by email **and** printed to
stdout (`print(f"[DEV] Super admin OTP ...")`). That print runs in production too, so OTPs
land in host log aggregation. The capsule's phrasing hides both the bypass and the leak.

### 2.5 🟡 Capsule claims FontAwesome; it is not used

`grep -rl "font-awesome\|fontawesome" --include=*.html .` → **0 matches**. Icons are inline
SVG plus Unicode glyphs (`✓`). Anyone following the capsule will add a FontAwesome CDN
dependency to a project that deliberately has none.

What *is* true: Tailwind CDN is loaded in exactly **2** files — `base.html` and
`dashboard_base.html` — and inherited by everything else (28 templates extend
`core/base.html`, 14 extend `core/dashboard_base.html`, 9 extend it with double quotes,
2 use `{% extends base_template %}`). Playfair Display ✅ (`base.html:11`, plus
`style.css` and 7 verification templates). `body { padding-top: 88px }` ✅
(`style.css:33`). `#notif-badge` polled every 30s ✅ (`base.html:45`, `setInterval(..., 30000)`),
and the JSON key matches on both ends (`{'count': ...}` ↔ `data.count`) — the endpoint is
correctly `@login_required` and only called inside `{% if user.is_authenticated %}`.

Also worth flagging: the BGV templates style themselves with **inline `style=` attributes**
and a navy `#030619` palette, not the documented Tailwind red/black system. The design-system
section describes the marketing pages, not the whole app.

---

## 3. What the capsule gets right (verified, not assumed)

Credit where due — these all check out against the code:

- **Job approval flow.** All four public listings filter `approval_status='approved'`:
  `home` (:104), `job_vacancies` (:132), `internships` (:1313), `walkin_jobs` (:1492).
  Default is `pending`. ✅ Exactly as described.
- **Resume unlock quota.** `unlock_resume` (:1026) is `@employer_required @require_POST`,
  checks job ownership, de-dupes via `ResumeUnlock`, enforces
  `subscription.can_view_resume()`, then increments `resumes_viewed_count`. ✅
- **Signup OTP is 10 minutes.** `timezone.now() + timedelta(minutes=10)` at :439 and on
  resend at :565. ✅ `JobSeekerSignupOTP` stores a pre-hashed password, never plaintext. ✅
- **BGV document hashing.** `VerificationDocument.save()` streams the file through SHA-256
  into `file_hash`. ✅ 5 fixed steps with `unique_together ('request','step_type')`. ✅
- **Segregation of duties.** `VerificationStep.mark()` raises `PermissionError` when
  `request.requested_by_id == actor.user_id`. ✅
- **DigiLocker dual mode.** `demo_mode()` returns True if `DIGILOCKER_DEMO_MODE` or no
  client ID; live path has `build_authorize_url` / `exchange_code` / `fetch_profile` /
  `fetch_issued_documents`. ✅
- **Storage fallback.** `USE_S3` flips `STORAGES['default']` to S3 only when all three AWS
  vars are set; otherwise local `FileSystemStorage`. ✅ WhiteNoise
  `CompressedStaticFilesStorage` for staticfiles. ✅
- **Email backend selection.** Explicit `EMAIL_BACKEND` > SMTP when creds present > console. ✅
- **Production hardening.** HSTS, secure cookies, `X_FRAME_OPTIONS='DENY'`, nosniff,
  `RENDER_EXTERNAL_HOSTNAME` handling, `CSRF_TRUSTED_ORIGINS`. ✅ All auto-derived from DEBUG.
- **`datadump.json` = 74 records.** ✅ Exact. (23 users, 14 seeker profiles, 10 applications,
  8 subscriptions, 6 profiles, 5 jobs, 3 sessions, 3 plans, 2 notifications.)
- **Blog safety-by-design.** Auto-unique slugs with numeric suffixes, gradient+emoji banners
  with no external image deps, `is_visible_to()` gating drafts to staff. ✅
- **Dependency set and env var list** match `requirements.txt` / `.env.example`. ✅

---

## 4. Things the capsule omits entirely

Beyond the models and routes listed above:

- **Management commands:** `seed_demo_data` (40 job seekers, 12 employers, 9 on paid plans,
  password `demo1234`), `seed_demo_users`, `seed_plans`. Only `seed_blog` and
  `create_verifier` are documented.
- **Test suite scale:** 134 tests across 6 files (verification 41, blog 28,
  core/tests_auth_extras 21, core/tests_smoke 21, core/tests 12, core/tests_chatbot 11).
  The capsule just says "run test suite".
- **`compute_ats_score_for_application`** (:1411) — scores an application against its actual
  job. The capsule only describes the public paste-a-JD checker at `/ats-checker/`, which
  compares a **pasted job description** against the resume (keyword-set intersection ÷ JD
  keywords), falling back to the profile resume when no file is uploaded, and errors clearly
  on scanned/image PDFs.
- **`AUDIT_2026-09-05.md`** — a 300-line prior audit already in the repo, and
  **`MERGE_SUMMARY.md`** + `Deploynix_Job_Portal_Blueprint.pdf`. The capsule never mentions
  them, yet the audit is the most accurate existing description of this tree.
- **Session policy:** `SESSION_EXPIRE_AT_BROWSER_CLOSE=True`, `SESSION_COOKIE_AGE=28800`
  (8h), with a 14-day "remember me" override in the super-admin flow.
- **`check_local_copy.ps1`**, `.editorconfig`, `404.html`/`500.html` handlers,
  `core/storage.py`, `core/chatbot.py`, `core/context_processors.py` (`support_contact`).

### Progress since the 2026-09-05 audit

Worth recording, because the capsule is silent on it and it changes the priority list.
The audit targeted commit `eea21c7`; the current `f0bbf89` has **fixed** most of it:

| Audit finding | Now |
|---|---|
| 3.7 `requirements.txt` UTF-16, unparsable | ✅ plain UTF-8, gunicorn guarded `sys_platform != "win32"` |
| 3.5 no verifier login route/view | ✅ `/bgv/staff/login/` + `verifier_login` + template |
| 3.3 missing `step_detail.html` (500) | ✅ present |
| 3.6 audit log `old_status == new_status` | ✅ `old_status` captured before mutation |
| 3.10 badge never updates (JSON key mismatch) | ✅ `count` on both ends |
| 3.11 candidate not notified on status change | ✅ `create_notification` in `update_application_status` |
| 3.12 live WhatsApp token committed | ✅ no token in tree; env-only |
| 3.9 signup blocked without SMTP | ✅ console-backend fallback |
| README truncated (steps 1–4 missing) | ✅ full README |
| `create_verifier` command absent | ✅ present (but documented wrongly — §1.1) |
| 3.8 `SECRET_KEY` no default | ⚠️ **still** `config('SECRET_KEY')` — app won't boot without `.env` |
| SQLite fallback when `DATABASE_URL` empty | ⚠️ **still** falls back to PostgreSQL |
| `base.html` navbar/footer blocks | 🔴 **regressed** — neither exists now (§2.2) |

Still open and not covered by either document: **§2.1 payment bypass** and **§2.3 `Interview.__str__`**.

---

## 5. Suggested order of work

1. **Fix the payment flow (§2.1)** — server-side derive the plan from the fetched order,
   assert amount + `paid` status, persist `order_id`/`payment_id` with a unique constraint
   for idempotency. This is the only finding with direct financial impact.
2. **Add `navbar`/`footer` blocks to `base.html` (§2.2)** — one-line-each fix that restores
   the BGV staff navigation someone already wrote.
3. **Correct the capsule before it is used as reference again** — the URL table (§1.2), the
   schema section (§1.3), and the `create_verifier` command (§1.1). Cheapest way: regenerate
   §6 from `core/urls.py` / `verification/urls.py` / `blog/urls.py`, and §3 from
   `manage.py inspectdb`-style introspection of the 22 real models.
4. **Guard the free-plan reset** (§2.1 tail) and **remove the production OTP `print`** (§2.4).
5. Small: `Interview.__str__` → `display_full_name` (§2.3); consider a `SECRET_KEY` dev
   default and SQLite fallback so the app boots without a `.env`.
