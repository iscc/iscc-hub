"""Test gateway URL expansion functionality."""

import pytest

from iscc_hub.gateway import expand_gateway_url


def test_expand_gateway_url_with_template():
    # type: () -> None
    """Test URL expansion with template variables."""
    gateway_url = "https://example.com/{iscc_id}"
    template_vars = {"iscc_id": "ISCC123", "iscc_code": "CODE456", "datahash": "HASH789"}

    result = expand_gateway_url(gateway_url, template_vars)

    assert result == "https://example.com/ISCC123"


def test_expand_gateway_url_with_multiple_templates():
    # type: () -> None
    """Test URL expansion with multiple template variables."""
    gateway_url = "https://example.com/{iscc_code}/data/{datahash}"
    template_vars = {"iscc_id": "ISCC123", "iscc_code": "CODE456", "datahash": "HASH789"}

    result = expand_gateway_url(gateway_url, template_vars)

    assert result == "https://example.com/CODE456/data/HASH789"


def test_expand_gateway_url_simple_append_with_slash():
    # type: () -> None
    """Test that non-template URL ending with slash is returned unmodified."""
    gateway_url = "https://example.com/path/"
    template_vars = {"iscc_id": "ISCC123", "iscc_code": "CODE456", "datahash": "HASH789"}

    result = expand_gateway_url(gateway_url, template_vars)

    assert result == "https://example.com/path/"


def test_expand_gateway_url_simple_append_without_slash():
    # type: () -> None
    """Test that non-template URL without slash is returned unmodified."""
    gateway_url = "https://example.com/path"
    template_vars = {"iscc_id": "ISCC123", "iscc_code": "CODE456", "datahash": "HASH789"}

    result = expand_gateway_url(gateway_url, template_vars)

    assert result == "https://example.com/path"


def test_expand_gateway_url_simple_append_with_equals():
    # type: () -> None
    """Test that gateway URLs with query parameters are allowed."""
    gateway_url = "https://example.com/path?id="
    template_vars = {"iscc_id": "ISCC123", "iscc_code": "CODE456", "datahash": "HASH789"}

    # Query parameters are now allowed
    result = expand_gateway_url(gateway_url, template_vars)
    assert result == "https://example.com/path?id="


def test_expand_gateway_url_with_request_url_query_params():
    # type: () -> None
    """Test merging query parameters from request URL."""
    gateway_url = "https://example.com/{iscc_id}"
    template_vars = {"iscc_id": "ISCC123", "iscc_code": "CODE456", "datahash": "HASH789"}
    request_url = "https://hub.example/iscc/ISCC123?param1=value1&param2=value2"

    result = expand_gateway_url(gateway_url, template_vars, request_url)

    assert result == "https://example.com/ISCC123?param1=value1&param2=value2"


def test_expand_gateway_url_merge_existing_and_request_params():
    # type: () -> None
    """Test merging request query parameters with non-template URL."""
    gateway_url = "https://example.com/path"
    template_vars = {"iscc_id": "ISCC123", "iscc_code": "CODE456", "datahash": "HASH789"}
    request_url = "https://hub.example/iscc/ISCC123?new=param"

    result = expand_gateway_url(gateway_url, template_vars, request_url)

    # Non-template URL is returned with query params added
    assert result == "https://example.com/path?new=param"


def test_expand_gateway_url_duplicate_query_params():
    # type: () -> None
    """Test handling duplicate query parameters from request URL."""
    gateway_url = "https://example.com/{iscc_id}"
    template_vars = {"iscc_id": "ISCC123", "iscc_code": "CODE456", "datahash": "HASH789"}
    request_url = "https://hub.example/iscc/ISCC123?tag=foo&tag=bar"

    result = expand_gateway_url(gateway_url, template_vars, request_url)

    # Both tag values should be preserved
    assert result == "https://example.com/ISCC123?tag=foo&tag=bar"


def test_expand_gateway_url_blank_query_values():
    # type: () -> None
    """Test preserving blank query parameter values."""
    gateway_url = "https://example.com/{iscc_id}"
    template_vars = {"iscc_id": "ISCC123", "iscc_code": "CODE456", "datahash": "HASH789"}
    request_url = "https://hub.example/iscc/ISCC123?empty=&key=value"

    result = expand_gateway_url(gateway_url, template_vars, request_url)

    assert "empty=" in result
    assert "key=value" in result


def test_expand_gateway_url_no_request_url():
    # type: () -> None
    """Test expansion without request URL."""
    gateway_url = "https://example.com/{iscc_id}"
    template_vars = {"iscc_id": "ISCC123", "iscc_code": "CODE456", "datahash": "HASH789"}

    result = expand_gateway_url(gateway_url, template_vars, None)

    assert result == "https://example.com/ISCC123"


def test_expand_gateway_url_request_url_no_query():
    # type: () -> None
    """Test with request URL that has no query parameters."""
    gateway_url = "https://example.com/{iscc_id}"
    template_vars = {"iscc_id": "ISCC123", "iscc_code": "CODE456", "datahash": "HASH789"}
    request_url = "https://hub.example/iscc/ISCC123"

    result = expand_gateway_url(gateway_url, template_vars, request_url)

    assert result == "https://example.com/ISCC123"


def test_expand_gateway_url_with_fragment_rejected():
    # type: () -> None
    """Test that gateway URLs with fragments are rejected."""
    gateway_url = "https://example.com/{iscc_id}#section"
    template_vars = {"iscc_id": "ISCC123", "iscc_code": "CODE456", "datahash": "HASH789"}
    request_url = "https://hub.example/iscc/ISCC123?param=value"

    # Should raise validation error due to fragment restriction
    with pytest.raises(ValueError, match="restricted URL fragment component"):
        expand_gateway_url(gateway_url, template_vars, request_url)


def test_expand_gateway_url_complex_path():
    # type: () -> None
    """Test with complex URL path structure."""
    gateway_url = "https://example.com/api/v1/content"
    template_vars = {"iscc_id": "ISCC123", "iscc_code": "CODE456", "datahash": "HASH789"}
    request_url = "https://hub.example/iscc/ISCC123?format=json&lang=en"

    result = expand_gateway_url(gateway_url, template_vars, request_url)

    assert result == "https://example.com/api/v1/content?format=json&lang=en"


def test_expand_gateway_url_with_existing_query_params():
    # type: () -> None
    """Test gateway URL with existing query parameters like the user's example."""
    # Example from user: https://omero.iscc.id/webclient/?show=image-53
    gateway_url = "https://omero.iscc.id/webclient/?show=image-53"
    template_vars = {"iscc_id": "ISCC123", "iscc_code": "CODE456", "datahash": "HASH789"}

    # Should work without any issues
    result = expand_gateway_url(gateway_url, template_vars)
    assert result == "https://omero.iscc.id/webclient/?show=image-53"

    # With request URL having additional params
    request_url = "https://hub.example/iscc/ISCC123?format=json"
    result = expand_gateway_url(gateway_url, template_vars, request_url)
    # Request params should be merged with existing ones
    assert "show=image-53" in result
    assert "format=json" in result


def test_expand_gateway_url_template_with_query_params_allowed():
    # type: () -> None
    """Test that gateway URLs with query parameters in templates are allowed."""
    # Gateway URL templates with query parameters are now allowed
    gateway_url = "https://example.com/lookup?iscc={iscc_id}&code={iscc_code}"
    template_vars = {"iscc_id": "ISCC123", "iscc_code": "CODE456", "datahash": "HASH789"}
    request_url = "https://hub.example/iscc/ISCC123?format=json&code=override"

    # Query parameters are now allowed and templates are expanded
    result = expand_gateway_url(gateway_url, template_vars, request_url)
    # Templates expanded, request params override template params
    assert "ISCC123" in result  # From template expansion
    assert "code=override" in result  # Request param overrides template value
    assert "format=json" in result  # Added from request
