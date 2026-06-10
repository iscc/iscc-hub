"""
Tests for the /search similarity proxy (iscc_hub/search_proxy.py).

Pure policy-core tests run without I/O; integration tests run against real local
stub backends (tests.conftest.StubSearchBackend) — no mocking of the HTTP client.
"""

import json
import socket

import pytest
from django.test import override_settings

from iscc_hub.exceptions import BaseApiException
from iscc_hub.search_proxy import (
    breaker_failure,
    breaker_initial,
    breaker_open,
    classify_status,
    get_proxy_state,
    project_result,
    validate_limit,
    validate_query_body,
)
from tests.conftest import STUB_SEARCH_SUCCESS

VALID_CODE = "ISCC:KECYCMZIOY36XXGZ7S6QJQ2AEEXPOVEHZYPK6GMSFLU3WF54UPZMTPY"
VALID_ID = "ISCC:MAIGIIFJRDGEQQAA"

# The documented IDP shape the hub must emit for the canned stub success body
EXPECTED_PROJECTION = {
    "query": {"iscc_code": "ISCC:KECYCMZIOY36XXGZ7S6QJQ2AEEXPOVEHZYPK6GMSFLU3WF54UPZMTPY"},
    "global_matches": [
        {
            "iscc_id": "ISCC:MAIGIIFJRDGEQQAA",
            "score": 0.97,
            "types": {"CONTENT_TEXT_V0": 1.0, "DATA_NONE_V0": 0.5},
            "metadata": {
                "name": "Example Article",
                "gateway": "https://example.com/articles/123",
                "custom_ext": "kept",
            },
        },
        {
            "iscc_id": "ISCC:MAIGXXFZRDGEQQBB",
            "score": 0.75,
            "types": {"CONTENT_TEXT_V0": 1.0},
            "metadata": None,
        },
    ],
}


def unused_port_url():
    # type: () -> str
    """Return a URL on a local port with no listener (fast connection refused)."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return f"http://127.0.0.1:{port}"


####################################################################################################
# Pure policy core                                                                                 #
####################################################################################################


def test_classify_status():
    # type: () -> None
    """2xx is ok, 400/404/422 pass through, everything else is retryable (L10)."""
    assert classify_status(200) == "ok"
    assert classify_status(204) == "ok"
    for status in (400, 404, 422):
        assert classify_status(status) == "passthrough"
    for status in (301, 401, 403, 429, 500, 502, 503):
        assert classify_status(status) == "retryable"


def test_breaker_transitions():
    # type: () -> None
    """Breaker opens at the threshold, allows a probe after cooldown, re-opens on failed probe."""
    threshold, cooldown = 3, 15.0
    state = breaker_initial()
    assert not breaker_open(state, now=100.0)

    # Failures below the threshold leave the breaker closed
    state = breaker_failure(state, now=100.0, threshold=threshold, cooldown=cooldown)
    state = breaker_failure(state, now=101.0, threshold=threshold, cooldown=cooldown)
    assert state["failures"] == 2
    assert not breaker_open(state, now=101.0)

    # The threshold failure opens it for the cooldown window
    state = breaker_failure(state, now=102.0, threshold=threshold, cooldown=cooldown)
    assert breaker_open(state, now=102.0)
    assert breaker_open(state, now=102.0 + cooldown - 0.1)
    # After cooldown the backend may be probed again
    assert not breaker_open(state, now=102.0 + cooldown)

    # A failed probe re-opens immediately (consecutive count is already at the threshold)
    state = breaker_failure(state, now=120.0, threshold=threshold, cooldown=cooldown)
    assert breaker_open(state, now=120.0)

    # A success (deterministic answer or 2xx) closes and resets the count
    state = breaker_initial()
    assert state == {"failures": 0, "open_until": 0.0}


def test_validate_limit():
    # type: () -> None
    """Absent limit passes through as None; valid values parse; out-of-range/garbage -> 400."""
    assert validate_limit(None) is None
    assert validate_limit("1") == 1
    assert validate_limit("100") == 100
    for raw in ("0", "101", "-5", "abc", ""):
        with pytest.raises(BaseApiException, match="limit must be an integer"):
            validate_limit(raw)


def test_validate_query_body_accepts_documented_fields():
    # type: () -> None
    """Each documented query mode validates, alone and combined."""
    assert validate_query_body(json.dumps({"iscc_code": VALID_CODE}).encode()) == {"iscc_code": VALID_CODE}
    assert validate_query_body(json.dumps({"iscc_id": VALID_ID}).encode()) == {"iscc_id": VALID_ID}
    body = {"units": ["ISCC:AAAUHBUDQUT3LPWR"], "iscc_code": VALID_CODE}
    assert validate_query_body(json.dumps(body).encode()) == body


def test_validate_query_body_rejects_unknown_keys():
    # type: () -> None
    """Any top-level key outside the allow-list is rejected, simprints included (L6)."""
    for key in ("simprints", "foo", "iscc_codes"):
        with pytest.raises(BaseApiException, match=f"Unknown query field.*{key}"):
            validate_query_body(json.dumps({"iscc_code": VALID_CODE, key: {}}).encode())


def test_validate_query_body_rejects_malformed():
    # type: () -> None
    """Bad JSON, non-objects, empty queries, and malformed field values are rejected."""
    with pytest.raises(BaseApiException, match="valid JSON"):
        validate_query_body(b"not json{")
    with pytest.raises(BaseApiException, match="JSON object"):
        validate_query_body(b'["iscc_code"]')
    with pytest.raises(BaseApiException, match="At least one of"):
        validate_query_body(b"{}")
    with pytest.raises(BaseApiException, match="At least one of"):
        validate_query_body(b'{"iscc_code": null}')
    with pytest.raises(BaseApiException, match="Invalid iscc_id format"):
        validate_query_body(json.dumps({"iscc_id": "ISCC:TOOSHORT"}).encode())
    with pytest.raises(BaseApiException, match="Invalid iscc_id format"):
        validate_query_body(json.dumps({"iscc_id": 42}).encode())
    with pytest.raises(BaseApiException, match="Invalid iscc_code format"):
        validate_query_body(json.dumps({"iscc_code": "not-an-iscc"}).encode())
    with pytest.raises(BaseApiException, match="units must be a non-empty array"):
        validate_query_body(json.dumps({"units": []}).encode())
    with pytest.raises(BaseApiException, match="units must be a non-empty array"):
        validate_query_body(json.dumps({"units": "ISCC:AAAUHBUDQUT3LPWR"}).encode())


def test_project_result_happy():
    # type: () -> None
    """Projection keeps exactly the documented keys and forwards metadata whole (L11)."""
    raw = json.dumps(STUB_SEARCH_SUCCESS).encode("utf-8")
    assert project_result(raw) == EXPECTED_PROJECTION


def test_project_result_malformed():
    # type: () -> None
    """Non-JSON bodies and missing required keys signal a retryable backend failure."""
    assert project_result(b"not json") is None
    assert project_result(b'"a string"') is None
    assert project_result(b'{"global_matches": []}') is None  # query missing
    assert project_result(b'{"query": {}}') is None  # global_matches missing
    assert project_result(b'{"query": "x", "global_matches": []}') is None  # query not an object
    assert project_result(b'{"query": {}, "global_matches": "x"}') is None  # matches not a list
    assert project_result(b'{"query": {}, "global_matches": [42]}') is None  # match not an object
    no_score = {"query": {}, "global_matches": [{"iscc_id": VALID_ID, "types": {}}]}
    assert project_result(json.dumps(no_score).encode()) is None


def result_body(match_overrides=None, query_overrides=None):
    # type: (dict|None, dict|None) -> bytes
    """Serialize a minimal valid backend search result with optional field overrides."""
    match = {"iscc_id": VALID_ID, "score": 0.9, "types": {"CONTENT_TEXT_V0": 1.0}}
    match.update(match_overrides or {})
    query = {"iscc_code": VALID_CODE}
    query.update(query_overrides or {})
    return json.dumps({"query": query, "global_matches": [match]}).encode()


def test_project_result_rejects_invalid_match_values():
    # type: () -> None
    """Matches with schema-violating values are rejected like any malformed body (L11)."""
    assert project_result(result_body()) is not None  # baseline accepted
    assert project_result(result_body(match_overrides={"metadata": {"name": "x"}})) is not None
    invalid = (
        {"iscc_id": "ISCC:invalid"},
        {"iscc_id": 42},
        {"score": "0.9"},
        {"score": True},
        {"score": 1.5},
        {"score": -0.1},
        {"types": ["CONTENT_TEXT_V0"]},
        {"types": {"CONTENT_TEXT_V0": "1.0"}},
        {"types": {"CONTENT_TEXT_V0": 2.0}},
        {"metadata": "not-an-object"},
    )
    for overrides in invalid:
        assert project_result(result_body(match_overrides=overrides)) is None


def test_project_result_rejects_invalid_query_echo():
    # type: () -> None
    """Echoed query values that violate the IsccQuery shape are rejected (L11)."""
    accepted = (
        {"iscc_id": VALID_ID},  # backend-resolved iscc_id
        {"units": ["ISCC:AAAUHBUDQUT3LPWR"]},
    )
    for overrides in accepted:
        assert project_result(result_body(query_overrides=overrides)) is not None
    invalid = (
        {"iscc_id": "not-an-iscc"},
        {"iscc_id": 42},
        {"iscc_code": "not-an-iscc"},
        {"iscc_code": 42},
        {"units": []},
        {"units": "ISCC:AAAUHBUDQUT3LPWR"},
        {"units": [1, 2]},
    )
    for overrides in invalid:
        assert project_result(result_body(query_overrides=overrides)) is None


####################################################################################################
# Integration (real stub backends)                                                                 #
####################################################################################################


@pytest.mark.django_db
def test_search_unconfigured_returns_404(api_client, proxy_state_reset):
    # type: (object, object) -> None
    """Without configured backends, similarity search is a 404 on this hub (L4/L7)."""
    with override_settings(ISCC_HUB_SEARCH_URLS=[]):
        for response in (
            api_client.get(f"/search?iscc_code={VALID_CODE}"),
            api_client.post("/search", data=json.dumps({"iscc_code": VALID_CODE})),
        ):
            assert response.status_code == 404
            assert response.json()["error"]["code"] == "not_found"
            assert "not enabled" in response.json()["error"]["message"]


@pytest.mark.django_db
def test_search_get_happy_projection(api_client, search_stub):
    # type: (object, object) -> None
    """GET /search proxies to the backend index and projects the response (L11)."""
    with override_settings(ISCC_HUB_SEARCH_URLS=[search_stub.url]):
        response = api_client.get(f"/search?iscc_code={VALID_CODE}")

    assert response.status_code == 200
    assert response.json() == EXPECTED_PROJECTION
    assert len(search_stub.requests) == 1
    recorded = search_stub.requests[0]
    assert recorded["method"] == "GET"
    assert recorded["path"] == "/indexes/idptest/search"  # realm 0 derives idptest
    assert "iscc_code=" in recorded["query"]
    assert "limit" not in recorded["query"]


@pytest.mark.django_db
def test_search_post_happy_forwards_body_verbatim(api_client, search_stub):
    # type: (object, object) -> None
    """POST /search forwards the raw body as-is (L5) and projects the success response."""
    body = json.dumps({"iscc_code": VALID_CODE})
    with override_settings(ISCC_HUB_SEARCH_URLS=[search_stub.url]):
        response = api_client.post("/search", data=body)

    assert response.status_code == 200
    assert response.json() == EXPECTED_PROJECTION
    recorded = search_stub.requests[0]
    assert recorded["method"] == "POST"
    assert recorded["body"] == body.encode("utf-8")


@pytest.mark.django_db
def test_search_post_query_modes(api_client, search_stub):
    # type: (object, object) -> None
    """iscc_id (more-like-this) and units queries are accepted and forwarded."""
    with override_settings(ISCC_HUB_SEARCH_URLS=[search_stub.url]):
        for body in ({"iscc_id": VALID_ID}, {"units": ["ISCC:AAAUHBUDQUT3LPWR"]}):
            response = api_client.post("/search", data=json.dumps(body))
            assert response.status_code == 200


@pytest.mark.django_db
def test_search_post_rejects_unknown_top_level_keys(api_client, search_stub):
    # type: (object, object) -> None
    """Unknown top-level body keys (simprints included) yield 400 without a backend call (L6)."""
    with override_settings(ISCC_HUB_SEARCH_URLS=[search_stub.url]):
        for key in ("simprints", "foo", "iscc_codes"):
            response = api_client.post("/search", data=json.dumps({"iscc_code": VALID_CODE, key: {}}))
            assert response.status_code == 400
            assert key in response.json()["error"]["message"]
    assert search_stub.requests == []


@pytest.mark.django_db
def test_search_post_simprints_inside_value_not_rejected(api_client, search_stub):
    # type: (object, object) -> None
    """The allow-list is a key check, not a substring scan: 'simprints' in a value forwards."""
    body = json.dumps({"units": ["simprints"]})
    with override_settings(ISCC_HUB_SEARCH_URLS=[search_stub.url]):
        response = api_client.post("/search", data=body)

    assert response.status_code == 200
    assert b"simprints" in search_stub.requests[0]["body"]


@pytest.mark.django_db
def test_search_get_validation_errors(api_client, search_stub):
    # type: (object, object) -> None
    """Missing or malformed iscc_code yields 400 before any backend call."""
    with override_settings(ISCC_HUB_SEARCH_URLS=[search_stub.url]):
        for path in ("/search", "/search?iscc_code=not-an-iscc"):
            response = api_client.get(path)
            assert response.status_code == 400
            assert "iscc_code" in response.json()["error"]["message"]
    assert search_stub.requests == []


@pytest.mark.django_db
def test_search_limit_validation_and_forwarding(api_client, search_stub):
    # type: (object, object) -> None
    """Valid limit values are forwarded on the wire; out-of-range yields 400, no backend call (L8)."""
    with override_settings(ISCC_HUB_SEARCH_URLS=[search_stub.url]):
        response = api_client.get(f"/search?iscc_code={VALID_CODE}&limit=5")
        assert response.status_code == 200
        assert "limit=5" in search_stub.requests[0]["query"]

        response = api_client.post("/search?limit=7", data=json.dumps({"iscc_code": VALID_CODE}))
        assert response.status_code == 200
        assert "limit=7" in search_stub.requests[1]["query"]

        for bad in ("0", "101", "abc"):
            response = api_client.get(f"/search?iscc_code={VALID_CODE}&limit={bad}")
            assert response.status_code == 400
    assert len(search_stub.requests) == 2


@pytest.mark.django_db
def test_search_backend_400_passthrough_no_failover(api_client, search_stub, search_stub2):
    # type: (object, object, object) -> None
    """A backend 400 is deterministic: forwarded verbatim, no failover."""
    search_stub.status = 400
    search_stub.body = b'{"detail": "bad query"}'
    with override_settings(ISCC_HUB_SEARCH_URLS=[search_stub.url, search_stub2.url]):
        response = api_client.get(f"/search?iscc_code={VALID_CODE}")

    assert response.status_code == 400
    assert response.json() == {"detail": "bad query"}
    assert len(search_stub.requests) == 1
    assert search_stub2.requests == []


@pytest.mark.django_db
def test_search_backend_404_passthrough_no_failover(api_client, search_stub, search_stub2):
    # type: (object, object, object) -> None
    """A backend 404 (reference/index not found) is forwarded as 404, never laundered into 503."""
    search_stub.status = 404
    search_stub.body = b'{"detail": "iscc_id not indexed"}'
    with override_settings(ISCC_HUB_SEARCH_URLS=[search_stub.url, search_stub2.url]):
        response = api_client.post("/search", data=json.dumps({"iscc_id": VALID_ID}))

    assert response.status_code == 404
    assert response.json() == {"detail": "iscc_id not indexed"}
    assert len(search_stub.requests) == 1
    assert search_stub2.requests == []


@pytest.mark.django_db
def test_search_backend_422_passthrough_resets_breaker(api_client, search_stub):
    # type: (object, object) -> None
    """A 422 passes through without failover and resets the consecutive-failure count."""
    with override_settings(
        ISCC_HUB_SEARCH_URLS=[search_stub.url],
        ISCC_HUB_SEARCH_CB_FAILS=2,
        ISCC_HUB_SEARCH_CB_COOLDOWN=300,
    ):
        search_stub.status = 500
        assert api_client.get(f"/search?iscc_code={VALID_CODE}").status_code == 503  # failures=1

        search_stub.status = 422
        search_stub.body = b'{"detail": "validation error"}'
        response = api_client.get(f"/search?iscc_code={VALID_CODE}")
        assert response.status_code == 422
        assert response.json() == {"detail": "validation error"}  # passthrough resets the count

        search_stub.status = 500
        search_stub.body = None
        assert api_client.get(f"/search?iscc_code={VALID_CODE}").status_code == 503  # failures=1
        assert api_client.get(f"/search?iscc_code={VALID_CODE}").status_code == 503  # failures=2 -> open

        assert api_client.get(f"/search?iscc_code={VALID_CODE}").status_code == 503  # breaker skips
    assert len(search_stub.requests) == 4  # the last request never reached the backend


@pytest.mark.django_db
def test_search_failover_to_second_backend(api_client, search_stub, search_stub2):
    # type: (object, object, object) -> None
    """A 5xx on the first backend fails over to the second (L2)."""
    search_stub.status = 500
    with override_settings(ISCC_HUB_SEARCH_URLS=[search_stub.url, search_stub2.url]):
        response = api_client.get(f"/search?iscc_code={VALID_CODE}")

    assert response.status_code == 200
    assert response.json() == EXPECTED_PROJECTION
    assert len(search_stub.requests) == 1
    assert len(search_stub2.requests) == 1


@pytest.mark.django_db
def test_search_backend_redirect_not_followed(api_client, search_stub, search_stub2):
    # type: (object, object, object) -> None
    """A 30x is retryable and never followed: the Hub must not serve from an unintended URL."""
    search_stub.redirect_to = f"{search_stub2.url}/indexes/idptest/search"
    with override_settings(ISCC_HUB_SEARCH_URLS=[search_stub.url]):
        response = api_client.get(f"/search?iscc_code={VALID_CODE}")

    assert response.status_code == 503  # the only configured backend redirected -> unavailable
    assert len(search_stub.requests) == 1
    assert search_stub2.requests == []  # the redirect target was never contacted


@pytest.mark.django_db
def test_search_non_json_2xx_is_retryable(api_client, search_stub, search_stub2):
    # type: (object, object, object) -> None
    """A 2xx body that fails to parse as JSON fails over; alone it becomes an honest 503."""
    search_stub.body = b"<html>not json</html>"
    with override_settings(ISCC_HUB_SEARCH_URLS=[search_stub.url, search_stub2.url]):
        response = api_client.get(f"/search?iscc_code={VALID_CODE}")
        assert response.status_code == 200  # served by the second backend

    with override_settings(ISCC_HUB_SEARCH_URLS=[search_stub.url]):
        response = api_client.get(f"/search?iscc_code={VALID_CODE}")
        assert response.status_code == 503


@pytest.mark.django_db
def test_search_2xx_missing_required_key_is_retryable(api_client, search_stub):
    # type: (object, object) -> None
    """A 2xx body missing a required documented key is never served as a 200."""
    with override_settings(ISCC_HUB_SEARCH_URLS=[search_stub.url]):
        search_stub.body = json.dumps({"query": {}}).encode()  # no global_matches
        assert api_client.get(f"/search?iscc_code={VALID_CODE}").status_code == 503

        no_score = {"query": {}, "global_matches": [{"iscc_id": VALID_ID, "types": {}}]}
        search_stub.body = json.dumps(no_score).encode()
        assert api_client.get(f"/search?iscc_code={VALID_CODE}").status_code == 503


@pytest.mark.django_db
def test_search_all_backends_down_returns_503(api_client, proxy_state_reset):
    # type: (object, object) -> None
    """Connection errors on all backends yield 503 with Retry-After and the error envelope (L3)."""
    with override_settings(ISCC_HUB_SEARCH_URLS=[unused_port_url(), unused_port_url()]):
        response = api_client.get(f"/search?iscc_code={VALID_CODE}")

    assert response.status_code == 503
    assert response["Retry-After"] == "5"
    assert response.json()["error"]["code"] == "search_unavailable"
    assert "unavailable" in response.json()["error"]["message"]


@pytest.mark.django_db
def test_search_backend_timeout_returns_503(api_client, search_stub):
    # type: (object, object) -> None
    """A backend hanging past the configured timeout counts as a retryable failure."""
    search_stub.delay = 1.0
    with override_settings(ISCC_HUB_SEARCH_URLS=[search_stub.url], ISCC_HUB_SEARCH_TIMEOUT=0.25):
        response = api_client.get(f"/search?iscc_code={VALID_CODE}")

    assert response.status_code == 503
    assert response["Retry-After"] == "5"


@pytest.mark.django_db
def test_search_saturation_returns_503(api_client, search_stub):
    # type: (object, object) -> None
    """When the in-flight cap is exhausted the hub sheds load immediately (no queuing)."""
    with override_settings(ISCC_HUB_SEARCH_URLS=[search_stub.url], ISCC_HUB_SEARCH_MAX_INFLIGHT=1):
        state = get_proxy_state()
        assert state.semaphore.acquire(blocking=False)  # occupy the single slot
        try:
            response = api_client.get(f"/search?iscc_code={VALID_CODE}")
        finally:
            state.semaphore.release()

    assert response.status_code == 503
    assert response["Retry-After"] == "5"
    assert search_stub.requests == []


@pytest.mark.django_db
def test_search_circuit_breaker_skips_open_backend(api_client, search_stub):
    # type: (object, object) -> None
    """After CB_FAILS consecutive failures the backend is skipped until cooldown."""
    search_stub.status = 500
    with override_settings(
        ISCC_HUB_SEARCH_URLS=[search_stub.url],
        ISCC_HUB_SEARCH_CB_FAILS=2,
        ISCC_HUB_SEARCH_CB_COOLDOWN=300,
    ):
        for _ in range(2):
            assert api_client.get(f"/search?iscc_code={VALID_CODE}").status_code == 503
        assert len(search_stub.requests) == 2

        assert api_client.get(f"/search?iscc_code={VALID_CODE}").status_code == 503
    assert len(search_stub.requests) == 2  # breaker open: no further backend call


@pytest.mark.django_db
def test_search_api_key_forwarded_when_configured(api_client, search_stub):
    # type: (object, object) -> None
    """The configured API key is sent as X-API-Key and satisfies a key-requiring backend."""
    search_stub.required_api_key = "sekret"
    with override_settings(ISCC_HUB_SEARCH_URLS=[search_stub.url], ISCC_HUB_SEARCH_API_KEY="sekret"):
        response = api_client.get(f"/search?iscc_code={VALID_CODE}")

    assert response.status_code == 200
    assert search_stub.requests[0]["headers"].get("x-api-key") == "sekret"


@pytest.mark.django_db
def test_search_api_key_absent_when_unconfigured(api_client, search_stub, search_stub2):
    # type: (object, object, object) -> None
    """Without a configured key none is sent; a backend 401 is retryable (failover, then 503)."""
    search_stub.required_api_key = "sekret"
    with override_settings(ISCC_HUB_SEARCH_URLS=[search_stub.url, search_stub2.url]):
        response = api_client.get(f"/search?iscc_code={VALID_CODE}")
        assert response.status_code == 200  # 401 on the first backend failed over to the second
        assert "x-api-key" not in search_stub.requests[0]["headers"]

    with override_settings(ISCC_HUB_SEARCH_URLS=[search_stub.url]):
        response = api_client.get(f"/search?iscc_code={VALID_CODE}")
        assert response.status_code == 503  # all-401 means no backend can serve right now


@pytest.mark.django_db
def test_search_index_name_override(api_client, search_stub):
    # type: (object, object) -> None
    """ISCC_HUB_SEARCH_INDEX overrides the network-derived backend index name."""
    from django.conf import settings

    assert settings.ISCC_HUB_SEARCH_INDEX == "idptest"  # realm 0 (testnet) derivation
    with override_settings(ISCC_HUB_SEARCH_URLS=[search_stub.url], ISCC_HUB_SEARCH_INDEX="custom"):
        response = api_client.get(f"/search?iscc_code={VALID_CODE}")

    assert response.status_code == 200
    assert search_stub.requests[0]["path"] == "/indexes/custom/search"
