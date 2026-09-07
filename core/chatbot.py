"""
Rule-based support chatbot for Deploynix.

No external API keys required: intent matching on keywords, canned replies in
multiple Indian languages, plus live answers pulled from the database for
logged-in users (applications, saved jobs, BGV status, employer stats).

Supported reply languages: English (en), Tamil (ta), Hindi (hi).
Other languages fall back to English text; the browser voice engine still
speaks/understands the selected locale.
"""
import re

SUPPORTED_LANGS = {
    "en-IN": "en", "ta-IN": "ta", "hi-IN": "hi",
    "te-IN": "en", "kn-IN": "en", "ml-IN": "en",
    "mr-IN": "en", "bn-IN": "en", "gu-IN": "en",
}

# (intent, [keywords]) - first match wins, checked in order
INTENTS = [
    ("greeting", ["hi", "hello", "hey", "vanakkam", "namaste", "hai"]),
    ("my_applications", ["my application", "my applications", "applied", "my apply", "application status", "my jobs applied"]),
    ("saved_jobs", ["saved job", "saved jobs", "my saved", "bookmark"]),
    ("bgv", ["bgv", "background verification", "verification status", "documents", "upload document", "my verification"]),
    ("ats", ["ats", "resume score", "resume check", "resume match"]),
    ("apply_how", ["how to apply", "how do i apply", "apply for a job", "apply job"]),
    ("post_job", ["post job", "post a job", "posting a job", "publish job", "add job"]),
    ("my_jobs_stats", ["my jobs", "my postings", "applicants", "my candidates", "how many candidates", "my job posts"]),
    ("plans", ["plan", "pricing", "price", "subscription", "upgrade", "pay"]),
    ("interview", ["interview"]),
    ("account", ["password", "login", "log in", "sign in", "account", "email verification", "otp"]),
    ("contact", ["contact", "call", "phone", "whatsapp", "human", "agent", "support number", "talk to"]),
    ("thanks", ["thanks", "thank you", "nandri", "dhanyavad"]),
    ("bye", ["bye", "good night", "see you"]),
]

REPLIES = {
    "greeting": {
        "en": "Hello! I am the Deploynix support assistant. Ask me about applying for jobs, your applications, background verification, posting jobs or plans. You can also tap the mic and speak to me.",
        "ta": "வணக்கம்! நான் டிப்ளாய்னிக்ஸ் உதவியாளர். வேலை விண்ணப்பம், உங்கள் விண்ணப்பங்கள், பின்னணி சரிபார்ப்பு, வேலை பதிவு அல்லது திட்டங்கள் பற்றி கேளுங்கள். மைக்கை அழுத்தி பேசவும்லாம்.",
        "hi": "नमस्ते! मैं डिप्लॉयनिक्स सहायक हूँ। नौकरी आवेदन, आपके आवेदन, बैकग्राउंड वेरिफिकेशन, जॉब पोस्टिंग या प्लान के बारे में पूछें। आप माइक दबाकर बोल भी सकते हैं।",
    },
    "my_applications": {
        "en": "You have {apps} application(s). Open My Applications from the menu to see each status and background verification progress.",
        "ta": "உங்களிடம் {apps} விண்ணப்பம்(கள்) உள்ளன. மெனுவில் My Applications திறந்து ஒவ்வொரு நிலையையும் BGV முன்னேற்றத்தையும் பாருங்கள்.",
        "hi": "आपके {apps} आवेदन हैं। मेनू से My Applications खोलकर हर आवेदन की स्थिति और बैकग्राउंड वेरिफिकेशन देखें।",
    },
    "saved_jobs": {
        "en": "You have {saved} saved job(s). Find them under Saved Jobs in your menu.",
        "ta": "உங்களிடம் {saved} சேமித்த வேலை(கள்) உள்ளன. மெனுவில் Saved Jobs இல் பாருங்கள்.",
        "hi": "आपके {saved} सहेजे गए जॉब हैं। मेनू में Saved Jobs से देखें।",
    },
    "bgv": {
        "en": "When an employer shortlists you, we start background verification. You will get a notification and email with your secure upload link. Upload your documents (ID, education, employment, address) there and our verifiers will review them.",
        "ta": "ஒரு நிறுவனம் உங்களை தேர்வு செய்தால், பின்னணி சரிபார்ப்பு தொடங்கும். உங்களுக்கு அறிவிப்பும் இமெயிலும் வரும். அந்த இணைப்பில் உங்கள் ஆவணங்களை (அடையாளம், கல்வி, வேலை, முகவரி) பதிவேற்றுங்கள்.",
        "hi": "जब कोई नियोक्ता आपको शॉर्टलिस्ट करता है, तो बैकग्राउंड वेरिफिकेशन शुरू होता है। आपको सूचना और ईमेल से सुरक्षित अपलोड लिंक मिलेगा। वहाँ अपने दस्तावेज़ (पहचान, शिक्षा, नौकरी, पता) अपलोड करें।",
    },
    "ats": {
        "en": "Open the ATS Checker from your menu, paste the job description and upload your resume PDF. I will score how well your resume matches the job.",
        "ta": "மெனுவில் ATS Checker திறந்து, வேலை விவரத்தை ஒட்டி உங்கள் ரெஸ்யூமே PDF பதிவேற்றுங்கள். பொருத்த மதிப்பெண் கிடைக்கும்.",
        "hi": "मेनू से ATS Checker खोलें, जॉब विवरण पेस्ट करें और अपना रिज़्यूमे PDF अपलोड करें। मैच स्कोर मिलेगा।",
    },
    "apply_how": {
        "en": "Browse Vacancies or Internships, open a job, and tap Apply. Complete your profile first if asked. You can track everything under My Applications.",
        "ta": "Vacancies அல்லது Internships பார்த்து, ஒரு வேலையை திறந்து Apply அழுத்துங்கள். கேட்டால் முதலில் உங்கள் சுயவிவரத்தை நிரப்பவும்.",
        "hi": "Vacancies या Internships देखें, जॉब खोलें और Apply दबाएँ। पूछे जाने पर पहले अपनी प्रोफ़ाइल पूरी करें।",
    },
    "post_job": {
        "en": "From your employer dashboard tap Post a Job, choose Full-time, Internship or Walk-in, fill the details and publish. Admin approval may be needed before it goes live.",
        "ta": "எம்ப்ளாயர் டாஷ்போர்டில் Post a Job அழுத்தி, வகையை தேர்வு செய்து விவரங்களை நிரப்பி வெளியிடுங்கள்.",
        "hi": "एम्पलॉयर डैशबोर्ड से Post a Job दबाएँ, श्रेणी चुनें, विवरण भरें और प्रकाशित करें।",
    },
    "my_jobs_stats": {
        "en": "You have {jobs} job post(s) and {apps} candidate application(s). Manage candidates from your dashboard.",
        "ta": "உங்களிடம் {jobs} வேலை பதிவு(கள்) மற்றும் {apps} விண்ணப்பதாரர்(கள்) உள்ளனர். டாஷ்போர்டில் நிர்வகிக்கவும்.",
        "hi": "आपके {jobs} जॉब पोस्ट और {apps} उम्मीदवार आवेदन हैं। डैशबोर्ड से प्रबंधित करें।",
    },
    "plans": {
        "en": "Plans start Free with limits on job posts and resume views. Open Plans from your dashboard to see Basic and Premium and upgrade in a few taps.",
        "ta": "இலவச திட்டத்தில் தொடங்கலாம். அடிப்படை மற்றும் பிரீமியம் திட்டங்களை உங்கள் டாஷ்போர்டில் Plans இல் பாருங்கள்.",
        "hi": "फ्री प्लान से शुरू करें। डैशबोर्ड में Plans खोलकर Basic और Premium देखें और अपग्रेड करें।",
    },
    "interview": {
        "en": "Employers can schedule interviews from Candidates -> Add Interview. Candidates see interview details in their notifications.",
        "ta": "நிறுவனங்கள் Candidates -> Add Interview மூலம் நேர்காணல் திட்டமிடலாம்.",
        "hi": "नियोक्ता Candidates -> Add Interview से इंटरव्यू शेड्यूल कर सकते हैं।",
    },
    "account": {
        "en": "Use the Forgot Password link on the login page to reset your password by email. New accounts verify their email with a 6-digit OTP.",
        "ta": "கடவுச்சொல்லை மறந்தால் லாகின் பக்கத்தில் Forgot Password பயன்படுத்துங்கள். புதிய கணக்குகள் OTP மூலம் இமெயிலை சரிபார்க்கும்.",
        "hi": "पासवर्ड भूलने पर लॉगिन पेज पर Forgot Password उपयोग करें। नए खाते OTP से ईमेल सत्यापित करते हैं।",
    },
    "contact": {
        "en": "You can reach our support team using the Call and WhatsApp buttons at the bottom of this chat. {hours}",
        "ta": "இந்த சாட்டின் கீழே உள்ள Call மற்றும் WhatsApp பொத்தான்கள் மூலம் எங்கள் ஆதரவு குழுவை தொடர்பு கொள்ளலாம். {hours}",
        "hi": "इस चैट के नीचे Call और WhatsApp बटन से हमारी सहायता टीम से संपर्क करें। {hours}",
    },
    "thanks": {
        "en": "You are welcome! Happy to help.",
        "ta": "பரவாயில்லை! மகிழ்ச்சி.",
        "hi": "आपका स्वागत है!",
    },
    "bye": {
        "en": "Goodbye! Come back anytime you need help.",
        "ta": "போய் வாருங்கள்! தேவைப்படும்போது மீண்டும் வாருங்கள்.",
        "hi": "अलविदा! ज़रूरत हो तो फिर आएँ।",
    },
    "fallback": {
        "en": "Sorry, I did not understand that. Try asking about: applying for jobs, my applications, background verification, ATS resume check, posting jobs, plans, or contact support.",
        "ta": "மன்னிக்கவும், எனக்கு புரியவில்லை. வேலை விண்ணப்பம், விண்ணப்பங்கள், BGV, ATS, வேலை பதிவு, திட்டங்கள் அல்லது தொடர்பு பற்றி கேளுங்கள்.",
        "hi": "क्षमा करें, समझ नहीं आया। जॉब आवेदन, मेरे आवेदन, BGV, ATS, जॉब पोस्टिंग, प्लान या संपर्क के बारे में पूछें।",
    },
    "not_a_candidate": {
        "en": "That is a job seeker feature. Log in with a job seeker account to use it, or ask me anything else!",
        "ta": "இது வேலை தேடுபவர்களுக்கான அம்சம். வேறு ஏதேனும் கேளுங்கள்!",
        "hi": "यह जॉब सीकर फीचर है। कुछ और पूछें!",
    },
}

QUICK_REPLIES = {
    "candidate": ["How do I apply?", "My applications", "Background verification", "ATS resume check", "Contact support"],
    "employer": ["Post a job", "My jobs and applicants", "Plans and pricing", "Interviews", "Contact support"],
    "other": ["How do I apply?", "Post a job", "Background verification", "Contact support"],
}


def detect_intent(text):
    t = (text or "").lower()
    for intent, keywords in INTENTS:
        if any(kw in t for kw in keywords):
            return intent
    return "fallback"


def _translate(lang_code, intent, **params):
    table = REPLIES.get(intent, REPLIES["fallback"])
    reply = table.get(lang_code) or table["en"]
    try:
        return reply.format(**params)
    except (KeyError, IndexError):
        return reply


def bot_reply(user, message, lang="en-IN"):
    """Return dict(reply, intent, suggestions, speak_lang) for a chat message."""
    lang_code = SUPPORTED_LANGS.get(lang, "en")
    intent = detect_intent(message)

    is_candidate = hasattr(user, "jobseeker_profile")
    is_employer = hasattr(user, "profile") and user.profile.is_employer

    if intent == "my_applications":
        if not is_candidate:
            return _pack(lang_code, _translate(lang_code, "not_a_candidate"), intent, user)
        apps = user.jobseeker_profile.applications.count() if hasattr(user.jobseeker_profile, "applications") else 0
        return _pack(lang_code, _translate(lang_code, intent, apps=apps), intent, user)

    if intent == "saved_jobs":
        if not is_candidate:
            return _pack(lang_code, _translate(lang_code, "not_a_candidate"), intent, user)
        saved = user.saved_jobs.count()
        return _pack(lang_code, _translate(lang_code, intent, saved=saved), intent, user)

    if intent == "my_jobs_stats":
        if not is_employer:
            return _pack(lang_code, _translate(lang_code, "not_a_candidate"), intent, user)
        from core.models import Job, JobApplication
        jobs = Job.objects.filter(posted_by=user)
        apps = JobApplication.objects.filter(job__in=jobs).count()
        return _pack(lang_code, _translate(lang_code, intent, jobs=jobs.count(), apps=apps), intent, user)

    if intent == "contact":
        from core.models import SupportContact
        sc = SupportContact.current()
        hours = f"Our support hours: {sc.support_hours}." if sc.support_hours else ""
        return _pack(lang_code, _translate(lang_code, intent, hours=hours), intent, user)

    if intent == "bgv" and is_candidate:
        # give live status if the candidate has a BGV in progress
        from verification.models import VerificationRequest
        bgv = (VerificationRequest.objects
               .filter(application__job_seeker_profile=user.jobseeker_profile)
               .order_by("-created_at").first())
        if bgv is not None:
            base = _translate(lang_code, intent)
            live = f"\n\nYour latest verification status: {bgv.get_overall_status_display().upper()}."
            return _pack(lang_code, base + live, intent, user)

    return _pack(lang_code, _translate(lang_code, intent), intent, user)


def _pack(lang_code, reply, intent, user):
    if hasattr(user, "jobseeker_profile"):
        role = "candidate"
    elif hasattr(user, "profile") and user.profile.is_employer:
        role = "employer"
    else:
        role = "other"
    return {
        "reply": reply,
        "intent": intent,
        "lang": lang_code,
        "suggestions": QUICK_REPLIES[role],
    }
