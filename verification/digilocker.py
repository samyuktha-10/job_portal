"""
DigiLocker integration helpers.

Real mode (DIGILOCKER_CLIENT_ID + DIGILOCKER_CLIENT_SECRET set, DIGILOCKER_DEMO_MODE=False):
    OAuth2 authorization-code flow against api.digilocker.gov.in, then the
    "issued documents" API is queried for each supported document type.

Demo mode (default, no credentials needed):
    A built-in simulator returns a realistic set of issued documents so the
    whole flow can be demonstrated locally.
"""
from django.conf import settings

AUTH_URL = "https://api.digilocker.gov.in/oauth2/authorize"
TOKEN_URL = "https://api.digilocker.gov.in/oauth2/token"
PROFILE_URL = "https://api.digilocker.gov.in/1.3/details/profile"
ISSUED_DOC_URL = "https://api.digilocker.gov.in/1.3/details/issued/doc"

# DigiLocker doc type -> (our step_type, our doc_type, display name)
DOCTYPE_MAP = {
    "ADHCRD": ("identity", "aadhaar", "Aadhaar Card"),
    "PANCARD": ("identity", "pan_card", "PAN Card"),
    "DRVLI": ("identity", "driving_license", "Driving Licence"),
    "HSMARK": ("education", "marksheet", "Class XII Marksheet"),
    "DEGREE": ("education", "degree_certificate", "Degree Certificate"),
}


def demo_mode():
    """Demo mode when explicitly enabled or when no real credentials exist."""
    return bool(getattr(settings, "DIGILOCKER_DEMO_MODE", True)) or not settings.DIGILOCKER_CLIENT_ID


def redirect_uri():
    return f"{settings.SITE_URL.rstrip('/')}/bgv/digilocker/callback/"


def build_authorize_url(state):
    from urllib.parse import urlencode
    params = {
        "response_type": "code",
        "client_id": settings.DIGILOCKER_CLIENT_ID,
        "redirect_uri": redirect_uri(),
        "state": state,
        "scope": "profile issued_docs",
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code(code):
    """Trade the authorization code for an access token (real DigiLocker)."""
    import requests
    resp = requests.post(TOKEN_URL, data={
        "grant_type": "authorization_code",
        "code": code,
        "client_id": settings.DIGILOCKER_CLIENT_ID,
        "client_secret": settings.DIGILOCKER_CLIENT_SECRET,
        "redirect_uri": redirect_uri(),
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_profile(access_token):
    import requests
    resp = requests.get(PROFILE_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_issued_documents(access_token):
    """Query the issued-documents API for each supported doc type. Returns a
    list of dicts: {doc_key, name, issued_date, uri}."""
    import requests
    docs = []
    for doc_key, (_step, _dt, display) in DOCTYPE_MAP.items():
        try:
            resp = requests.get(
                ISSUED_DOC_URL,
                params={"type": doc_key, "format": "json"},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=15,
            )
            if resp.status_code != 200:
                continue  # user does not have this document in their locker
            payload = resp.json()
            entries = payload.get("documents", payload if isinstance(payload, list) else [])
            for entry in entries:
                docs.append({
                    "doc_key": doc_key,
                    "name": entry.get("name", display),
                    "issued_date": str(entry.get("date", "")),
                    "uri": str(entry.get("uri", "")),
                })
        except (requests.RequestException, ValueError):
            continue
    return docs


def demo_issued_documents(username):
    """Simulated locker contents — no network calls."""
    return [
        {"doc_key": "ADHCRD", "name": "Aadhaar Card", "issued_date": "2019-03-14",
         "uri": f"demo://digilocker/{username}/ADHCRD"},
        {"doc_key": "PANCARD", "name": "PAN Card", "issued_date": "2020-01-02",
         "uri": f"demo://digilocker/{username}/PANCARD"},
        {"doc_key": "DRVLI", "name": "Driving Licence", "issued_date": "2022-07-21",
         "uri": f"demo://digilocker/{username}/DRVLI"},
        {"doc_key": "HSMARK", "name": "Class XII Marksheet", "issued_date": "2018-05-10",
         "uri": f"demo://digilocker/{username}/HSMARK"},
        {"doc_key": "DEGREE", "name": "Degree Certificate", "issued_date": "2021-04-30",
         "uri": f"demo://digilocker/{username}/DEGREE"},
    ]


def save_documents(account, docs):
    """Persist fetched locker documents for an account (demo or live)."""
    from .models import DigiLockerDocument
    saved = []
    for d in docs:
        mapping = DOCTYPE_MAP.get(d["doc_key"])
        if not mapping:
            continue
        step_type, doc_type, display = mapping
        obj, _created = DigiLockerDocument.objects.update_or_create(
            account=account, doc_key=d["doc_key"],
            defaults={
                "name": d.get("name") or display,
                "issued_date": d.get("issued_date", ""),
                "uri": d.get("uri", ""),
                "step_type": step_type,
                "doc_type": doc_type,
            },
        )
        saved.append(obj)
    return saved
