"""URL configuration for API endpoints."""

from django.urls import path

from iscc_hub.api import api

urlpatterns = [
    path("", api.urls),
]
