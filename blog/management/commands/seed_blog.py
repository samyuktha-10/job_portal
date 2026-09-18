"""Seed the Deploynix blog with demo authors and articles.

Idempotent: authors and posts are keyed by name/slug, so the command can be
re-run safely (it refreshes content instead of duplicating).

Usage:  python manage.py seed_blog
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from blog.models import BlogAuthor, BlogPost

AUTHORS = [
    dict(name="Priya Raghavan", role="Careers Editor", avatar_color="purple",
         bio="Priya writes about resumes, interviews and everything that happens between 'applied' and 'hired'."),
    dict(name="Arjun Mehta", role="Recruitment Specialist", avatar_color="teal",
         bio="Arjun has screened thousands of applications and shares what recruiters actually look for."),
    dict(name="Deploynix Editorial Team", role="Editorial Team", avatar_color="red",
         bio="Guides, data and career insights from the Deploynix team."),
]

POSTS = [
    # ---- Interview Questions -------------------------------------------
    dict(slug="top-20-hr-interview-questions-and-answers",
         title="Top 20 HR Interview Questions and How to Answer Them",
         category="interview-questions", author="Priya Raghavan",
         banner="blue", emoji="🎯", featured=True, tags="interview, hr, questions",
         excerpt="The 20 most common HR questions, what the interviewer is really testing, and sample answers you can adapt.",
         content="""HR interviews test communication, honesty and fit, not technical depth. Prepare stories, not scripts.

## The classics you will almost certainly hear

- **Tell me about yourself.** Give a 60-second pitch: present role, relevant past, and why this job is next.
- **Why do you want this job?** Connect the company's work to your own goals. Name something specific about the company.
- **What are your strengths and weaknesses?** Pick a real strength with proof, and a weakness you are actively fixing.
- **Where do you see yourself in five years?** Show ambition that this role can realistically feed.
- **Why should we hire you?** Summarise the match: their needs, your evidence.

## Tricky ones worth rehearsing

- **Tell me about a conflict at work.** Describe the situation, your calm action, and the resolution. Never blame.
- **Why is there a gap in your career?** Be brief and honest, then pivot to what you learned or built.
- **What salary do you expect?** Give a researched range and say you are open to the full package.

> Interviewers remember structure. Use the STAR method: Situation, Task, Action, Result.

## How to practise

- Write bullet-point answers, not essays, and speak them out loud.
- Do one mock interview with a friend two days before, not the night before.
- Prepare 3 questions to ask them at the end; it signals genuine interest.

Walk in with examples ready and you will outperform most candidates."""),

    dict(slug="how-to-answer-tell-me-about-yourself",
         title="How to Answer 'Tell Me About Yourself' (With Sample Answers)",
         category="interview-questions", author="Arjun Mehta",
         banner="purple", emoji="🗣️", featured=False, tags="interview, introduction, freshers",
         excerpt="The first question sets the tone for the whole interview. Use this simple 3-part formula with ready-to-adapt samples.",
         content="""'Tell me about yourself' is an invitation to frame the conversation. Use the **Present-Past-Future** formula and keep it under 90 seconds.

## The formula

- **Present:** who you are right now (degree, role, or most recent work).
- **Past:** two or three experiences that built relevant skills.
- **Future:** why this role is the logical next step.

## Sample for a fresher

'I just completed my B.E. in Computer Science at Anna University. During my final year I built a college placement tracker used by 200 students, which taught me Django and teamwork under deadlines. I'm now looking for a developer role where I can ship real products, which is why your opening excited me.'

## Sample for an experienced candidate

'I'm a support engineer with three years at an IT services firm, where I own escalations for 40 enterprise clients. Before that I interned in QA, which is where I learned to reproduce issues systematically. I want to move into a product company because I enjoy fixing root causes more than firefighting, and your team's focus on reliability matches that.'

## Mistakes to avoid

- Reciting your resume line by line.
- Sharing personal history that isn't relevant.
- Rambling past two minutes.

> Practise out loud until it sounds natural, then stop rehearsing the exact words."""),

    # ---- Career Guidance -----------------------------------------------
    dict(slug="career-planning-for-final-year-students",
         title="Career Planning for Final-Year Students: A Step-by-Step Guide",
         category="career-guidance", author="Deploynix Editorial Team",
         banner="teal", emoji="🧭", featured=True, tags="students, career plan, campus",
         excerpt="Final year feels overwhelming. This 12-month plan breaks it into small, doable steps from self-assessment to offer letter.",
         content="""Most students lose final year to panic. A simple timeline beats a perfect plan.

## Months 1 to 2: know your starting point

- List subjects and tasks you genuinely enjoy; patterns reveal direction.
- Take one aptitude test and note strengths, not just the score.
- Talk to three seniors in different roles; ask about their actual week.

## Months 3 to 5: build proof of skill

- Pick one track (for example: web development, data, marketing, design) and finish two real projects.
- Create profiles on job portals, including Deploynix, and keep them complete.
- Attend campus sessions and walk-in drives even 'just to observe'.

## Months 6 to 9: apply seriously

- Tailor your resume per role; our Resume Format section shows how.
- Apply in small daily batches: 5 quality applications beat 50 sprayed ones.
- Log every application and follow up politely after a week.

## Months 10 to 12: convert and negotiate

- Practise interviews weekly; record yourself once.
- Compare offers on total package, learning and location, not just CTC.

> Your first job is a launchpad, not a life sentence. Direction matters more than speed.

If you're stuck between two paths, choose the one where you learn faster."""),

    dict(slug="freelancing-while-studying",
         title="How to Earn With Freelancing While You Study",
         category="career-guidance", author="Arjun Mehta",
         banner="amber", emoji="💼", featured=False, tags="freelance, students, earning",
         excerpt="Freelancing builds your resume and your wallet at the same time. Here's how to start without tanking your grades.",
         content="""Freelancing is the best side hustle for students because it doubles as portfolio building.

## Skills that get student-friendly work

- Content writing and social media posts
- Basic web pages (HTML, CSS, WordPress)
- Graphic design for local shops and clubs
- Data entry, transcription, and video editing

## How to get your first three clients

- Tell professors, seniors and local businesses what you offer; referrals beat cold pitching.
- Do one small paid project at a low rate in exchange for a testimonial.
- Create a simple one-page portfolio; a clean PDF also works.

## Protect your studies

- Cap freelance work at **10 to 12 hours a week** during term.
- Never accept deadlines that clash with exams; say no early.
- Keep one buffer day per week for backlog.

## Money basics

- Agree scope and payment in writing, even for known clients.
- Take 50% advance for any project above a week of effort.
- Track income monthly; it helps with taxes later.

> A completed freelance project impresses interviewers more than any certificate."""),

    # ---- Job Application ------------------------------------------------
    dict(slug="how-to-write-job-application-email",
         title="How to Write a Job Application Email That Gets Replies",
         category="job-application", author="Priya Raghavan",
         banner="pink", emoji="✉️", featured=True, tags="email, application, cover letter",
         excerpt="Recruiters spend seconds on each email. This format, subject line guide and sample will get yours actually read.",
         content="""Your application email has one job: make the recruiter open your resume.

## The subject line does half the work

- Format: **Role - Your Name - Key qualification**
- Example: 'Frontend Developer - Meera S - 2 yrs React'
- Never leave it blank or write only 'Job application'.

## Structure in four short paragraphs

- **Opening:** the exact role and where you saw it.
- **Pitch:** two lines of your strongest, most relevant proof.
- **Logistics:** notice period, location preference, links to portfolio.
- **Close:** polite sign-off with phone number and resume attached as PDF.

## Sample

Subject: Data Analyst - Karthik R - SQL and Power BI

Dear Hiring Team,

I'm applying for the Data Analyst position listed on Deploynix. In my last role I automated weekly sales reporting with SQL and Power BI, saving the team 15 hours a month.

I'm based in Chennai, can join within 30 days, and my portfolio is linked in my resume.

Thank you for your time.
Karthik R, +91 98xxxxxx01

## Common mistakes

- Attaching Word files instead of PDF.
- Writing a 400-word life story.
- Sending at midnight; weekday mornings work better.

> Keep the whole email under 120 words. Brevity itself is a skill signal."""),

    dict(slug="seven-mistakes-that-get-applications-rejected",
         title="7 Mistakes That Get Your Application Rejected in 30 Seconds",
         category="job-application", author="Arjun Mehta",
         banner="slate", emoji="🚫", featured=False, tags="application, mistakes, rejection",
         excerpt="Recruiters reject most applications before finishing them. Check that you're not making these seven errors.",
         content="""After screening thousands of applications, here are the fastest ways to a 'no'.

## The seven mistakes

- **Wrong company name in the cover letter.** It screams copy-paste.
- **One generic resume for every role.** Mirror the job description's keywords honestly.
- **Unprofessional email ID.** Use firstname.lastname@gmail.com.
- **No numbers anywhere.** 'Improved sales' is forgettable; 'grew sales 18%' is not.
- **Applying for roles far outside your profile.** Stretch is fine; fantasy is not.
- **Broken links.** Test your portfolio, LinkedIn and GitHub links from another device.
- **Silence after applying.** A polite follow-up after 7 days is normal, not annoying.

## The 30-second self-check

- Read your resume out loud; anything awkward, rewrite.
- Run it through our **ATS Checker** to catch formatting issues.
- Ask one friend: 'What is my strongest skill based on this page?' If they can't answer, neither can a recruiter.

> Rejection is rarely about talent. It's usually about presentation, and presentation is fixable."""),

    # ---- Resume Format ---------------------------------------------------
    dict(slug="resume-format-for-freshers",
         title="Resume Format for Freshers: A Simple Template That Works",
         category="resume-format", author="Priya Raghavan",
         banner="green", emoji="📄", featured=False, tags="resume, freshers, template",
         excerpt="No experience? No problem. This one-page order puts your strongest assets first and passes recruiter screening.",
         content="""Freshers should lead with potential: education, projects and skills, in that spirit.

## The order that works

- **Header:** name, phone, professional email, LinkedIn, city.
- **Summary:** 2 lines connecting your degree to the target role.
- **Education:** degree, college, CGPA if above 7, and graduation year.
- **Projects:** 2 or 3 with problem, tools, and result.
- **Skills:** grouped honestly, like 'Python, SQL' versus 'Familiar with AWS'.
- **Certifications and activities:** keep only recent, relevant ones.

## Project lines that impress

- Weak: 'Did a website project in final year.'
- Strong: 'Built a hostel complaint tracker (Django, SQLite) used by 300 students; cut resolution time from 3 days to 1.'

## Formatting rules

- One page, clean fonts, no photos unless asked.
- No tables or graphics if you'll apply online; they confuse ATS software.
- Save as **FirstName_LastName_Resume.pdf**.

> Every line should answer one question: why can this person do the job?

Pair this format with our ATS Checker before you hit apply."""),

    dict(slug="make-your-resume-ats-friendly",
         title="Beat the Bots: How to Make Your Resume ATS-Friendly",
         category="resume-format", author="Deploynix Editorial Team",
         banner="blue", emoji="🤖", featured=False, tags="ats, resume, keywords",
         excerpt="Many resumes are filtered by software before any human sees them. These changes make yours machine-readable.",
         content="""An ATS (Applicant Tracking System) parses your resume into plain text. Fancy design can silently destroy your content.

## What breaks parsing

- Tables, text boxes, headers and footers with key info
- Icons replacing words (a phone symbol instead of 'Phone:')
- JPEG or PDF scans that are actually images
- Creative section titles like 'My Journey' instead of 'Experience'

## What passes cleanly

- Single-column layout with standard headings: Summary, Experience, Education, Skills.
- Plain bullet points and standard fonts.
- Keywords copied from the job description, used honestly.
- Dates in common formats like 'Jun 2024 - Present'.

## Keyword strategy

- List the top skills from 5 similar job posts; the repeats are what the ATS hunts for.
- Include both forms: 'JavaScript' and 'JS', 'Search Engine Optimization' and 'SEO'.
- Never keyword-stuff; a human reads it eventually.

> Deploynix has a free **ATS Checker** under your profile menu. Paste the job description, upload your resume PDF, and fix what the score flags before applying."""),

    # ---- Salary -----------------------------------------------------------
    dict(slug="entry-level-salaries-india-2026",
         title="Entry-Level Salaries in India: What to Expect in 2026",
         category="salary", author="Deploynix Editorial Team",
         banner="amber", emoji="💰", featured=False, tags="salary, freshers, india",
         excerpt="Realistic fresher ranges across IT, BFSI, marketing and core engineering, plus what actually moves the number.",
         content="""Salary talk is full of outliers. Here are grounded ranges for freshers in 2026.

## Typical fresher ranges (annual CTC)

- **Software development:** 4 to 9 LPA in services firms; 8 to 20+ in product companies.
- **Data and analytics:** 4 to 8 LPA, higher with strong SQL and project proof.
- **Digital marketing:** 2.5 to 5 LPA; portfolios can push this up fast.
- **BFSI and operations:** 3 to 6 LPA with steadier increments.
- **Core engineering:** 3.5 to 7 LPA, with PSUs and railways via exams as alternatives.

> Metro cities pay 10 to 20% more, but rent eats a big slice. Compare net savings, not CTC.

## What actually moves your number

- Demonstrated skills: projects, internships, and measurable results.
- Multiple offers; competing offers remain the strongest lever.
- Communication skills, which influence interview scores heavily.

## Understand the breakup

- **Fixed vs variable:** ask what portion is performance-linked.
- **Deductions:** PF, professional tax, and the new tax regime change in-hand pay.
- A 6 LPA offer can mean roughly 42 to 45k in hand monthly; always ask for the breakup.

Use these ranges as guardrails, not gospel, when you negotiate."""),

    dict(slug="how-to-negotiate-your-first-salary",
         title="How to Negotiate Your First Salary Without Fear",
         category="salary", author="Priya Raghavan",
         banner="teal", emoji="🤝", featured=False, tags="salary, negotiation, offer",
         excerpt="Even freshers can negotiate respectfully. Scripts and ranges included for the awkward money conversation.",
         content="""Companies expect a polite negotiation. Silence costs you money.

## Before the call

- Research the role's market range on job portals and from seniors.
- Decide your walk-in number and your target number.
- Collect evidence: internship outcomes, projects, competing offers.

## Scripts that work

- On a low offer: 'Thank you, I'm excited about the role. Based on my research and my internship results, I was expecting something closer to X. Is there flexibility?'
- When asked your expectation: give a range anchored slightly above your target: 'I'm looking at 6 to 7 LPA based on the responsibilities we discussed.'
- If the budget is fixed: ask about review cycles, joining bonus, relocation, or learning allowances instead.

## Rules of the game

- Negotiate once, politely; don't reopen it weekly.
- Get the final numbers in the written offer.
- Never bluff with a fake competing offer; rescinded offers are real.

> The worst outcome of a respectful ask is usually 'no', and 'no' is where you already were."""),

    # ---- Internships -------------------------------------------------------
    dict(slug="convert-internship-into-full-time-job",
         title="From Internship to Offer: Converting Your Internship Into a Full-Time Job",
         category="internships", author="Arjun Mehta",
         banner="purple", emoji="🚀", featured=False, tags="internship, conversion, full-time",
         excerpt="Most full-time conversions are decided quietly, weeks before HR speaks. Here's how to be the obvious choice.",
         content="""An internship is a three-month interview. Conversion decisions are usually made informally first.

## Weeks 1 to 2: become easy to work with

- Write down everything; never ask the same question twice.
- Learn how the team communicates: email, chat, or quick calls.
- Ship something small early, even if it's just fixing documentation.

## Weeks 3 to 8: create visible value

- Own one task end-to-end and finish it without reminders.
- Send a short weekly update to your mentor: done, planned, blocked.
- Ask for feedback mid-way and act on it visibly.

## Final weeks: make the ask explicit

- Tell your mentor you'd love to continue full-time; don't assume they know.
- Ask what a conversion would require and close any gaps named.
- Document your work in a short handover note; it proves maturity.

## If there are no openings

- Ask to be referred internally or recommended on LinkedIn.
- Convert the experience into resume lines with numbers.

> Interns who communicate like employees get treated like future employees."""),

    dict(slug="find-genuine-internships-avoid-scams",
         title="How to Find Genuine Internships and Spot the Scams",
         category="internships", author="Deploynix Editorial Team",
         banner="pink", emoji="🛡️", featured=False, tags="internship, scams, safety",
         excerpt="Fake internships target eager students. Learn the red flags and where legitimate internships actually live.",
         content="""Where there's demand, scammers follow. Protect your time, money and data.

## Red flags of a fake internship

- They ask YOU to pay: 'training fees', 'registration', or 'laptop security deposit'.
- Offer letter arrives without any interview or task.
- Vague job descriptions with extravagant stipends for zero skills.
- Communication only from free email IDs claiming to be big brands.
- Requests for bank OTPs, Aadhaar passwords, or scanned signatures on blank paper.

## Where real internships live

- Your college placement cell and alumni network.
- Established job portals; on Deploynix, internships are listed under **Internships** and employers are gated by approval.
- Company career pages for firms you can verify on LinkedIn.

## Quick verification checklist

- Search the company name plus 'scam' or 'reviews'.
- Check the company exists on the MCA registry for Indian firms.
- Ask the recruiter for the interviewer's full name and team; real teams answer this easily.

> No legitimate employer charges candidates money. Ever. Walk away the moment fees are mentioned."""),

    # ---- Expert Edge ---------------------------------------------------
    dict(slug="what-recruiters-look-for-in-first-30-seconds",
         title="What Recruiters Look For in the First 30 Seconds of an Interview",
         category="expert-edge", author="Arjun Mehta",
         banner="slate", emoji="🔍", featured=False, tags="expert, recruiter, first impressions",
         excerpt="A recruiter explains the split-second judgments made before your first answer, and how to tilt them in your favour.",
         content="""Thirty seconds before your first real answer, a recruiter has already formed impressions. Here's what drives them.

## What gets noticed first

- **Punctuality and setup:** joining on time, camera and audio working, clean background. Lateness reads as unreliability.
- **Greeting energy:** eye contact, a clear hello, and a smile beat a perfect script.
- **How you introduce yourself:** structured beats rambling; 60 to 90 seconds is the sweet spot.

## The quiet signals

- You mention the company's actual work instead of generic praise.
- You ask a thoughtful question early, showing you researched the role.
- You admit when you don't know something, then reason aloud.

## What hurts you instantly

- Reading answers from the screen; recruiters can see your eyes moving.
- Interrupting or finishing the interviewer's sentences.
- Bad-mouthing a previous college, team, or employer.

> Interviews are conversations with consequences. Warm, prepared and concise wins over flashy.

Every signal above is trainable. Record one mock interview this week and watch it back; you'll spot your own tells immediately."""),
]


class Command(BaseCommand):
    help = "Seed the Deploynix blog with demo authors and articles (idempotent)."

    def handle(self, *args, **options):
        now = timezone.now()
        authors = {}
        for data in AUTHORS:
            author, _ = BlogAuthor.objects.update_or_create(
                name=data["name"],
                defaults={"role": data["role"], "avatar_color": data["avatar_color"],
                          "bio": data["bio"]},
            )
            authors[data["name"]] = author

        created = updated = 0
        for i, data in enumerate(POSTS):
            defaults = {
                "title": data["title"],
                "author": authors[data["author"]],
                "category": data["category"],
                "excerpt": data["excerpt"],
                "content": data["content"],
                "tags": data["tags"],
                "banner": data["banner"],
                "emoji": data["emoji"],
                "featured": data["featured"],
                "published": True,
            }
            post, was_created = BlogPost.objects.update_or_create(
                slug=data["slug"], defaults=defaults)
            # Only set the publish date on first creation so re-runs don't
            # shuffle dates (and views) around.
            if was_created:
                post.published_at = now - timezone.timedelta(days=i * 3, hours=i)
                post.save(update_fields=["published_at"])
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(
            "Blog seeded: %d created, %d updated, %d authors."
            % (created, updated, len(authors))))
