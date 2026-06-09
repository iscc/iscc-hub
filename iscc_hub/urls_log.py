"""URL configuration for the ISCC-Log read endpoints (mounted at /log)."""

from django.urls import path

from iscc_hub import log_api

urlpatterns = [
    path("log/checkpoint", log_api.checkpoint, name="log_checkpoint"),
    path("log/tile/entries/<path:tail>", log_api.entry_bundle, name="log_entry_bundle"),
    path("log/tile/<int:level>/<path:tail>", log_api.hash_tile, name="log_hash_tile"),
]
