# Deploynix — Job Portal

A complete, user-friendly job portal built with **Django 5.2**.
This is the **merged** project: two developers' codebases combined into one,
keeping the best feature from each. See `MERGE_SUMMARY.md` for the full merge report
and `Deploynix_Job_Portal_Blueprint.pdf` for the complete project blueprint.

## Features at a glance

- **Job Seekers** — email-OTP signup, profile with completeness %, WhatsApp opt-in,
  job search (vacancies / internships / walk-in), one-click apply, My Applications
  timeline, saved jobs, ATS resume checker, notifications, account deletion.
- **Employers** — login by company email, dashboard, post/edit/delete jobs in 5 types,
  candidate management + resume search, interview scheduling, walk-in candidates,
  company profile, Razorpay subscription plans, resume unlock, reports.
- **Super Admin** — email + OTP login, control panel with job approval workflow,
  employer / job-seeker / subscription / plan / inquiry management.
- **Background Verification (BGV)** — dedicated `verification` app with a 5-step
  workflow (identity, education, employment, address, criminal), verifier dashboard,
  DigiLocker stub, and an immutable audit log.

---

## 1) Open the project in VS Code

1. **Extract** the zip (if you haven't already) — right-click → *Extract All* on Windows.
2. Open **VS Code** → **File → Open Folder…** → select the `Deploynix_Job_Portal` folder.
3. Open the terminal: **Ctrl + `` ` ``** (backtick).

The folder already includes a `.vscode` setup with:
- **F5** = run the Django dev server (with debugger)
- **Run ▸ Django: tests** = run the test suite
- Recommended extensions (Python, Pylance, Django) — accept the prompt when it appears

---

## 2) Create a virtual environment

**Windows (PowerShell):**
```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

**Mac / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

In VS Code, press **Ctrl+Shift+P** → *Python: Select Interpreter* → choose
`venv\Scripts\python.exe` (Windows) or `venv/bin/python` (Mac/Linux).

---

## 3) Install dependencies

```bash
pip install -r requirements.txt
```

---

## 4) Configure environment variables

Copy the example file to your own `.env`:

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
```

Then edit `.env` and set at least:
```
SECRET_KEY=any-long-random-string
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=            # leave empty to use SQLite for local dev
```
> ⚠️ Leave `DATABASE_URL` empty for a zero-setup local database (SQLite).
> PostgreSQL is only needed for production.

---

## 5) Set up the database & sample data

```bash
python manage.py migrate
python manage.py loaddata datadump.json
```

Create a **super admin** account (for the admin control panel):
```bash
python manage.py createsuperuser
```

---

## 6) Run the server

```bash
python manage.py runserver
```

or just press **F5** in VS Code (the launch config already sets the dev env vars).

Open **http://127.0.0.1:8000/** in your browser.

| Page | URL |
|---|---|
| Public home | http://127.0.0.1:8000/ |
| Super admin login | http://127.0.0.1:8000/super-admin/login/ |
| Admin control panel | http://127.0.0.1:8000/control-panel/ |
| Verifier dashboard | http://127.0.0.1:8000/bgv/staff/verifier/ |
| Django built-in admin | http://127.0.0.1:8000/admin/ |

---

## 7) Running the tests

```bash
python manage.py test
```

(or use the **Run ▸ Django: tests** configuration in VS Code)

---

## Project structure

```
Deploynix_Job_Portal/
├── deploynix/            # project settings & root URLs
├── core/                 # main app — models, views, forms, templates, admin panel
│   └── whatsapp/         # WhatsApp Business API client
├── verification/         # background-verification app (BGV)
├── core/templates/core/  # all HTML pages
├── core/static/core/     # CSS + images
├── datadump.json         # sample data (jobs, users, plans)
├── requirements.txt      # Python dependencies
├── build.sh              # Render build script
├── manage.py
├── .env.example          # documented environment variables
├── .vscode/              # VS Code launch + settings + extension recommendations
├── MERGE_SUMMARY.md      # what was merged and how
└── Deploynix_Job_Portal_Blueprint.pdf   # full project blueprint
```

---

## Deploying

The project is pre-configured for **Render** (see `build.sh`). Push this folder to a
GitHub repo, create a Web Service on Render, and use:

- **Build command:** `./build.sh`
- **Start command:** `gunicorn deploynix.wsgi:application`

Free alternatives: **PythonAnywhere** or **Railway**.
Full steps are in `MERGE_SUMMARY.md`.

---

## Need help?

- Run `python manage.py check` to verify your setup.
- The full feature list, page directory and database schema are in
  **Deploynix_Job_Portal_Blueprint.pdf**.
