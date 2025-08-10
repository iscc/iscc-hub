"""URL configuration for HTML views."""

from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView

from iscc_hub import views

urlpatterns = [
    path("admin", RedirectView.as_view(url="/admin/", permanent=True)),  # Convenience redirect
    path("admin/", admin.site.urls),  # Keep trailing slash for admin compatibility
    path("health", views.health, name="health"),
]
