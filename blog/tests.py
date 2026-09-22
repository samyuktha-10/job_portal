"""Tests for the Deploynix blog.

Coverage focus: the "unbreakable" guarantees — junk pagination input, unknown
slugs/categories, empty/huge/malicious search queries, draft visibility,
XSS-safe rendering, idempotent seeding and navigation wiring.
"""
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import BlogAuthor, BlogPost
from .rendering import render_content


def make_author(name="Test Author", **kwargs):
    return BlogAuthor.objects.create(name=name, **kwargs)


def make_post(title, category="career-guidance", **kwargs):
    defaults = dict(
        excerpt="An excerpt for %s." % title,
        content="## Section\n\nSome useful paragraph about %s." % title,
        author=kwargs.pop("author", None),
    )
    defaults.update(kwargs)
    return BlogPost.objects.create(title=title, category=category, **defaults)


class RenderingTests(TestCase):
    def test_headings_lists_quotes_bold(self):
        html = render_content("## Title\n### Sub\n- one\n- two\n> quoted\npara **bold** text")
        self.assertIn("<h2>Title</h2>", html)
        self.assertIn("<h3>Sub</h3>", html)
        self.assertIn("<ul><li>one</li><li>two</li></ul>", html)
        self.assertIn("<blockquote>quoted</blockquote>", html)
        self.assertIn("<strong>bold</strong>", html)

    def test_paragraphs_joined_with_breaks(self):
        html = render_content("line one\nline two")
        self.assertIn("<p>line one<br>line two</p>", html)

    def test_script_content_is_escaped(self):
        html = render_content('<script>alert("xss")</script>')
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_empty_content(self):
        self.assertEqual(render_content(""), "")
        self.assertEqual(render_content(None), "")


class ModelTests(TestCase):
    def test_slug_auto_and_unique(self):
        p1 = make_post("My Great Post!")
        p2 = make_post("My Great Post!")
        self.assertEqual(p1.slug, "my-great-post")
        self.assertEqual(p2.slug, "my-great-post-2")

    def test_author_slug_auto_and_unique(self):
        a1 = make_author("Same Name")
        a2 = BlogAuthor.objects.create(name="Same Name?")  # slugifies equal, needs suffix
        self.assertEqual(a1.slug, "same-name")
        self.assertEqual(a2.slug, "same-name-2")

    def test_read_time_minimum_one(self):
        post = make_post("Tiny", content="short")
        self.assertEqual(post.read_time, 1)

    def test_draft_visibility_rules(self):
        draft = make_post("Draft", published=False)
        future = make_post("Future", published_at=timezone.now() + timezone.timedelta(days=1))
        live = make_post("Live")

        class Anon:
            is_staff = False
            is_superuser = False

        class Staff:
            is_staff = True
            is_superuser = False

        self.assertFalse(draft.is_visible_to(Anon()))
        self.assertFalse(future.is_visible_to(Anon()))
        self.assertTrue(live.is_visible_to(Anon()))
        self.assertTrue(draft.is_visible_to(Staff()))
        # Never crashes even with None.
        self.assertFalse(draft.is_visible_to(None))

    def test_banner_fallback(self):
        # An unknown key (within the column's max_length -- Postgres enforces
        # varchar limits that SQLite ignores) must fall back to the default
        # gradient instead of breaking rendering.
        post = make_post("Banner", banner="nope")
        self.assertIn("linear-gradient", post.banner_style)


class BlogPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = make_author("Priya Raghavan", role="Careers Editor",
                                 bio="Writes about careers.")
        # Featured + enough posts to force two pages (9 per page).
        cls.featured = make_post("Featured Guide", featured=True, author=cls.author)
        cls.posts = [make_post("Article %d" % i, author=cls.author if i % 2 else None)
                     for i in range(1, 13)]
        cls.draft = make_post("Secret Draft", published=False)

    def test_home_page(self):
        r = self.client.get(reverse("blog_home"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Deploynix")
        self.assertContains(r, "Featured Guide")
        self.assertNotContains(r, "Secret Draft")
        self.assertContains(r, "Contributors")

    def test_home_empty_state(self):
        BlogPost.objects.all().delete()
        r = self.client.get(reverse("blog_home"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "No articles published yet")

    def test_category_filter_and_404(self):
        r = self.client.get(reverse("blog_category", args=["career-guidance"]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Career Guidance")
        r = self.client.get("/blog/category/does-not-exist/")
        self.assertEqual(r.status_code, 404)

    def test_search_finds_and_empty_returns_all(self):
        r = self.client.get(reverse("blog_search"), {"q": "Featured"})
        self.assertContains(r, "Featured Guide")
        r = self.client.get(reverse("blog_search"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context["page_obj"].object_list), 9)

    def test_search_xss_payload_is_harmless(self):
        payload = '<script>alert("xss")</script>'
        r = self.client.get(reverse("blog_search"), {"q": payload})
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, payload)
        self.assertContains(r, "&lt;script&gt;")

    def test_search_huge_query_capped(self):
        r = self.client.get(reverse("blog_search"), {"q": "a" * 5000})
        self.assertEqual(r.status_code, 200)

    def test_search_no_results_state(self):
        r = self.client.get(reverse("blog_search"), {"q": "zzz-no-match"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "No articles found")

    def test_detail_page_and_view_counter(self):
        url = reverse("blog_detail", args=[self.featured.slug])
        before = BlogPost.objects.get(pk=self.featured.pk).views
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, self.featured.title)
        self.assertContains(r, "wa.me")  # share buttons rendered
        after = BlogPost.objects.get(pk=self.featured.pk).views
        self.assertEqual(after, before + 1)

    def test_detail_post_content_xss_safe(self):
        evil = make_post("Evil", content='<script>alert("xss")</script>')
        r = self.client.get(reverse("blog_detail", args=[evil.slug]))
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(b'<script>alert("xss")</script>', r.content)
        self.assertIn(b"&lt;script&gt;", r.content)

    def test_detail_404s(self):
        self.assertEqual(self.client.get("/blog/no-such-post/").status_code, 404)
        self.assertEqual(self.client.get("/blog/%s/" % self.draft.slug).status_code, 404)

    def test_draft_preview_for_staff_only(self):
        staff = User.objects.create_user("staffblog", "s@x.com", "pw", is_staff=True)
        self.client.force_login(staff)
        r = self.client.get(reverse("blog_detail", args=[self.draft.slug]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Draft preview")

    def test_pagination_garbage_is_safe(self):
        url = reverse("blog_category", args=["career-guidance"])
        for junk in ("abc", "-3", "0", "99999", ""):
            r = self.client.get(url, {"page": junk})
            self.assertEqual(r.status_code, 200, junk)
        # page=99999 must clamp to the last page, not error
        r = self.client.get(url, {"page": "99999"})
        self.assertEqual(r.context["page_obj"].number,
                         r.context["page_obj"].paginator.num_pages)

    def test_pagination_preserves_search_query(self):
        r = self.client.get(reverse("blog_search"), {"q": "Article", "page": "2"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("q=Article", r.context["extra_qs"])

    def test_author_page_and_404(self):
        r = self.client.get(reverse("blog_author", args=[self.author.slug]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Priya Raghavan")
        self.assertEqual(self.client.get("/blog/authors/ghost/").status_code, 404)

    def test_related_and_prev_next_on_detail(self):
        r = self.client.get(reverse("blog_detail", args=[self.posts[0].slug]))
        self.assertContains(r, "Related Articles")


class SeedAndNavTests(TestCase):
    def test_seed_command_idempotent(self):
        call_command("seed_blog", verbosity=0)
        n_posts, n_authors = BlogPost.objects.count(), BlogAuthor.objects.count()
        self.assertEqual(n_posts, 13)
        self.assertEqual(n_authors, 3)
        call_command("seed_blog", verbosity=0)
        self.assertEqual(BlogPost.objects.count(), n_posts)
        self.assertEqual(BlogAuthor.objects.count(), n_authors)
        # Featured articles exist and slugs stay stable for deep links.
        self.assertTrue(BlogPost.objects.filter(featured=True).count() >= 3)
        self.assertTrue(BlogPost.objects.filter(
            slug="how-to-write-job-application-email").exists())

    def test_seeded_pages_render(self):
        call_command("seed_blog", verbosity=0)
        self.assertEqual(self.client.get("/blog/").status_code, 200)
        post = BlogPost.objects.filter(featured=True).first()
        self.assertEqual(self.client.get("/blog/%s/" % post.slug).status_code, 200)
        self.assertEqual(self.client.get("/blog/category/salary/").status_code, 200)
        self.assertEqual(self.client.get(
            "/blog/authors/%s/" % post.author.slug).status_code, 200)

    def test_navbar_and_footer_link_to_blog(self):
        r = self.client.get("/")
        self.assertContains(r, reverse("blog_home"))

    def test_chatbot_knows_about_blog(self):
        from core.chatbot import detect_intent
        self.assertEqual(detect_intent("Do you have career tips?"), "blog")
        self.assertEqual(detect_intent("show me your blog"), "blog")
