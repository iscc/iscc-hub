import uritemplate


def expand_gateway_url(gateway_url, iscc_id, iscc_code):
    """
    Build a gateway URL with appropriate template substitution or appending.

    This function handles URL template substitution if the gateway URL contains
    template variables (e.g., {iscc_id}, {iscc_code}). If no template variables
    are present, it appends the ISCC-ID to the gateway URL.

    :param gateway_url: The base gateway URL (may contain template variables)
    :param iscc_id: The ISCC-ID to substitute or append
    :param iscc_code: The ISCC-CODE to use in template substitution
    :return: The final gateway URL with substitutions applied
    """
    # Prepare template variables
    template_vars = {"iscc_id": str(iscc_id), "iscc_code": iscc_code}

    # Check if the gateway URL contains template variables
    if "{" in gateway_url and "}" in gateway_url:
        # Use uritemplate for substitution
        return uritemplate.expand(gateway_url, template_vars)
    else:
        # Simple append - add slash if needed
        if not gateway_url.endswith("/") and not gateway_url.endswith("="):
            gateway_url += "/"
        return gateway_url + str(iscc_id)
