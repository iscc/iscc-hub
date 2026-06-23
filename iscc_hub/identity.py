"""
DID identity verification for the declaration write path (Policy B).

This is the only I/O-bearing acceptance policy: it resolves the signature
``controller``'s DID document, caches positive results per worker, and requires
the document to authorize the signing key. It is strict fail-closed — a missing
controller, an unresolvable controller, or a document that does not vouch for the
key all reject the request. The client-controlled ``did:web`` fetch is wrapped in
an SSRF guard so the production client only reaches globally-routable hosts, and the
production client never follows HTTP redirects so a 30x cannot bounce the fetch to a
private address past that host check.

The caller (``iscc_hub.api``) invokes :func:`verify_note_identity` only for
otherwise-authorized writes — after validation and the permission/ownership gate,
and never inside the sequencer transaction.
"""

import ipaddress
import socket
from urllib.parse import urlsplit

import iscc_crypto as icr
import niquests
from django.conf import settings
from django.core.cache import cache
from iscc_crypto.resolve import HttpClient, ResolutionError, resolve

from iscc_hub.exceptions import IdentityError
from iscc_hub.validators import validate_controller_present_did_web

DID_RETRY_AFTER = 5  # Seconds; transient can't-tell hint, mirrors SearchUnavailableError


class RedirectSafeHttpClient:
    """
    Production inner ``HttpClient`` that fetches JSON without following HTTP redirects.

    The SSRF guard in :class:`GuardedHttpClient` only vets the host of the initial URL.
    Following a redirect would let a public ``did:web`` host bounce the fetch to a private
    address behind the guard's back, so this client never follows them: a controller that
    answers with a 3xx is treated as unresolvable (fail-closed) instead of being chased.
    """

    async def get_json(self, url):
        # type: (str) -> dict
        """
        Fetch JSON from a host the guard already vetted, with redirects disabled.

        :param url: The HTTPS URL to fetch (host already checked by the SSRF guard)
        :return: Parsed JSON document
        :raises ResolutionError: If the host answers with a redirect (never followed)
        """
        response = await niquests.aget(
            url, timeout=(5, 10), allow_redirects=False, headers={"User-Agent": "iscc-notary"}
        )
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("location")
            raise ResolutionError(f"Refusing to follow redirect from {url} to {location!r}")
        response.raise_for_status()
        return response.json()


class GuardedHttpClient:
    """
    SSRF-guarded production ``HttpClient`` for client-controlled ``did:web`` fetches.

    Implements the ``async get_json(url)`` protocol expected by ``iscc_crypto.resolve``.
    Before fetching, it resolves the URL host and rejects any address that is not
    globally routable (loopback / private / link-local / reserved / multicast) and any
    unresolvable host, then delegates to a redirect-safe niquests client so a 30x to a
    private address cannot slip past the host check.
    """

    def __init__(self, client=None):
        # type: (HttpClient|None) -> None
        """Wrap an inner HttpClient (the redirect-safe production client by default) used after the guard passes."""
        self._client = client or RedirectSafeHttpClient()  # type: HttpClient

    async def get_json(self, url):
        # type: (str) -> dict
        """
        Fetch JSON only when the URL host resolves exclusively to globally-routable addresses.

        :param url: The HTTPS URL to fetch (built from the client-supplied did:web)
        :return: Parsed JSON document
        :raises ResolutionError: If the host is missing, unresolvable, or not publicly routable
        """
        host = urlsplit(url).hostname
        if not host:
            raise ResolutionError(f"Refusing to fetch URL without a host: {url}")
        guard_public_host(host)
        return await self._client.get_json(url)


def guard_public_host(host):
    # type: (str) -> None
    """
    Reject hosts that resolve to any non-globally-routable address (SSRF guard).

    Fails closed: an unresolvable host or one resolving to any loopback / private /
    link-local / reserved / multicast address raises, so the caller rejects the request.

    :param host: The hostname or IP literal extracted from the target URL
    :raises ResolutionError: If the host is unresolvable or resolves to a non-public address
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as e:
        raise ResolutionError(f"Cannot resolve host {host!r}: {e}") from e
    for addr in {info[4][0] for info in infos}:
        if not ipaddress.ip_address(addr).is_global:
            raise ResolutionError(f"Refusing to fetch from non-public host {host!r} ({addr})")


def http_client():
    # type: () -> HttpClient
    """
    Return the DID HTTP client to use for resolution.

    Defaults to the SSRF-guarded production client; tests inject a local stub via the
    ``ISCC_HUB_DID_HTTP_CLIENT`` setting.

    :return: An object implementing the ``async get_json(url)`` HttpClient protocol
    """
    return getattr(settings, "ISCC_HUB_DID_HTTP_CLIENT", None) or GuardedHttpClient()


def resolve_controller_document(controller):
    # type: (str) -> dict
    """
    Resolve a controller's DID document, caching positive results per worker.

    Only successful resolutions are cached (TTL ``ISCC_HUB_DID_CACHE_TTL``); failures are
    not negatively cached, so recovery is immediate once the controller host is reachable.

    :param controller: The ``did:web`` controller URI to resolve
    :return: The resolved DID document
    :raises ResolutionError: If resolution fails (propagated to the caller for fail-closed handling)
    """
    key = f"did:{controller}"
    document = cache.get(key)
    if document is None:
        document = resolve(controller, http_client=http_client())
        cache.set(key, document, settings.ISCC_HUB_DID_CACHE_TTL)
    return document


def verify_note_identity(note):
    # type: (dict) -> None
    """
    Verify a note's signing key is authorized by its DID controller (Policy B, fail-closed).

    Requires a ``did:web`` controller, resolves it (cached), and requires the document to
    authorize the embedded pubkey. Re-runs signature verification as a side effect of
    ``verify_json`` (already done during validation); this is harmless and cheap relative to
    the network call, and there is no public identity-only entry point in iscc_crypto.

    :param note: The validated IsccNote (with signature) to verify identity for
    :raises IdentityError: did_required (422) if no did:web controller; did_unresolvable (503)
        if the controller cannot be resolved; did_unauthorized (422) if the document does not
        authorize the signing key
    """
    signature = note.get("signature", {})
    validate_controller_present_did_web(signature)
    controller = signature["controller"]
    try:
        document = resolve_controller_document(controller)
    except Exception as e:
        # Can't-tell case (DNS/TLS/timeout/4xx/5xx/malformed-doc/SSRF-guard): fail closed, transient.
        raise IdentityError(
            f"Could not resolve DID controller {controller!r}: {e}",
            code="did_unresolvable",
            status_code=503,
            retry_after=DID_RETRY_AFTER,
        ) from e
    result = icr.verify_json(note, identity_doc=document, raise_on_error=False)
    if result.identity_verified is not True:
        raise IdentityError(
            f"DID controller {controller!r} does not authorize the signing key",
            code="did_unauthorized",
            status_code=422,
        )
