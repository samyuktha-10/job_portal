from django import template
from django.utils.safestring import mark_safe

from blog.rendering import render_content

register = template.Library()


@register.filter(name="render_content")
def render_content_filter(value):
    """Render plain-text post markup to safe HTML (escaped first)."""
    return mark_safe(render_content(value))
