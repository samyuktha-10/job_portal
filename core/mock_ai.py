"""AI mock-interview engine: question generation + answer evaluation.

Deliberately rule-based and explainable (same philosophy as the ATS checker):
questions are derived from the job's skills / description / experience level,
and every point of every score maps to something a human reviewer can see
(matched keywords, answer length, structure signals). No external API key is
required, so the feature works offline and in tests.
"""
import re

from .views import extract_keywords

FILLERS = {'um', 'uh', 'like', 'basically', 'actually', 'stuff', 'things'}
STRUCTURE_WORDS = {'because', 'therefore', 'example', 'for example', 'result',
                   'learned', 'situation', 'action', 'outcome', 'finally', 'first', 'then'}

BEHAVIORAL = (
    "Describe a time you disagreed with a teammate or manager. What did you do, "
    "and what was the outcome?"
)
BEHAVIORAL_FOCUS = ['disagree', 'team', 'outcome', 'communicat', 'resolve']


def _skills_of(job):
    return [s.strip() for s in (job.skills_required or '').split(',') if s.strip()][:6]


def generate_questions(job):
    """Return 5 ordered question dicts: {question, kind, focus_keywords}."""
    skills = _skills_of(job)
    jd_keywords = sorted(extract_keywords(
        f"{job.job_title} {job.job_description}"))[:40]

    questions = []
    for i, skill in enumerate(skills[:2]):
        questions.append({
            'question': (
                f"Tell us about a project or course where you used {skill}. "
                f"What exactly was your contribution, and what {skill}-related "
                "problems did you solve?"
            ),
            'kind': 'skill',
            'focus_keywords': sorted(extract_keywords(skill)) + [skill.lower()],
        })

    if jd_keywords:
        top = ', '.join(jd_keywords[:3])
        questions.append({
            'question': (
                f"This role focuses on {top}. How would you approach your first "
                "90 days in this position, and which of these areas would you "
                "tackle first? Why?"
            ),
            'kind': 'technical',
            'focus_keywords': jd_keywords[:8],
        })
    else:
        questions.append({
            'question': (
                f"Walk us through how you would plan and deliver a typical task "
                f"in a {job.job_title} role from requirement to completion."
            ),
            'kind': 'technical',
            'focus_keywords': sorted(extract_keywords(job.job_title))[:8],
        })

    if job.experience_required in ('fresher', '0-1'):
        questions.append({
            'question': (
                "As an early-career candidate, how do you keep your skills "
                "current? Give one concrete example of something you learned "
                "recently and how you practised it."
            ),
            'kind': 'experience',
            'focus_keywords': ['learn', 'practis', 'practice', 'project', 'course', 'skill'],
        })
    else:
        questions.append({
            'question': (
                f"Tell us about the most impactful thing you delivered in your "
                f"current or last role, and how it relates to a {job.job_title} "
                "position like this one."
            ),
            'kind': 'experience',
            'focus_keywords': ['deliver', 'impact', 'role', 'responsib', 'result'],
        })

    questions.append({
        'question': BEHAVIORAL,
        'kind': 'behavioral',
        'focus_keywords': BEHAVIORAL_FOCUS,
    })
    return questions[:5]


def _word_count(text):
    return len((text or '').split())


def evaluate_answer(question, answer_text, job):
    """Score one answer 0-100 with explainable feedback. Returns a dict."""
    text = (answer_text or '').strip()
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9'-]*", text.lower())
    answer_keywords = extract_keywords(text)
    focus = [f for f in question.get('focus_keywords', []) if f]

    matched = sorted({f for f in focus if f in answer_keywords
                      or any(f in k for k in answer_keywords)})
    missing = sorted(set(focus) - set(matched))

    # 1) relevance: 0-60 -- coverage of the question's focus keywords, plus a
    #    bonus for naming the job's actual skills.
    if focus:
        relevance = round(50 * len(matched) / len(focus))
    else:
        relevance = 25
    job_skills = {s.lower() for s in _skills_of(job)}
    if job_skills & answer_keywords:
        relevance += 10
    relevance = min(relevance, 60)

    # 2) completeness: 0-25 -- is there enough substance to judge?
    wc = _word_count(text)
    if wc < 20:
        completeness = 5
    elif wc < 50:
        completeness = 12
    elif wc < 150:
        completeness = 20
    else:
        completeness = 25

    # 3) communication: 0-15 -- structure signals minus filler words.
    sentences = len(re.split(r'[.!?]+', text)) - (1 if text else 0)
    communication = 8 if sentences >= 3 else (4 if sentences >= 1 else 0)
    fillers = sum(1 for w in words if w in FILLERS)
    communication -= min(6, fillers * 3)
    if STRUCTURE_WORDS & answer_keywords:
        communication += 7
    communication = max(0, min(communication, 15))

    score = max(0, min(100, relevance + completeness + communication))

    feedback = []
    if matched:
        feedback.append("Good coverage of: " + ', '.join(matched[:6]) + ".")
    if missing:
        feedback.append("Consider addressing: " + ', '.join(missing[:6]) + ".")
    if wc < 50:
        feedback.append("Your answer is quite short - add a concrete example "
                         "(situation, your action, the result).")
    if fillers >= 2:
        feedback.append("Reduce filler words (" + ', '.join(sorted(set(
            w for w in words if w in FILLERS))[:3]) + ") for a sharper delivery.")
    if sentences >= 3 and not (STRUCTURE_WORDS & answer_keywords):
        feedback.append("Structure helps: signal order with words like "
                        "'first', 'because', 'for example', 'result'.")
    if not feedback:
        feedback.append("Clear, relevant and well-structured answer.")

    return {
        'score': score,
        'feedback': ' '.join(feedback),
        'matched_keywords': matched,
        'missing_keywords': missing,
    }


def build_summary(session_answers, job):
    """Overall score + plain-language summary for the employer and candidate."""
    scores = [a.score for a in session_answers if a.score is not None]
    overall = round(sum(scores) / len(scores)) if scores else 0

    all_missing = []
    for a in session_answers:
        all_missing += a.missing_keywords or []
    best = max(session_answers, key=lambda a: a.score or 0) if session_answers else None
    worst = min(session_answers, key=lambda a: a.score or 0) if session_answers else None
    mic_count = sum(1 for a in session_answers if a.used_mic)

    parts = [
        f"Overall AI mock-interview score: {overall}/100 across "
        f"{len(session_answers)} questions "
        f"({mic_count} answered by voice, {len(session_answers) - mic_count} typed).",
    ]
    if best:
        parts.append(f"Strongest area: question {best.order + 1} ({best.get_kind_display()}) "
                     f"at {best.score}/100.")
    if worst:
        parts.append(f"Needs work: question {worst.order + 1} ({worst.get_kind_display()}) "
                     f"at {worst.score}/100.")
    if all_missing:
        seen = []
        for k in all_missing:
            if k not in seen:
                seen.append(k)
        parts.append("Topics to prepare before the real interview: "
                     + ', '.join(seen[:8]) + ".")
    return overall, ' '.join(parts)
