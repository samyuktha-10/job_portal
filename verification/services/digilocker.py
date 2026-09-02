"""
Step 1 - Identity Verification via DigiLocker.
Instant, synchronous, government-backed. Candidate authenticates directly
with DigiLocker (OTP) and consents to share Aadhaar/PAN data with us.
We never store the raw Aadhaar number - only the verified confirmation payload.
"""
import requests
from django.conf import settings


class DigiLockerService:
    BASE_URL = "https://api.<your-chosen-vendor>.com/v1"  # e.g. Surepass / Cashfree / IDSPay

    def __init__(self):
        self.api_key = settings.DIGILOCKER_API_KEY

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def create_consent_url(self, candidate_id: str, redirect_url: str) -> str:
        """
        Step A: generate the DigiLocker redirect URL the candidate is sent to.
        Candidate logs in with Aadhaar + OTP there, not on our site.
        """
        resp = requests.post(
            f"{self.BASE_URL}/digilocker/initiate",
            headers=self._headers(),
            json={"client_ref_id": candidate_id, "redirect_url": redirect_url},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["redirect_url"]

    def fetch_verified_identity(self, client_ref_id: str) -> dict:
        """
        Step B: after candidate completes DigiLocker consent flow and is
        redirected back, call this to fetch the verified, structured data.

        Returns e.g.:
        {
            "verified": True,
            "name": "Samyuktha ...",
            "dob": "1999-01-01",
            "address": "...",
            "photo_base64": "...",
            "aadhaar_last4": "1234",
        }
        """
        resp = requests.get(
            f"{self.BASE_URL}/digilocker/fetch",
            headers=self._headers(),
            params={"client_ref_id": client_ref_id},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()


def process_identity_step(step, client_ref_id):
    """Called from a view/task once the candidate completes DigiLocker consent."""
    from ..models import VerificationStep  # local import to avoid circulars

    service = DigiLockerService()
    data = service.fetch_verified_identity(client_ref_id)

    step.raw_api_response = data
    step.external_reference_id = client_ref_id

    if data.get("verified"):
        step.status = VerificationStep.Status.VERIFIED
        step.remarks = "Auto-verified via DigiLocker (government-issued Aadhaar/PAN match)."
    else:
        step.status = VerificationStep.Status.REJECTED
        step.remarks = "DigiLocker verification failed or was not consented to."

    step.method = VerificationStep.Method.API
    step.save()
    step.request.recalculate_overall_status()
    return step
