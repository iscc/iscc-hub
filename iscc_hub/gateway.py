from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import uritemplate

from iscc_hub.validators import validate_gateway, validate_url


def expand_gateway_url(gateway_url, template_vars, request_url=None):
    # type: (str, dict, str|None) -> str
    """
    Build a gateway URL with the appropriate template substitution or appending.

    This function handles URL template substitution if the gateway URL contains
    template variables (e.g., {iscc_id}, {iscc_code}). If no template variables
    are present, it appends the ISCC-ID to the gateway URL.

    :param gateway_url: The base gateway URL (may contain template variables)
    :param template_vars: Veriables for URI template substitution (iscc_id, iscc_code, datahash)
    :param request_url: Optional request URL for redirect URL building
    :return: The final gateway/redirect URL with substitutions and query params applied
    """

    validate_gateway(gateway_url)

    if "{" in gateway_url and "}" in gateway_url:
        result_url = uritemplate.expand(gateway_url, template_vars)
    else:
        # Simple append - add slash if needed
        if not gateway_url.endswith("/") and not gateway_url.endswith("="):
            gateway_url += "/"
        result_url = gateway_url + template_vars["iscc_id"]

    if request_url:
        # Append query params from request URL to the result URL
        req_parsed = urlparse(request_url)
        req_qs = parse_qs(req_parsed.query, keep_blank_values=True)

        if req_qs:
            res_parsed = urlparse(result_url)
            # Since gateway URLs are validated to not contain query components,
            # we can simply use the request query parameters directly
            new_query = urlencode(req_qs, doseq=True)
            result_url = urlunparse(
                (
                    res_parsed.scheme,
                    res_parsed.netloc,
                    res_parsed.path,
                    res_parsed.params,
                    new_query,
                    res_parsed.fragment,
                )
            )

    validate_url(result_url)
    return result_url
