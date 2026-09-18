"""Blog models for the Deploynix career blog.

Design notes ("unbreakable" rules):
- No external image dependencies: every post banner is a CSS gradient + emoji
  chosen from a fixed palette, so nothing can ever 404.
- Slugs are generated automatically and made unique with numeric suffixes.
- Post content is plain text with a tiny markup subset (## headings,
  ``-`` bullets, ``>`` quotes, ``**bold**``). It is rendered by
  ``blog.rendering.render_content`` which escapes FIRST, then wraps in
  tags, so stored content can never inject HTML/JS.
"""
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

CATEGORIES = [
    ("interview-questions", "Interview Questions"),
    ("career-guidance", "Career Guidance"),
    ("job-application", "Job Application"),
    ("resume-format", "Resume Format"),
    ("salary", "Salary Insights"),
    ("internships", "Internships"),
    ("expert-edge", "Expert Edge"),
]
CATEGORY_DICT = dict(CATEGORIES)

# key -> (admin label, CSS gradient used as inline style)
BANNERS = [
    ("purple", "Purple"),
    ("blue", "Blue"),
    ("pink", "Pink"),
    ("teal", "Teal"),
    ("amber", "Amber"),
    ("green", "Green"),
    ("slate", "Slate"),
]
BANNER_CSS = {
    "purple": "linear-gradient(135deg, #a855f7 0%, #6d28d9 100%)",
    "blue": "linear-gradient(135deg, #38bdf8 0%, #1d4ed8 100%)",
    "pink": "linear-gradient(135deg, #f472b6 0%, #be185d 100%)",
    "teal": "linear-gradient(135deg, #2dd4bf 0%, #0f766e 100%)",
    "amber": "linear-gradient(135deg, #fbbf24 0%, #b45309 100%)",
    "green": "linear-gradient(135deg, #4ade80 0%, #15803d 100%)",
    "slate": "linear-gradient(135deg, #64748b 0%, #1e293b 100%)",
}

AVATAR_COLORS = [
    ("red", "#dc2626"),
    ("purple", "#7c3aed"),
    ("teal", "#0d9488"),
    ("blue", "#2563eb"),
    ("amber", "#d97706"),
    ("pink", "#db2777"),
]
AVATAR_COLOR_DICT = dict(AVATAR_COLORS)

WORDS_PER_MINUTE = 200


def unique_slug(base, exists_fn, max_length=200):
    """Return ``base`` (slugified) or ``base-2``, ``base-3`` ... until unique."""
    base = (slugify(base, allow_unicode=False) or "post")[:max_length]
    candidate = base
    n = 2
    while exists_fn(candidate):
        suffix = "-%d" % n
        candidate = base[: max_length - len(suffix)] + suffix
        n += 1
    return candidate


class BlogAuthor(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    role = models.CharField(max_length=120, blank=True, default="")
    bio = models.TextField(blank=True, default="")
    avatar_color = models.CharField(max_length=12, choices=AVATAR_COLORS, default="red")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(
                self.name,
                lambda s: BlogAuthor.objects.exclude(pk=self.pk).filter(slug=s).exists(),
                max_length=140,
            )
        super().save(*args, **kwargs)

    @property
    def initial(self):
        return (self.name or "D").strip()[:1].upper() or "D"

    @property
    def avatar_color_value(self):
        return AVATAR_COLOR_DICT.get(self.avatar_color, "#64748b")


class BlogPost(models.Model):
    title = models.CharField(max_length=220)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    author = models.ForeignKey(
        BlogAuthor, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="posts",
    )
    category = models.CharField(max_length=40, choices=CATEGORIES, db_index=True)
    excerpt = models.TextField(max_length=500, blank=True, default="")
    content = models.TextField(help_text="Plain text markup: ## heading, ### subheading, - bullet, > quote, **bold**.")
    tags = models.CharField(max_length=300, blank=True, default="",
                            help_text="Comma separated tags.")
    banner = models.CharField(max_length=12, choices=BANNERS, default="blue")
    emoji = models.CharField(max_length=8, default="📝")
    featured = models.BooleanField(default=False, db_index=True)
    published = models.BooleanField(default=True, db_index=True)
    published_at = models.DateTimeField(default=timezone.now, db_index=True)
    views = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at", "-id"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(
                self.title,
                lambda s: BlogPost.objects.exclude(pk=self.pk).filter(slug=s).exists(),
                max_length=220,
            )
        super().save(*args, **kwargs)

    # ---- display helpers -------------------------------------------------
    @property
    def banner_style(self):
        return BANNER_CSS.get(self.banner, BANNER_CSS["blue"])

    @property
    def tags_list(self):
        return [t.strip() for t in (self.tags or "").split(",") if t.strip()]

    @property
    def read_time(self):
        words = len((self.content or "").split())
        return max(1, round(words / WORDS_PER_MINUTE))

    @property
    def author_name(self):
        return self.author.name if self.author else "Deploynix Editorial"

    def is_visible_to(self, user):
        """Published posts are public; drafts are previewable by staff only."""
        if self.published and self.published_at <= timezone.now():
            return True
        return bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))
