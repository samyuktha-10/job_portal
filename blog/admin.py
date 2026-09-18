from django.contrib import admin

from .models import BlogAuthor, BlogPost


@admin.register(BlogAuthor)
class BlogAuthorAdmin(admin.ModelAdmin):
    list_display = ("name", "role", "avatar_color", "slug")
    search_fields = ("name", "role")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "author", "published_at",
                    "published", "featured", "views")
    list_filter = ("category", "published", "featured", "banner")
    search_fields = ("title", "excerpt", "content", "tags")
    prepopulated_fields = {"slug": ("title",)}
    date_hierarchy = "published_at"
