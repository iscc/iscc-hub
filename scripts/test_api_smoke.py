#!/usr/bin/env python
"""
Simple smoke tests for ISCC-HUB API endpoints.

Tests basic connectivity and response codes without complex validation.
Designed for CI/CD pipeline verification.
"""

import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def test_endpoint(url, method="GET", headers=None, data=None, expected_status=None):
    # type: (str, str, dict|None, bytes|None, list|None) -> bool
    """Test a single endpoint and return success status."""
    headers = headers or {}
    headers["Accept"] = "application/json"

    try:
        req = Request(url, data=data, headers=headers, method=method)
        response = urlopen(req)
        status = response.getcode()

        if expected_status:
            if status not in expected_status:
                print(f"❌ {method} {url}: Got {status}, expected one of {expected_status}")
                return False
        print(f"✅ {method} {url}: {status}")
        return True

    except HTTPError as e:
        status = e.code
        if expected_status and status in expected_status:
            print(f"✅ {method} {url}: {status} (expected error)")
            return True
        print(f"❌ {method} {url}: {status} - {e.reason}")
        return False
    except URLError as e:
        print(f"❌ {method} {url}: Connection failed - {e.reason}")
        return False
    except Exception as e:
        print(f"❌ {method} {url}: Unexpected error - {e}")
        return False


def run_smoke_tests():
    # type: () -> int
    """Run basic smoke tests for all API endpoints."""
    base_url = "http://localhost:8000"
    all_passed = True

    print("🔍 Running ISCC-HUB API Smoke Tests...\n")

    # Test health endpoint
    all_passed &= test_endpoint(f"{base_url}/health")

    # Test search endpoint - no parameters (should return 400)
    all_passed &= test_endpoint(f"{base_url}/search", expected_status=[400])

    # Test search endpoint - with valid datahash
    all_passed &= test_endpoint(
        f"{base_url}/search?datahash=1e205ca7815adcb484e9a136c11efe69c1d530176d549b5d18d038eb5280b4b3470c",
        expected_status=[200],
    )

    # Test search endpoint - with valid iscc_code
    all_passed &= test_endpoint(
        f"{base_url}/search?iscc_code=ISCC:KACWN77F73NA44D6EUG3S3QNJIL2BPPQFMW6ZX6CZNOKPAK23S2IJ2I",
        expected_status=[200],
    )

    # Test declaration endpoint - missing data (should return 400)
    all_passed &= test_endpoint(
        f"{base_url}/declaration",
        method="POST",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        expected_status=[400, 422],
    )

    # Test delete endpoint - non-existent ID (should return 404)
    all_passed &= test_endpoint(
        f"{base_url}/declaration/ISCC:MAAAAAAAAAAAAAAA",
        method="DELETE",
        data=b'{"iscc_id":"ISCC:MAAAAAAAAAAAAAAA"}',
        headers={"Content-Type": "application/json"},
        expected_status=[400, 404, 422],
    )

    # Test DID document endpoint
    all_passed &= test_endpoint(f"{base_url}/.well-known/did.json")

    print("\n" + "=" * 50)
    if all_passed:
        print("✅ All smoke tests passed!")
        return 0
    else:
        print("❌ Some tests failed!")
        return 1


if __name__ == "__main__":
    sys.exit(run_smoke_tests())
