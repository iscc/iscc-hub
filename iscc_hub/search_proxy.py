"""
Similarity-search proxy: forwards /search requests to external iscc-search backends.

The Hub mirrors the iscc-search contract (simprint-free) against a single
hub-global index, with ordered failover across configured backends. The module
splits into a pure policy core (validation, failover classification, circuit
breaker transitions, response projection — all testable without I/O) and a thin
I/O shell (shared niquests session, in-flight semaphore, per-backend breakers).

Opt-in: with no ISCC_HUB_SEARCH_URLS configured, every /search request gets 404.
"""

import json
import re
import threading
import time

import niquests
from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse

from iscc_hub.exceptions import BaseApiException, NotFoundError, SearchUnavailableError

# Retry-After seconds on 503 responses (module constant by design; not server config)
RETRY_AFTER = 5

# Bounds for the client-facing limit parameter (the backend imposes no maximum)
LIMIT_MIN = 1
LIMIT_MAX = 100

# Documented query fields: request allow-list on POST /search (everything else, simprints
# included, -> 400) and keys kept by the L11 response projection
QUERY_KEYS = ("iscc_id", "iscc_code", "units")
ALLOWED_QUERY_KEYS = frozenset(QUERY_KEYS)

# Documented match shape: keys kept by the L11 allow-list projection
MATCH_KEYS = ("iscc_id", "score", "types", "metadata")

ISCC_ID_PATTERN = re.compile(r"^ISCC:[A-Z2-7]{16}$")
ISCC_CODE_PATTERN = re.compile(r"^ISCC:[A-Z2-7]{16,}$")


####################################################################################################
# Pure policy core (no I/O)                                                                        #
####################################################################################################


def validate_limit(raw):
    # type: (str|None) -> int|None
    """
    Validate the optional limit query parameter; None passes the backend default through.

    :param raw: Raw query-string value or None when absent
    :return: Parsed limit, or None when not provided
    """
    if raw is None:
        return None
    message = f"limit must be an integer between {LIMIT_MIN} and {LIMIT_MAX}"
    try:
        limit = int(raw)
    except ValueError:
        raise BaseApiException(message) from None
    if not LIMIT_MIN <= limit <= LIMIT_MAX:
        raise BaseApiException(message)
    return limit


def validate_query_body(raw):
    # type: (bytes) -> dict
    """
    Validate a POST /search body against the simprint-free allow-list.

    Rejects any top-level key outside ALLOWED_QUERY_KEYS by explicit key check
    (not schema omission, not a substring scan), validates documented field
    formats, and requires at least one query field. Item contents of units are
    left to the backend.

    :param raw: Raw request body bytes (forwarded as-is on success)
    :return: Parsed body dict
    """
    try:
        data = json.loads(raw)
    except ValueError:
        raise BaseApiException("Request body must be valid JSON") from None
    if not isinstance(data, dict):
        raise BaseApiException("Request body must be a JSON object")
    unknown = sorted(set(data) - ALLOWED_QUERY_KEYS)
    if unknown:
        raise BaseApiException(f"Unknown query field(s): {', '.join(unknown)}")
    if all(data.get(key) is None for key in ALLOWED_QUERY_KEYS):
        raise BaseApiException("At least one of iscc_id, iscc_code or units is required")
    iscc_id = data.get("iscc_id")
    if iscc_id is not None and not (isinstance(iscc_id, str) and ISCC_ID_PATTERN.match(iscc_id)):
        raise BaseApiException("Invalid iscc_id format. Expected: ISCC: followed by 16 base32 characters")
    iscc_code = data.get("iscc_code")
    if iscc_code is not None and not (isinstance(iscc_code, str) and ISCC_CODE_PATTERN.match(iscc_code)):
        raise BaseApiException("Invalid iscc_code format. Expected: ISCC: followed by 16+ base32 characters")
    units = data.get("units")
    if units is not None and not (isinstance(units, list) and len(units) > 0):
        raise BaseApiException("units must be a non-empty array")
    return data


def classify_status(status):
    # type: (int) -> str
    """
    Classify a backend HTTP status as 'ok', 'passthrough', or 'retryable'.

    2xx succeeds; 400/404/422 are deterministic backend answers forwarded to the
    client without failover; everything else (5xx, 401/403/429, redirects) means
    this backend cannot serve the request right now — try the next one.

    :param status: Backend HTTP status code
    :return: One of 'ok', 'passthrough', 'retryable'
    """
    if 200 <= status < 300:
        return "ok"
    if status in (400, 404, 422):
        return "passthrough"
    return "retryable"


def valid_score(value):
    # type: (object) -> bool
    """Return True when value is a JSON number within the documented 0.0-1.0 score range."""
    return isinstance(value, int | float) and not isinstance(value, bool) and 0.0 <= value <= 1.0


def valid_query_echo(query):
    # type: (dict) -> bool
    """
    Return True when the documented fields of a backend's echoed query are well-formed.

    Undocumented keys are ignored (the projection drops them); only values that
    survive into the Hub response are checked against the IsccQuery shape.

    :param query: Parsed query object from a backend 2xx body
    :return: True when all documented field values conform
    """
    iscc_id = query.get("iscc_id")
    if iscc_id is not None and not (isinstance(iscc_id, str) and ISCC_ID_PATTERN.match(iscc_id)):
        return False
    iscc_code = query.get("iscc_code")
    if iscc_code is not None and not (isinstance(iscc_code, str) and ISCC_CODE_PATTERN.match(iscc_code)):
        return False
    units = query.get("units")
    if units is not None and not (isinstance(units, list) and len(units) > 0):
        return False
    return units is None or all(isinstance(unit, str) for unit in units)


def valid_match(match):
    # type: (object) -> bool
    """
    Return True when a backend match conforms to the documented IsccGlobalMatch shape.

    Requires a well-formed iscc_id, a score within 0.0-1.0, types as a map of
    in-range unit scores, and metadata (when present) as an object or null.

    :param match: One entry of a backend's global_matches list
    :return: True when the match is servable under the documented schema
    """
    if not isinstance(match, dict):
        return False
    iscc_id = match.get("iscc_id")
    if not (isinstance(iscc_id, str) and ISCC_ID_PATTERN.match(iscc_id)):
        return False
    if not valid_score(match.get("score")):
        return False
    types = match.get("types")
    if not isinstance(types, dict) or not all(valid_score(score) for score in types.values()):
        return False
    metadata = match.get("metadata")
    return metadata is None or isinstance(metadata, dict)


def project_result(raw):
    # type: (bytes) -> dict|None
    """
    Project a backend 2xx body onto the documented IDP response shape.

    Keeps only documented keys — query {iscc_id, iscc_code, units}, matches
    {iscc_id, score, types, metadata} with metadata forwarded whole as the
    designated extension point. Backend-internal fields (chunk_matches) and
    unknown additions are dropped. Returns None when the body is not JSON or
    any kept value is missing or violates the documented shape (valid_query_echo
    / valid_match); the caller treats that as a retryable backend failure so the
    Hub never serves a 200 violating its own schema.

    :param raw: Raw backend response body bytes
    :return: Projected response dict, or None when malformed
    """
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    query = data.get("query")
    matches = data.get("global_matches")
    if not isinstance(query, dict) or not valid_query_echo(query):
        return None
    if not isinstance(matches, list) or not all(valid_match(match) for match in matches):
        return None
    return {
        "query": {key: query[key] for key in QUERY_KEYS if key in query},
        "global_matches": [{key: match[key] for key in MATCH_KEYS if key in match} for match in matches],
    }


def breaker_initial():
    # type: () -> dict
    """Return a fresh closed circuit-breaker state."""
    return {"failures": 0, "open_until": 0.0}


def breaker_open(state, now):
    # type: (dict, float) -> bool
    """
    Return True when the breaker is open (the backend must be skipped) at time now.

    :param state: Breaker state dict {failures, open_until}
    :param now: Current monotonic timestamp
    :return: True when the backend is in its cooldown window
    """
    return now < state["open_until"]


def breaker_failure(state, now, threshold, cooldown):
    # type: (dict, float, int, float) -> dict
    """
    Advance breaker state by one retryable failure, (re)opening it at the threshold.

    Failures at or beyond the threshold each (re)start the cooldown window, so a
    failed probe after cooldown re-opens the breaker immediately while a success
    (handled by resetting to breaker_initial) closes it.

    :param state: Breaker state dict {failures, open_until}
    :param now: Current monotonic timestamp
    :param threshold: Consecutive failures that open the breaker
    :param cooldown: Seconds the breaker stays open
    :return: Advanced breaker state dict
    """
    failures = state["failures"] + 1
    open_until = now + cooldown if failures >= threshold else state["open_until"]
    return {"failures": failures, "open_until": open_until}


####################################################################################################
# I/O shell                                                                                        #
####################################################################################################


class ProxyState:
    """Per-process I/O state for the search proxy, built lazily from current settings."""

    def __init__(self, max_inflight):
        # type: (int) -> None
        """
        Initialize the shared session, in-flight semaphore, and circuit-breaker map.

        :param max_inflight: Concurrent proxied searches allowed per process
        """
        self.session = niquests.Session()
        self.semaphore = threading.BoundedSemaphore(max_inflight)
        self.breakers = {}  # type: dict[str, dict]
        self.lock = threading.Lock()


_proxy_state = None  # type: ProxyState|None
_proxy_state_lock = threading.Lock()


def get_proxy_state():
    # type: () -> ProxyState
    """Return the process-wide ProxyState, building it from current settings on first use."""
    global _proxy_state
    with _proxy_state_lock:
        if _proxy_state is None:
            _proxy_state = ProxyState(settings.ISCC_HUB_SEARCH_MAX_INFLIGHT)
        return _proxy_state


def reset_proxy_state():
    # type: () -> None
    """Drop the process-wide ProxyState so the next request rebuilds it from current settings."""
    global _proxy_state
    with _proxy_state_lock:
        _proxy_state = None


def handle_get(request):
    # type: (HttpRequest) -> HttpResponse
    """
    Handle GET /search — similarity by ISCC-CODE.

    :param request: The incoming HTTP request
    :return: Projected backend response or passthrough error response
    """
    _require_configured()
    iscc_code = request.GET.get("iscc_code")
    if not iscc_code or not ISCC_CODE_PATTERN.match(iscc_code):
        raise BaseApiException("Invalid or missing iscc_code. Expected: ISCC: followed by 16+ base32 characters")
    limit = validate_limit(request.GET.get("limit"))
    params = {"iscc_code": iscc_code}
    if limit is not None:
        params["limit"] = str(limit)
    return _proxied_search("GET", params, None)


def handle_post(request):
    # type: (HttpRequest) -> HttpResponse
    """
    Handle POST /search — similarity by IsccQuery body (forwarded as-is after validation).

    :param request: The incoming HTTP request
    :return: Projected backend response or passthrough error response
    """
    _require_configured()
    validate_query_body(request.body)
    limit = validate_limit(request.GET.get("limit"))
    params = {}
    if limit is not None:
        params["limit"] = str(limit)
    return _proxied_search("POST", params, request.body)


def _require_configured():
    # type: () -> None
    """Raise 404 when no search backend is configured (similarity disabled on this Hub)."""
    if not settings.ISCC_HUB_SEARCH_URLS:
        raise NotFoundError("Similarity search not enabled on this hub")


def _proxied_search(method, params, body):
    # type: (str, dict, bytes|None) -> HttpResponse
    """
    Walk configured backends in order until one yields a definitive answer.

    Skips backends with an open breaker, fails over on retryable outcomes, and
    sheds load with an immediate 503 when the in-flight cap is reached.

    :param method: HTTP method to use against the backend ('GET' or 'POST')
    :param params: Query parameters to forward
    :param body: Raw request body to forward (POST only)
    :return: Hub response built from the first definitive backend answer
    """
    state = get_proxy_state()
    if not state.semaphore.acquire(blocking=False):
        raise SearchUnavailableError("Search backend saturated", retry_after=RETRY_AFTER)
    try:
        for base_url in settings.ISCC_HUB_SEARCH_URLS:
            with state.lock:
                breaker = state.breakers.setdefault(base_url, breaker_initial())
                if breaker_open(breaker, time.monotonic()):
                    continue
            status, content = _call_backend(state.session, method, base_url, params, body)
            verdict = "retryable" if status is None else classify_status(status)
            if verdict == "ok":
                projected = project_result(content or b"")
                if projected is not None:
                    _record_success(state, base_url)
                    return JsonResponse(projected)
                verdict = "retryable"  # malformed 2xx body: not servable as a conformant 200
            if verdict == "passthrough":
                _record_success(state, base_url)
                return HttpResponse(content, status=status, content_type="application/json")
            _record_failure(state, base_url)
        raise SearchUnavailableError("Search backend unavailable", retry_after=RETRY_AFTER)
    finally:
        state.semaphore.release()


def _call_backend(session, method, base_url, params, body):
    # type: (niquests.Session, str, str, dict, bytes|None) -> tuple[int|None, bytes|None]
    """
    Issue one request against a single backend; (None, None) signals a connection-level failure.

    :param session: Shared niquests session (documented thread-safe)
    :param method: HTTP method ('GET' or 'POST')
    :param base_url: Backend base URL
    :param params: Query parameters
    :param body: Raw JSON body for POST
    :return: Tuple of (status_code, content) or (None, None) on timeout/connection error
    """
    url = f"{base_url.rstrip('/')}/indexes/{settings.ISCC_HUB_SEARCH_INDEX}/search"
    headers = {"Accept": "application/json"}
    if settings.ISCC_HUB_SEARCH_API_KEY:
        headers["X-API-Key"] = settings.ISCC_HUB_SEARCH_API_KEY
    timeout = settings.ISCC_HUB_SEARCH_TIMEOUT
    # Redirects are not followed: a 30x reaches classify_status as retryable instead of
    # silently serving (and sending the API key to) an unintended URL.
    try:
        if method == "GET":
            response = session.get(url, params=params, headers=headers, timeout=timeout, allow_redirects=False)
        else:
            headers["Content-Type"] = "application/json"
            response = session.post(
                url, params=params, data=body, headers=headers, timeout=timeout, allow_redirects=False
            )
    except niquests.exceptions.RequestException:
        return None, None
    return response.status_code, response.content


def _record_failure(state, base_url):
    # type: (ProxyState, str) -> None
    """Count one retryable failure against base_url's circuit breaker."""
    with state.lock:
        breaker = state.breakers.setdefault(base_url, breaker_initial())
        state.breakers[base_url] = breaker_failure(
            breaker,
            time.monotonic(),
            settings.ISCC_HUB_SEARCH_CB_FAILS,
            settings.ISCC_HUB_SEARCH_CB_COOLDOWN,
        )


def _record_success(state, base_url):
    # type: (ProxyState, str) -> None
    """Close base_url's circuit breaker; deterministic backend answers count as successes."""
    with state.lock:
        state.breakers[base_url] = breaker_initial()
