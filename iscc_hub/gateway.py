from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import uritemplate

from iscc_hub.validators import validate_gateway, validate_url


def preserve_query_params(url, request_url):
    # type: (str, str) -> str
    """
    Append query parameters from request URL to target URL.

    :param url: Target URL to append query parameters to
    :param request_url: Request URL containing query parameters to forward
    :return: URL with query parameters appended
    """
    req_parsed = urlparse(request_url)
    req_qs = parse_qs(req_parsed.query, keep_blank_values=True)

    if not req_qs:
        return url

    res_parsed = urlparse(url)
    # Merge existing query parameters with request query parameters
    existing_qs = parse_qs(res_parsed.query, keep_blank_values=True) if res_parsed.query else {}
    # Request parameters take precedence over existing ones
    merged_qs = {**existing_qs, **req_qs}
    new_query = urlencode(merged_qs, doseq=True)
    return urlunparse(
        (
            res_parsed.scheme,
            res_parsed.netloc,
            res_parsed.path,
            res_parsed.params,
            new_query,
            res_parsed.fragment,
        )
    )


def expand_gateway_url(gateway_url, template_vars, request_url=None):
    # type: (str, dict, str|None) -> str
    """
    Build a gateway URL with the appropriate template substitution or direct redirect.

    This function handles URL template substitution if the gateway URL contains
    template variables (e.g., {iscc_id}, {iscc_code}). If no template variables
    are present, it returns the gateway URL unmodified for direct redirect.

    :param gateway_url: The base gateway URL (may contain template variables)
    :param template_vars: Variables for URI template substitution (iscc_id, iscc_code, datahash)
    :param request_url: Optional request URL for query parameter forwarding
    :return: The final gateway/redirect URL with substitutions and query params applied
    """
    validate_gateway(gateway_url)

    if "{" in gateway_url and "}" in gateway_url:
        result_url = uritemplate.expand(gateway_url, template_vars)
    else:
        # Return non-template URLs unmodified for direct redirect
        result_url = gateway_url

    if request_url:
        result_url = preserve_query_params(result_url, request_url)

    validate_url(result_url)
    return result_url
