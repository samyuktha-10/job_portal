<#
  check_local_copy.ps1
  Compares YOUR LOCAL Deploynix_Job_Portal folder against the 14 findings in
  AUDIT_2026-09-05.md (which was produced against github.com/samyuktha-10/job_portal @ eea21c7).

  Run from the project root (the folder that contains manage.py):
      cd C:\Users\Samyuktha\Downloads\Deploynix_Job_Portal\Deploynix_Job_Portal
      Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
      .\check_local_copy.ps1
#>

$ErrorActionPreference = 'SilentlyContinue'
$results = @()

function Add-Finding($id, $name, $ok, $detail) {
    $script:results += [pscustomobject]@{
        '#'      = $id
        Finding  = $name
        Status   = if ($ok) { 'FIXED' } else { 'STILL PRESENT' }
        Evidence = $detail
    }
}

if (-not (Test-Path 'manage.py')) {
    Write-Host "ERROR: manage.py not found. cd into the folder that contains manage.py first." -ForegroundColor Red
    exit 1
}

# --- 0. git repo? ---
$hasGit = Test-Path '.git'
Add-Finding 0 'Folder is a git repository' $hasGit `
    $(if ($hasGit) { '.git exists' } else { 'no .git - git fetch/branch/push cannot work here' })

# --- 1. notifications_list.html (audit 3.1) ---
$t = 'core\templates\core\notifications_list.html'
Add-Finding 1 'core/notifications_list.html exists' (Test-Path $t) `
    $(if (Test-Path $t) { $t } else { "missing -> /notifications/ returns 500" })

# --- 2. admin_inquiries_list.html (audit 3.2) ---
$t = 'core\templates\core\admin_panel\admin_inquiries_list.html'
Add-Finding 2 'core/admin_panel/admin_inquiries_list.html exists' (Test-Path $t) `
    $(if (Test-Path $t) { $t } else { "missing -> /control-panel/inquiries/ returns 500" })

# --- 3. verification/step_detail.html (audit 3.3) ---
$t = 'verification\templates\verification\step_detail.html'
Add-Finding 3 'verification/step_detail.html exists' (Test-Path $t) `
    $(if (Test-Path $t) { $t } else { "missing -> verifier cannot open a case (500)" })

# --- 4. verification/company_overview.html (audit 3.4) ---
$t = 'verification\templates\verification\company_overview.html'
Add-Finding 4 'verification/company_overview.html exists' (Test-Path $t) `
    $(if (Test-Path $t) { $t } else { "missing -> /bgv/company/overview/ returns 500" })

# --- 5. verifier_login route (audit 3.5) ---
$vu = Get-Content 'verification\urls.py' -Raw
$has = $vu -match 'staff/login/'
Add-Finding 5 'verification staff/login/ route' $has `
    $(if ($has) { 'route present' } else { "no route -> verifiers land on /admin/login/" })

# --- 6. audit log old_status (audit 3.6) ---
$vm = Get-Content 'verification\models.py' -Raw
$has = $vm -match 'old\s*=\s*self\.status'
Add-Finding 6 'audit log captures real old_status' $has `
    $(if ($has) { 'captures before value' } else { "old_status always equals new_status" })

# --- 7. requirements.txt encoding (audit 3.7) ---
$bytes = [System.IO.File]::ReadAllBytes((Resolve-Path 'requirements.txt'))
$isUtf16 = ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE)
$reqTxt = Get-Content 'requirements.txt' -Raw
$guarded = $reqTxt -match 'gunicorn[^\r\n]*sys_platform'
Add-Finding 7 'requirements.txt is plain ASCII/UTF-8' (-not $isUtf16) `
    $(if ($isUtf16) { "first bytes FF FE = UTF-16 -> pip cannot parse" } else { "first bytes $($bytes[0]) $($bytes[1])" })
Add-Finding '7b' 'gunicorn guarded for Windows' $guarded `
    $(if ($guarded) { 'sys_platform marker present' } else { 'gunicorn unguarded -> pip fails on Windows' })

# --- 8. SECRET_KEY default (audit 3.8) ---
$st = Get-Content 'deploynix\settings.py' -Raw
$has = $st -match "config\(\s*'SECRET_KEY'[^)]*default"
Add-Finding 8 'SECRET_KEY has a dev default' $has `
    $(if ($has) { 'default present' } else { "no default -> UndefinedValueError without .env" })

# --- 9. console email backend in DEBUG (audit 3.9) ---
$has = $st -match 'console\.EmailBackend'
Add-Finding 9 'console email backend when DEBUG' $has `
    $(if ($has) { 'console backend wired' } else { 'SMTP hard-wired -> signup blocked without creds' })

# --- 10. notification badge JSON key (audit 3.10) ---
$cv = Get-Content 'core\views.py' -Raw
$bb = Get-Content 'core\templates\core\base.html' -Raw
$viewKey = if ($cv -match "def unread_notification_count[\s\S]{0,400}?JsonResponse\(\{\s*'(\w+)'") { $Matches[1] } else { '?' }
$jsKey   = if ($bb -match 'data\.(\w+)') { $Matches[1] } else { '?' }
Add-Finding 10 'notification badge JSON keys match' ($viewKey -eq $jsKey) "view returns '$viewKey', js reads data.$jsKey"

# --- 11. candidate notified on shortlist (audit 3.11) ---
$sg = Get-Content 'verification\signals.py' -Raw
$todo = $sg -match 'TODO: send Notification'
Add-Finding 11 'candidate notified on shortlist' (-not $todo) `
    $(if ($todo) { 'signals.py still has the TODO' } else { 'TODO resolved' })

# --- 12. hardcoded WhatsApp token (audit 3.12) ---
$has = $st -match 'WHATSAPP_ACCESS_TOKEN\s*=\s*"EAAS'
Add-Finding 12 'WhatsApp token out of settings.py' (-not $has) `
    $(if ($has) { 'live token still hardcoded in settings.py' } else { 'moved to env/config' })

# --- 13. create_verifier management command (audit 3.14) ---
$t = 'verification\management\commands\create_verifier.py'
Add-Finding 13 'create_verifier command exists' (Test-Path $t) `
    $(if (Test-Path $t) { $t } else { 'missing -> unknown command' })

# --- 14. base.html footer block (audit 3.14) ---
$has = $bb -match '\{%\s*block\s+footer'
Add-Finding 14 'base.html has {% block footer %}' $has `
    $(if ($has) { 'block present' } else { 'footer is a hard include' })

# --- output ---
Write-Host ''
$results | Format-Table -AutoSize -Wrap
$bad = ($results | Where-Object { $_.Status -eq 'STILL PRESENT' }).Count
Write-Host ("{0} of {1} audit items still present in this local copy." -f $bad, $results.Count) -ForegroundColor Cyan

# --- live checks that need Django ---
Write-Host ''
Write-Host '--- Django system check ---' -ForegroundColor Yellow
python manage.py check 2>&1 | Select-Object -Last 5

Write-Host ''
Write-Host '--- Test suite (expect 8/9 if the stale signup test is unpatched) ---' -ForegroundColor Yellow
python manage.py test 2>&1 | Select-Object -Last 6
