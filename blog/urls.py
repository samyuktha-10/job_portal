from django.urls import path

from . import views

urlpatterns = [
    path("", views.blog_home, name="blog_home"),
    path("search/", views.blog_search, name="blog_search"),
    path("category/<slug:category_slug>/", views.blog_category, name="blog_category"),
    path("authors/<slug:author_slug>/", views.blog_author, name="blog_author"),
    # Article slug comes last so the fixed routes above always win.
    path("<slug:slug>/", views.blog_detail, name="blog_detail"),
]
