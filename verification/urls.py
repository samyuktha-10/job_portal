from django.urls import path
from . import views

app_name = "verification"

urlpatterns = [
    # Company
    path("company/overview/", views.company_bgv_overview, name="company_bgv_overview"),
    path("company/application/<int:application_id>/status/", views.company_bgv_status, name="company_bgv_status"),
    path("company/application/<int:application_id>/request/", views.request_bgv, name="request_bgv"),

    # Verifier
    path("staff/login/", views.verifier_login, name="verifier_login"),
    path("staff/verifier/", views.verifier_dashboard, name="verifier_dashboard"),
    path("staff/verifier/step/<int:step_id>/", views.verifier_step_detail, name="verifier_step_detail"),

    # Admin
    path("staff/admin/queue/", views.admin_assignment_queue, name="admin_assignment_queue"),
    path("staff/admin/assign/<uuid:bgv_id>/", views.admin_assign_verifier, name="admin_assign_verifier"),
    path("candidate/<uuid:bgv_id>/upload/", views.candidate_upload, name="candidate_upload"),
]