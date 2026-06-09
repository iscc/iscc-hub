"""
HTTP read surface for the ISCC-Log (C2SP tlog-tiles), mounted at ``/log``.

Three static, cacheable GET endpoints (ISCC-Log §9): the signed checkpoint, the
hash tiles, and the entry bundles. These are plain Django views (not Ninja) for
full control over binary/text bodies, and are dispatched by path — never by
``Accept`` — so the Go clients and ``fsck`` that consume them (which send no
``Accept`` header) reach them. There are no proof-computing endpoints; a
Verifier computes proofs locally from the tiles.
"""

from django.http import HttpRequest, HttpResponse, HttpResponseNotFound
from django.views.decorators.http import require_safe

from iscc_hub import log_tree, merkle

# Full tiles/bundles are immutable; partial ones are rewritten as the tree grows.
_IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
_PARTIAL_CACHE = "max-age=10"


@require_safe
def checkpoint(request):
    # type: (HttpRequest) -> HttpResponse
    """Serve the latest signed checkpoint (text/plain)."""
    response = HttpResponse(log_tree.get_checkpoint(), content_type="text/plain; charset=utf-8")
    response["Cache-Control"] = _PARTIAL_CACHE
    return response


def _tile_response(data, width):
    # type: (bytes, int) -> HttpResponse
    """Wrap tile/bundle bytes with the right immutability cache header."""
    response = HttpResponse(data, content_type="application/octet-stream")
    response["Cache-Control"] = _PARTIAL_CACHE if width else _IMMUTABLE_CACHE
    return response


@require_safe
def hash_tile(request, level, tail):
    # type: (HttpRequest, int, str) -> HttpResponse
    """Serve the hash tile at ``level``/``tail`` (``application/octet-stream``)."""
    if level > 63:
        return HttpResponseNotFound()
    try:
        index, width = merkle.parse_tile_index(tail)
    except ValueError:
        return HttpResponseNotFound()
    data = log_tree.get_hash_tile(level, index, width)
    if data is None:
        return HttpResponseNotFound()
    return _tile_response(data, width)


@require_safe
def entry_bundle(request, tail):
    # type: (HttpRequest, str) -> HttpResponse
    """Serve the entry bundle at ``tail`` (``application/octet-stream``)."""
    try:
        index, width = merkle.parse_tile_index(tail)
    except ValueError:
        return HttpResponseNotFound()
    data = log_tree.get_entry_bundle(index, width)
    if data is None:
        return HttpResponseNotFound()
    return _tile_response(data, width)
