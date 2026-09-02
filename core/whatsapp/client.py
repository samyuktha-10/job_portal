import requests
from django.conf import settings


def send_whatsapp_template(candidate_profile, template_name, params=None, lang="en_US"):
    """
    Sends a WhatsApp template message to a job seeker.
    candidate_profile: a JobSeekerProfile instance
    template_name: name of the approved WhatsApp template (e.g. 'application_status_update')
    params: list of strings to fill the template's {{1}}, {{2}}, etc.
    """
    if not candidate_profile.whatsapp_opted_in:
        return None

    if not candidate_profile.phone:
        return None

    url = f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": candidate_profile.phone.lstrip("+"),
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": lang},
        },
    }

    if params:
        payload["template"]["components"] = [
            {
                "type": "body",
                "parameters": [{"type": "text", "text": str(p)} for p in params],
            }
        ]

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        return response.json()
    except requests.RequestException as e:
        print("WHATSAPP SEND ERROR:", e)
        return None