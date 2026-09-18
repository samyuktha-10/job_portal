"""Public blog views. Every page is defensive by design:

- invalid/missing page numbers fall back to page 1, out-of-range clamps to
  the last page (never a 500),
- unknown category or slug -> clean 404,
- search input is trimmed and length-capped,
- draft posts are invisible to anonymous visitors.
"""
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from .models import CATEGORIES, CATEGORY_DICT, BlogAuthor, BlogPost

SEARCH_MAX_LEN = 200
POSTS_PER_PAGE = 9


def published_posts():
    return (
        BlogPost.objects.filter(published=True, published_at__lte=timezone.now())
        .select_related("author")
    )


def safe_page(request, queryset, per_page=POSTS_PER_PAGE):
    """Paginate without ever raising on junk input.

    ``page=abc`` -> page 1, ``page=-3`` -> page 1, ``page=9999`` -> last page.
    Returns (page_obj, extra_querystring) where extra_querystring preserves
    other GET params (e.g. ``q=...``) across pagination links.
    """
    paginator = Paginator(queryset, per_page)
    raw = request.GET.get("page", "1")
    try:
        number = int(raw)
    except (TypeError, ValueError):
        number = 1
    number = max(1, min(number, paginator.num_pages or 1))
    params = request.GET.copy()
    params.pop("page", None)
    extra = params.urlencode()
    return paginator.get_page(number), ("&" + extra if extra else "")


def blog_home(request):
    posts = published_posts()
    featured = list(posts.filter(featured=True)[:3])
    sections = []
    for key, label in CATEGORIES:
        latest = list(posts.filter(category=key)[:3])
        if latest:
            sections.append({
                "key": key,
                "label": label,
                "posts": latest,
                "count": posts.filter(category=key).count(),
            })
    featured_ids = [p.pk for p in featured]
    recent = list(posts.exclude(pk__in=featured_ids)[:6])
    authors = BlogAuthor.objects.filter(posts__published=True).distinct()
    return render(request, "blog/blog_home.html", {
        "featured": featured,
        "sections": sections,
        "recent": recent,
        "authors": authors,
        "categories": CATEGORIES,
        "total": posts.count(),
    })


def blog_category(request, category_slug):
    if category_slug not in CATEGORY_DICT:
        raise Http404("Unknown blog category.")
    posts = published_posts().filter(category=category_slug)
    page_obj, extra = safe_page(request, posts)
    return render(request, "blog/blog_list.html", {
        "heading": CATEGORY_DICT[category_slug],
        "subtitle": "%d article%s" % (page_obj.paginator.count,
                                       "" if page_obj.paginator.count == 1 else "s"),
        "page_obj": page_obj,
        "extra_qs": extra,
        "active_category": category_slug,
        "categories": CATEGORIES,
    })


def blog_search(request):
    q = (request.GET.get("q") or "").strip()[:SEARCH_MAX_LEN]
    posts = published_posts()
    if q:
        posts = posts.filter(
            Q(title__icontains=q) | Q(excerpt__icontains=q)
            | Q(content__icontains=q) | Q(tags__icontains=q)
        )
    page_obj, extra = safe_page(request, posts)
    heading = ("Results for \u201c%s\u201d" % q) if q else "All articles"
    return render(request, "blog/blog_list.html", {
        "heading": heading,
        "subtitle": ("%d article%s found" % (page_obj.paginator.count,
                                             "" if page_obj.paginator.count == 1 else "s")
                     if q else "Everything published on the Deploynix blog"),
        "page_obj": page_obj,
        "extra_qs": extra,
        "query": q,
        "categories": CATEGORIES,
    })


def blog_detail(request, slug):
    post = get_object_or_404(BlogPost.objects.select_related("author"), slug=slug)
    if not post.is_visible_to(request.user):
        raise Http404("This article is not available.")

    # Race-safe view counter: increment in SQL, never through read-modify-write.
    if post.published:
        BlogPost.objects.filter(pk=post.pk).update(views=F("views") + 1)
        post.refresh_from_db(fields=["views"])

    neighbours = published_posts().filter(category=post.category)
    prev_post = neighbours.filter(published_at__lt=post.published_at).order_by("-published_at", "-id").first()
    next_post = neighbours.filter(published_at__gt=post.published_at).order_by("published_at", "id").first()
    related = list(
        published_posts().filter(category=post.category).exclude(pk=post.pk)[:3]
    )
    return render(request, "blog/blog_detail.html", {
        "post": post,
        "prev_post": prev_post,
        "next_post": next_post,
        "related": related,
        "share_url": request.build_absolute_uri(),
        "categories": CATEGORIES,
    })


def blog_author(request, author_slug):
    author = get_object_or_404(BlogAuthor, slug=author_slug)
    posts = published_posts().filter(author=author)
    page_obj, extra = safe_page(request, posts)
    return render(request, "blog/blog_author.html", {
        "author": author,
        "page_obj": page_obj,
        "extra_qs": extra,
        "categories": CATEGORIES,
    })
