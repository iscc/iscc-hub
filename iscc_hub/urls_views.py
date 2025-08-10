"""URL configuration for HTML views."""

from django.contrib import admin
from django.urls import path

from iscc_hub import views

urlpatterns = [
    path("admin", admin.site.urls),
    path("health", views.health, name="health"),
]
