from django.contrib import admin
from .models import (
    VerifierProfile, VerificationRequest, VerificationStep,
    VerificationDocument, VerificationAuditLog,
)


class StepInline(admin.TabularInline):
    model = VerificationStep
    extra = 0
    readonly_fields = ("created_at", "updated_at")


@admin.register(VerificationRequest)
class VerificationRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "candidate_name", "overall_status", "assigned_verifier", "created_at")
    list_filter = ("overall_status",)
    search_fields = ("application__full_name", "application__job_seeker_profile__full_name")
    inlines = [StepInline]
    readonly_fields = ("id", "created_at", "updated_at", "completed_at")


@admin.register(VerifierProfile)
class VerifierProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "is_active", "active_case_count")


@admin.register(VerificationDocument)
class VerificationDocumentAdmin(admin.ModelAdmin):
    list_display = ("step", "uploaded_by", "uploaded_at")


@admin.register(VerificationAuditLog)
class VerificationAuditLogAdmin(admin.ModelAdmin):
    list_display = ("request", "actor", "action", "old_status", "new_status", "timestamp")
    list_filter = ("action",)

    def has_change_permission(self, request, obj=None):
        return False  # immutable

    def has_delete_permission(self, request, obj=None):
        return False  # immutable