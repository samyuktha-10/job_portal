"""Safe renderer for blog post content.

Posts are stored as plain text with a tiny markup subset:

    ## Heading two
    ### Heading three
    - bullet item
    > blockquote
    **bold** inline

Everything is HTML-escaped BEFORE any tags are added, so even a post whose
content contains ``<script>`` renders as harmless text. The output is safe to
use with Django's ``|safe`` filter.
"""
import html
import re

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _inline(text):
    """Escape a single line, then convert **bold** markers."""
    escaped = html.escape(text, quote=False)
    return _BOLD_RE.sub(r"<strong>\1</strong>", escaped)


def render_content(raw):
    """Convert plain-text post markup into safe HTML."""
    if not raw:
        return ""
    out = []
    paragraph = []
    bullets = []

    def flush_paragraph():
        if paragraph:
            out.append("<p>%s</p>" % "<br>".join(paragraph))
            paragraph.clear()

    def flush_bullets():
        if bullets:
            out.append("<ul>%s</ul>" % "".join("<li>%s</li>" % b for b in bullets))
            bullets.clear()

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            flush_bullets()
            continue
        if stripped.startswith("### "):
            flush_paragraph()
            flush_bullets()
            out.append("<h3>%s</h3>" % _inline(stripped[4:]))
        elif stripped.startswith("## "):
            flush_paragraph()
            flush_bullets()
            out.append("<h2>%s</h2>" % _inline(stripped[3:]))
        elif stripped.startswith("- "):
            flush_paragraph()
            bullets.append(_inline(stripped[2:]))
        elif stripped.startswith("> "):
            flush_paragraph()
            flush_bullets()
            out.append("<blockquote>%s</blockquote>" % _inline(stripped[2:]))
        else:
            flush_bullets()
            paragraph.append(_inline(stripped))

    flush_paragraph()
    flush_bullets()
    return "".join(out)
