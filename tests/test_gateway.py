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
    """Test simple append when URL ends with slash."""
    gateway_url = "https://example.com/path/"
    template_vars = {"iscc_id": "ISCC123", "iscc_code": "CODE456", "datahash": "HASH789"}

    result = expand_gateway_url(gateway_url, template_vars)

    assert result == "https://example.com/path/ISCC123"


def test_expand_gateway_url_simple_append_without_slash():
    # type: () -> None
    """Test simple append when URL doesn't end with slash."""
    gateway_url = "https://example.com/path"
    template_vars = {"iscc_id": "ISCC123", "iscc_code": "CODE456", "datahash": "HASH789"}

    result = expand_gateway_url(gateway_url, template_vars)

    assert result == "https://example.com/path/ISCC123"


def test_expand_gateway_url_simple_append_with_equals():
    # type: () -> None
    """Test simple append when URL ends with equals sign."""
    gateway_url = "https://example.com/path?id="
    template_vars = {"iscc_id": "ISCC123", "iscc_code": "CODE456", "datahash": "HASH789"}

    result = expand_gateway_url(gateway_url, template_vars)

    assert result == "https://example.com/path?id=ISCC123"


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
    """Test merging existing and request query parameters."""
    gateway_url = "https://example.com/path"
    template_vars = {"iscc_id": "ISCC123", "iscc_code": "CODE456", "datahash": "HASH789"}
    request_url = "https://hub.example/iscc/ISCC123?new=param"

    result = expand_gateway_url(gateway_url, template_vars, request_url)

    # First expand adds ISCC123, then query params are added
    assert result == "https://example.com/path/ISCC123?new=param"


def test_expand_gateway_url_duplicate_query_params():
    # type: () -> None
    """Test handling duplicate query parameters."""
    gateway_url = "https://example.com/{iscc_id}"
    template_vars = {"iscc_id": "ISCC123", "iscc_code": "CODE456", "datahash": "HASH789"}
    request_url = "https://hub.example/iscc/ISCC123?tag=foo&tag=bar"

    result = expand_gateway_url(gateway_url, template_vars, request_url)

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


def test_expand_gateway_url_with_fragment():
    # type: () -> None
    """Test preserving URL fragments."""
    gateway_url = "https://example.com/{iscc_id}#section"
    template_vars = {"iscc_id": "ISCC123", "iscc_code": "CODE456", "datahash": "HASH789"}
    request_url = "https://hub.example/iscc/ISCC123?param=value"

    result = expand_gateway_url(gateway_url, template_vars, request_url)

    assert result == "https://example.com/ISCC123?param=value#section"


def test_expand_gateway_url_complex_path():
    # type: () -> None
    """Test with complex URL path structure."""
    gateway_url = "https://example.com/api/v1/content"
    template_vars = {"iscc_id": "ISCC123", "iscc_code": "CODE456", "datahash": "HASH789"}
    request_url = "https://hub.example/iscc/ISCC123?format=json&lang=en"

    result = expand_gateway_url(gateway_url, template_vars, request_url)

    assert result == "https://example.com/api/v1/content/ISCC123?format=json&lang=en"


def test_expand_gateway_url_template_with_existing_query_params():
    # type: () -> None
    """Test merging when template expansion results in URL with query params."""
    # This gateway URL template will expand to include query parameters
    gateway_url = "https://example.com/lookup?iscc={iscc_id}&code={iscc_code}"
    template_vars = {"iscc_id": "ISCC123", "iscc_code": "CODE456", "datahash": "HASH789"}
    request_url = "https://hub.example/iscc/ISCC123?format=json&code=override"

    result = expand_gateway_url(gateway_url, template_vars, request_url)

    # The result should have merged query parameters
    # Original from template: iscc=ISCC123&code=CODE456
    # Added from request: format=json and code=override (extends the existing code param)
    assert "iscc=ISCC123" in result
    assert "format=json" in result
    # code parameter should have both values
    assert "code=CODE456" in result
    assert "code=override" in result
