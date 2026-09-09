import json

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse, HttpResponseForbidden, HttpResponseBadRequest
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.models import JobApplication, Notification
from .models import (VerificationRequest, VerificationStep, VerifierProfile,
                   VerificationDocument, DigiLockerAccount)
from . import digilocker as dl
from django.utils import timezone
from .emails import send_upload_link_email
from .models import (
    VerificationDocument,
    ALLOWED_FILE_EXTENSIONS,
    MAX_DOCUMENT_BYTES,
)


# ---------- Role helpers ----------

def is_verifier_or_admin(user):
    return hasattr(user, "verifier_profile") and user.verifier_profile.is_active


def _employer_has_bgv_access(user):
    """BGV company views are plan-gated via SubscriptionPlan.includes_bgv_access."""
    sub = getattr(user, "subscription", None)
    if sub is None:
        return True  # legacy accounts without a subscription keep access
    return bool(sub.plan.includes_bgv_access)


def is_admin(user):
    return hasattr(user, "verifier_profile") and user.verifier_profile.role == "admin"


# ---------- Verifier / BGV staff login ----------

def verifier_login(request):
    """Login page for the background-verification team (verifiers + BGV admins)."""
    if request.user.is_authenticated and is_verifier_or_admin(request.user):
        return redirect("verification:verifier_dashboard")

    error = None
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)

        if user is None:
            error = "Invalid username or password."
        elif not is_verifier_or_admin(user):
            error = "This login is for verification staff only."
        else:
            login(request, user)
            return redirect("verification:verifier_dashboard")

    return render(request, "verification/verifier_login.html", {"error": error})


# ---------- Company-facing views ----------

@login_required
@require_POST
def request_bgv(request, application_id):
    """
    Manual trigger: company clicks 'Request BGV' next to a shortlisted candidate.
    Only the employer who posted the job can request this.
    """
    if not _employer_has_bgv_access(request.user):
        messages.warning(request, "Your plan does not include background verification. Upgrade to unlock BGV.")
        return redirect("subscription_plans")

    application = get_object_or_404(
        JobApplication, id=application_id, job__posted_by=request.user
    )

    if application.status != "shortlisted":
        return HttpResponseBadRequest("Candidate must be shortlisted before requesting BGV.")

    if hasattr(application, "verification_request"):
        return redirect("verification:company_bgv_status", application_id=application.id)

    bgv = VerificationRequest.objects.create(application=application, requested_by=request.user)
    for step_type, _label in VerificationStep.StepType.choices:
        method = (
            VerificationStep.Method.API
            if step_type == VerificationStep.StepType.IDENTITY
            else VerificationStep.Method.MANUAL
        )
        VerificationStep.objects.create(request=bgv, step_type=step_type, method=method)

    # Notify the candidate using your existing Notification model
    if application.job_seeker_profile:
        Notification.objects.create(
            user=application.job_seeker_profile.user,
            notification_type="general",
            message=f"{application.job.company_name or application.job.posted_by.username} has "
                    f"requested background verification. Please upload your documents.",
            link=f"/bgv/candidate/{bgv.id}/upload/",
        )

    return redirect("verification:company_bgv_status", application_id=application.id)


@login_required
def company_bgv_status(request, application_id):
    """Company sees a SUMMARY only - not raw documents - of a candidate's BGV."""
    if not _employer_has_bgv_access(request.user):
        messages.warning(request, "Your plan does not include background verification. Upgrade to unlock BGV.")
        return redirect("subscription_plans")

    bgv = get_object_or_404(
        VerificationRequest, application_id=application_id, application__job__posted_by=request.user
    )
    steps = bgv.steps.all().only("step_type", "status", "remarks", "verified_at")
    return render(request, "verification/company_status.html", {"bgv": bgv, "steps": steps})


@login_required
def company_bgv_overview(request):
    """Dedicated sidebar page: all BGV requests across all of this company's job postings."""
    if not _employer_has_bgv_access(request.user):
        messages.warning(request, "Your plan does not include background verification. Upgrade to unlock BGV.")
        return redirect("subscription_plans")

    status_filter = request.GET.get("status")
    base_qs = VerificationRequest.objects.filter(
        application__job__posted_by=request.user
    ).select_related("application", "application__job")

    qs = base_qs
    if status_filter in ("not_started", "in_progress", "passed", "failed"):
        qs = qs.filter(overall_status=status_filter)

    counts = {
        "all": base_qs.count(),
        "in_progress": base_qs.filter(overall_status="in_progress").count(),
        "passed": base_qs.filter(overall_status="passed").count(),
        "failed": base_qs.filter(overall_status="failed").count(),
    }

    return render(request, "verification/company_overview.html", {
        "bgv_requests": qs, "counts": counts, "active_filter": status_filter or "all",
    })


# ---------- Verifier dashboard ----------
@login_required(login_url="verification:verifier_login")
@user_passes_test(is_verifier_or_admin, login_url="verification:verifier_login")
def verifier_dashboard(request):
    profile = request.user.verifier_profile
    assigned = VerificationRequest.objects.filter(
        assigned_verifier=profile
    ).exclude(overall_status__in=[VerificationRequest.Status.PASSED, VerificationRequest.Status.FAILED])
    return render(request, "verification/verifier_dashboard.html", {"requests": assigned})


@login_required(login_url="verification:verifier_login")
@user_passes_test(is_verifier_or_admin, login_url="verification:verifier_login")
def verifier_step_detail(request, step_id):
    step = get_object_or_404(
        VerificationStep, id=step_id, request__assigned_verifier=request.user.verifier_profile
    )
    if request.method == "POST":
        new_status = request.POST.get("status")
        remarks = request.POST.get("remarks", "")
        if new_status not in dict(VerificationStep.Status.choices):
            return HttpResponseBadRequest("Invalid status")
        try:
            step.mark(new_status, actor=request.user.verifier_profile, remarks=remarks)
        except PermissionError as e:
            return HttpResponseForbidden(str(e))
        return redirect("verification:verifier_dashboard")
    return render(request, "verification/step_detail.html", {"step": step})


@login_required
@user_passes_test(is_verifier_or_admin)
@require_POST
def resend_upload_link(request, bgv_id):
    """Verifier/admin can (re)send the candidate the consent + upload link by email."""
    bgv = get_object_or_404(VerificationRequest, id=bgv_id)
    if send_upload_link_email(bgv):
        messages.success(request, f"Upload link emailed to {bgv.candidate_email}.")
    else:
        messages.error(
            request,
            "Could not send the email (no candidate email on file, or email backend failed).",
        )
    return redirect(request.META.get("HTTP_REFERER") or "verification:verifier_dashboard")


# ---------- Admin: assignment ----------

@login_required(login_url="verification:verifier_login")
@user_passes_test(is_admin, login_url="verification:verifier_login")
def admin_assignment_queue(request):
    unassigned = VerificationRequest.objects.filter(assigned_verifier__isnull=True)
    verifiers = VerifierProfile.objects.filter(role="verifier", is_active=True)
    return render(request, "verification/admin_queue.html", {
        "unassigned": unassigned, "verifiers": verifiers,
    })


@login_required(login_url="verification:verifier_login")
@user_passes_test(is_admin, login_url="verification:verifier_login")
@require_POST
def admin_assign_verifier(request, bgv_id):
    bgv = get_object_or_404(VerificationRequest, id=bgv_id)
    verifier_id = request.POST.get("verifier_id")
    verifier = get_object_or_404(VerifierProfile, id=verifier_id)
    bgv.assigned_verifier = verifier
    bgv.save(update_fields=["assigned_verifier", "updated_at"])
    return redirect("verification:admin_assignment_queue")


@login_required(login_url="/job-seeker-login/")
def candidate_upload(request, bgv_id):
    bgv = get_object_or_404(VerificationRequest, id=bgv_id)

    # Only the candidate this request belongs to may access it
    candidate_user = getattr(bgv.application.job_seeker_profile, "user", None)
    if candidate_user is None or candidate_user != request.user:
        return HttpResponseForbidden("You are not authorized to view this verification request.")

    if request.method == "POST":
        if "give_consent" in request.POST:
            bgv.candidate_consent_given = True
            bgv.candidate_consent_at = timezone.now()
            bgv.save(update_fields=["candidate_consent_given", "candidate_consent_at"])
            return redirect("verification:candidate_upload", bgv_id=bgv.id)

        elif "save_address" in request.POST:
            bgv.candidate_address = request.POST.get("candidate_address", "").strip()
            bgv.save(update_fields=["candidate_address", "updated_at"])
            messages.info(request, "Declared address saved.")
            return redirect("verification:candidate_upload", bgv_id=bgv.id)

        elif "save_education" in request.POST:
            bgv.candidate_education = request.POST.get("candidate_education", "").strip()
            bgv.save(update_fields=["candidate_education", "updated_at"])
            messages.info(request, "Declared education details saved.")
            return redirect("verification:candidate_upload", bgv_id=bgv.id)

        elif "save_employment" in request.POST:
            bgv.candidate_employment = request.POST.get("candidate_employment", "").strip()
            bgv.employment_is_fresher = "is_fresher" in request.POST
            bgv.save(update_fields=["candidate_employment", "employment_is_fresher", "updated_at"])
            messages.info(request, "Declared employment details saved.")
            return redirect("verification:candidate_upload", bgv_id=bgv.id)

        elif "save_identity" in request.POST:
            bgv.candidate_identity = request.POST.get("candidate_identity", "").strip()
            bgv.save(update_fields=["candidate_identity", "updated_at"])
            messages.info(request, "Declared identity details saved.")
            return redirect("verification:candidate_upload", bgv_id=bgv.id)

        elif "save_criminal" in request.POST:
            bgv.candidate_criminal = request.POST.get("candidate_criminal", "").strip()
            bgv.criminal_declares_clean = "declares_clean" in request.POST
            bgv.save(update_fields=["candidate_criminal", "criminal_declares_clean", "updated_at"])
            messages.info(request, "Criminal record declaration saved.")
            return redirect("verification:candidate_upload", bgv_id=bgv.id)

        elif "upload_step_id" in request.POST:
            step_id = request.POST.get("upload_step_id")
            step = get_object_or_404(VerificationStep, id=step_id, request=bgv)
            uploaded_file = request.FILES.get("document")
            if uploaded_file:
                allowed = dict(step.allowed_doc_types)
                doc_type = request.POST.get("doc_type", "document")
                ext = uploaded_file.name.rsplit(".", 1)[-1].lower() if "." in uploaded_file.name else ""

                if doc_type not in allowed:
                    messages.error(
                        request,
                        f"'{doc_type}' is not an accepted document type for "
                        f"{step.get_step_type_display()}. Choose one of the listed options.",
                    )
                elif ext not in ALLOWED_FILE_EXTENSIONS:
                    messages.error(request, "Only PDF, JPG or PNG files are accepted.")
                elif uploaded_file.size > MAX_DOCUMENT_BYTES:
                    messages.error(request, "Document must be 5MB or smaller.")
                else:
                    VerificationDocument.objects.create(
                        step=step, file=uploaded_file, uploaded_by=request.user, doc_type=doc_type
                    )
                    if step.status == VerificationStep.Status.PENDING:
                        step.status = VerificationStep.Status.IN_REVIEW
                        step.save(update_fields=["status", "updated_at"])
                    bgv.recalculate_overall_status()
            return redirect("verification:candidate_upload", bgv_id=bgv.id)

    steps = bgv.steps.all().prefetch_related("documents")
    return render(request, "verification/candidate_upload.html", {"bgv": bgv, "steps": steps})

# DigiLocker integration ---------------------------------------------------------------------
def _candidate_bgvs(user):
    return (VerificationRequest.objects
            .filter(application__job_seeker_profile__user=user)
            .order_by("-created_at"))


@login_required(login_url="/job-seeker-login/")
def digilocker_connect(request):
    """Start linking the candidate's DigiLocker account."""
    if hasattr(request.user, "digilocker_account"):
        return redirect("verification:digilocker_documents")

    if dl.demo_mode():
        return render(request, "verification/digilocker_demo.html", {"demo": True})

    import secrets
    state = secrets.token_urlsafe(16)
    request.session["digilocker_state"] = state
    return redirect(dl.build_authorize_url(state))


@login_required(login_url="/job-seeker-login/")
@require_POST
def digilocker_demo_confirm(request):
    """Demo mode: simulate a successful DigiLocker authorization (no network)."""
    if not dl.demo_mode():
        return HttpResponseBadRequest("Demo mode is disabled.")
    username = request.POST.get("username", "").strip() or f"{request.user.username}-demo"
    account, _created = DigiLockerAccount.objects.get_or_create(
        user=request.user,
        defaults={"digilocker_username": username, "is_demo": True},
    )
    dl.save_documents(account, dl.demo_issued_documents(username))
    messages.success(request, f"DigiLocker connected (demo) as '{username}'.")
    return redirect("verification:digilocker_documents")


def digilocker_callback(request):
    """OAuth2 redirect back from api.digilocker.gov.in (real mode)."""
    code = request.GET.get("code")
    state = request.GET.get("state")
    if not code or state != request.session.pop("digilocker_state", None):
        messages.error(request, "DigiLocker authorization failed or was cancelled.")
        return redirect("verification:digilocker_documents")
    try:
        token = dl.exchange_code(code)
        access_token = token.get("access_token", "")
        profile = dl.fetch_profile(access_token)
        docs = dl.fetch_issued_documents(access_token)
    except Exception:  # noqa: BLE001 - any network/API failure lands the user safely
        messages.error(request, "Could not reach DigiLocker just now. Please try again.")
        return redirect("verification:digilocker_documents")

    from django.utils import timezone as dj_tz
    from datetime import timedelta
    account, _created = DigiLockerAccount.objects.update_or_create(
        user=request.user,
        defaults={
            "digilocker_username": profile.get("username", request.user.username),
            "access_token": access_token,
            "refresh_token": token.get("refresh_token", ""),
            "token_expires_at": dj_tz.now() + timedelta(seconds=int(token.get("expires_in", 3600))),
            "is_demo": False,
        },
    )
    saved = dl.save_documents(account, docs)
    messages.success(request, f"DigiLocker connected. {len(saved)} document(s) found in your locker.")
    return redirect("verification:digilocker_documents")


@login_required(login_url="/job-seeker-login/")
def digilocker_documents(request):
    account = getattr(request.user, "digilocker_account", None)
    if account is None:
        return redirect("verification:digilocker_connect")
    bgv = _candidate_bgvs(request.user).first()
    steps = bgv.steps.all() if bgv else []
    return render(request, "verification/digilocker_documents.html", {
        "account": account,
        "documents": account.documents.all(),
        "bgv": bgv,
        "steps": steps,
    })


@login_required(login_url="/job-seeker-login/")
@require_POST
def digilocker_attach(request, doc_id):
    """Attach one DigiLocker document to a step of the candidate's BGV request."""
    from .models import DigiLockerDocument
    account = getattr(request.user, "digilocker_account", None)
    if account is None:
        return HttpResponseForbidden("Connect DigiLocker first.")
    doc = get_object_or_404(DigiLockerDocument, id=doc_id, account=account)
    step_id = request.POST.get("step_id")
    # Scope the step to a verification request that belongs to the logged-in
    # candidate, so a user can never attach a document to someone else's step.
    step = get_object_or_404(
        VerificationStep,
        id=step_id,
        request__application__job_seeker_profile__user=request.user,
    )
    bgv = step.request

    allowed = dict(step.allowed_doc_types)
    if doc.doc_type not in allowed:
        messages.error(
            request,
            f"'{doc.name}' is not accepted for {step.get_step_type_display()}. "
            "Attach it to a matching step instead.",
        )
        return redirect("verification:digilocker_documents")

    VerificationDocument.objects.create(
        step=step, doc_type=doc.doc_type, uploaded_by=request.user,
        source="digilocker", digilocker_document=doc,
    )
    if step.status == VerificationStep.Status.PENDING:
        step.status = VerificationStep.Status.IN_REVIEW
        step.save(update_fields=["status", "updated_at"])
    bgv.recalculate_overall_status()
    messages.success(request, f"'{doc.name}' attached to {step.get_step_type_display()} via DigiLocker.")
    return redirect("verification:digilocker_documents")
