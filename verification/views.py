import json

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse, HttpResponseForbidden, HttpResponseBadRequest
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.models import JobApplication, Notification
from .models import VerificationRequest, VerificationStep, VerifierProfile
from django.utils import timezone
from .models import (
    VerificationDocument,
    ALLOWED_FILE_EXTENSIONS,
    MAX_DOCUMENT_BYTES,
)


# ---------- Role helpers ----------

def is_verifier_or_admin(user):
    return hasattr(user, "verifier_profile") and user.verifier_profile.is_active


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
    bgv = get_object_or_404(
        VerificationRequest, application_id=application_id, application__job__posted_by=request.user
    )
    steps = bgv.steps.all().only("step_type", "status", "remarks", "verified_at")
    return render(request, "verification/company_status.html", {"bgv": bgv, "steps": steps})


@login_required
def company_bgv_overview(request):
    """Dedicated sidebar page: all BGV requests across all of this company's job postings."""
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


@login_required
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