"""Schemathesis property-based API testing against OpenAPI specification."""

import pathlib

import pytest
import schemathesis

from iscc_hub.wsgi import application

# Get the OpenAPI schema path
HERE = pathlib.Path(__file__).parent.absolute()
OPENAPI_PATH = HERE.parent / "iscc_hub" / "static" / "openapi.yaml"

# Load schema from YAML file for WSGI testing
schema = schemathesis.openapi.from_path(OPENAPI_PATH.as_posix())


@schema.parametrize()
@pytest.mark.django_db
def test_api_fuzz(case):
    # type: (schemathesis.Case) -> None
    """
    Fuzz test API endpoints against the OpenAPI specification.

    This test generates random valid inputs based on the OpenAPI schema
    and validates that responses conform to the documented specification.

    Note: We accept 422 and 400 status codes as valid for validation errors.
    This follows REST best practices where 422 indicates the request
    was well-formed but contained semantic errors, and 400 indicates
    malformed requests.
    """
    # Test against the WSGI application
    response = case.call(app=application)

    # Accept documented error responses
    if response.status_code in [400, 401, 422]:
        # These are valid error responses per the OpenAPI spec
        return

    # The API should never return 500 errors - all inputs should be handled gracefully
    assert response.status_code != 500, f"Server error (500) - API crashed with body: {case.body}"

    # Validate all other responses against the schema
    case.validate_response(response)
