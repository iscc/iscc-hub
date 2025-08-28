"""TSA (RFC 3161) timestamping demo using tsp-client library."""

import hashlib
import os
import time

from tsp_client import SigningSettings, TSPSigner, TSPVerifier

# List of public TSA servers for testing - ordered by reliability/preference
TSA_SERVERS = [
    {
        "name": "DigiCert",
        "url": "http://timestamp.digicert.com",
        "description": "Default DigiCert TSA - reliable but HTTP only",
        "type": "trusted",
    },
    {
        "name": "rfc3161.ai.moda",
        "url": "http://rfc3161.ai.moda",
        "description": "High uptime with automatic failovers, serves millions of requests",
        "type": "trusted",
    },
    {
        "name": "Sectigo",
        "url": "http://timestamp.sectigo.com",
        "description": "Reliable commercial TSA with good uptime",
        "type": "trusted",
    },
    {
        "name": "Sectigo HTTPS",
        "url": "https://timestamp.sectigo.com",
        "description": "HTTPS endpoint but may have throttling",
        "type": "trusted",
    },
    {
        "name": "Entrust",
        "url": "http://timestamp.entrust.net/TSS/RFC3161sha2TS",
        "description": "Entrust TSA with SHA-2 support",
        "type": "trusted",
    },
    {
        "name": "IdenTrust",
        "url": "http://timestamp.identrust.com",
        "description": "IdenTrust TSA service",
        "type": "trusted",
    },
    {"name": "SSL.com", "url": "http://ts.ssl.com", "description": "SSL.com timestamp service", "type": "trusted"},
    {
        "name": "SwissSign",
        "url": "http://tsa.swisssign.net",
        "description": "SwissSign TSA service",
        "type": "trusted",
    },
    {
        "name": "ACCV Spain",
        "url": "http://tss.accv.es:8318/tsa",
        "description": "Qualified EU TSA from Spain",
        "type": "qualified",
    },
    {
        "name": "Belgium eID",
        "url": "http://tsa.belgium.be/connect",
        "description": "Qualified EU TSA from Belgium",
        "type": "qualified",
    },
    {
        "name": "FreeTSA",
        "url": "https://freetsa.org/tsr",
        "description": "Free TSA - known to have certificate validation issues with tsp-client",
        "type": "untrusted",
    },
]


def test_tsa_server(server_info, test_data):
    # type: (dict[str, str], bytes) -> tuple[bool, str, float]
    """
    Test a TSA server with sample data.

    :param server_info: Dictionary with server information
    :param test_data: Test data to timestamp
    :return: Tuple of (success, message, response_time)
    """
    try:
        start_time = time.time()

        # Create signing settings with the custom TSA server
        settings = SigningSettings(tsp_server=server_info["url"])
        signer = TSPSigner()

        # Create timestamp
        timestamp_token = signer.sign(test_data, signing_settings=settings)

        # Verify timestamp
        verifier = TSPVerifier()
        is_valid = verifier.verify(timestamp_token, message=test_data)

        response_time = time.time() - start_time

        if is_valid:
            return True, f"✓ Success ({len(timestamp_token)} bytes)", response_time
        else:
            return False, "✗ Verification failed", response_time

    except Exception as e:
        response_time = time.time() - start_time
        error_msg = str(e)[:100]  # Truncate long error messages
        return False, f"✗ Error: {error_msg}", response_time


def test_all_tsa_servers():
    # type: () -> list[dict]
    """
    Test all configured TSA servers and return results.

    :return: List of test results for each server
    """
    print("=== TSA Server Testing ===\n")

    # Create test data
    test_data = os.urandom(32)
    print(f"Test data: {test_data.hex()[:32]}... ({len(test_data)} bytes)")
    print(f"SHA-256: {hashlib.sha256(test_data).hexdigest()}\n")

    results = []

    print(f"Testing {len(TSA_SERVERS)} TSA servers...\n")

    for i, server in enumerate(TSA_SERVERS, 1):
        print(f"[{i:2d}/{len(TSA_SERVERS)}] {server['name']} ({server['type']})")
        print(f"       URL: {server['url']}")
        print(f"       {server['description']}")

        success, message, response_time = test_tsa_server(server, test_data)

        result = {
            "name": server["name"],
            "url": server["url"],
            "type": server["type"],
            "success": success,
            "message": message,
            "response_time": response_time,
            "description": server["description"],
        }
        results.append(result)

        print(f"       Result: {message} ({response_time:.2f}s)")
        print()

    return results


def print_summary(results):
    # type: (list[dict]) -> None
    """
    Print a summary of TSA test results.

    :param results: List of test results
    """
    print("=== TSA Test Summary ===\n")

    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]

    print(f"Successful: {len(successful)}/{len(results)}")
    print(f"Failed: {len(failed)}/{len(results)}\n")

    if successful:
        print("✓ Working TSA Servers (recommended for production):")
        successful.sort(key=lambda x: x["response_time"])
        for result in successful:
            print(f"  {result['name']:<20} {result['response_time']:6.2f}s  {result['url']}")
        print()

    if failed:
        print("✗ Failed TSA Servers:")
        for result in failed:
            print(f"  {result['name']:<20} {result['message']}")
        print()

    print("=== Recommendations for Production ===")
    if successful:
        fastest = successful[0]
        print(f"Fastest server: {fastest['name']} ({fastest['response_time']:.2f}s)")

        # Filter by type for recommendations
        [r for r in successful if r["type"] == "trusted"]
        [r for r in successful if r["type"] == "qualified"]

        print("\nRecommended fallback order (fastest first):")
        for i, result in enumerate(successful[:5], 1):  # Top 5
            print(f"  {i}. {result['name']} - {result['url']}")
    else:
        print("No working TSA servers found. Check network connectivity.")


def demo_basic_usage():
    # type: () -> None
    """
    Original demo showing basic tsp-client library usage with DigiCert.
    """
    print("=== TSA Timestamping Demo using tsp-client ===\n")
    print("This demo shows how tsp-client simplifies RFC 3161 timestamping")
    print("compared to the manual implementation in timestamp_tsa.py\n")

    # 1) Create test data
    test_data = os.urandom(32)
    print(f"Test data: {test_data.hex()[:32]}... ({len(test_data)} bytes)")
    print(f"SHA-256: {hashlib.sha256(test_data).hexdigest()}\n")

    # 2) Create timestamp with just 2 lines of code
    print("--- Creating Timestamp (2 lines of code) ---")
    signer = TSPSigner()
    timestamp_token = signer.sign(test_data)
    print(f"✓ Timestamp created ({len(timestamp_token)} bytes)")
    print("  TSA: DigiCert (default)")
    print("  Note: tsp-client handles all RFC 3161 protocol details internally\n")

    # 3) Save timestamp
    timestamp_file = f"timestamp_{test_data.hex()[:16]}.tsr"
    with open(timestamp_file, "wb") as f:
        f.write(timestamp_token)
    print(f"Saved timestamp to {timestamp_file}\n")

    # 4) Verify timestamp with just 2 lines of code
    print("--- Verifying Timestamp (2 lines of code) ---")
    verifier = TSPVerifier()
    is_valid = verifier.verify(timestamp_token, message=test_data)

    if is_valid:
        print("✓ Timestamp verified successfully")
        print("  The data was timestamped by DigiCert TSA")
        print(f"  Cryptographic proof stored in {timestamp_file}\n")
    else:
        print("✗ Timestamp verification failed\n")
        return

    # 5) Test with modified data (should fail)
    print("--- Testing Tamper Detection ---")
    modified_data = test_data[:-1] + b"\x00"
    print("Modified last byte of data")

    try:
        is_valid = verifier.verify(timestamp_token, message=modified_data)
        if not is_valid:
            print("✓ Tampering detected - verification correctly failed")
    except Exception as e:
        print(f"✓ Tampering detected: {str(e)[:60]}...")

    print("\n=== Code Comparison ===")
    print("Task: Create and verify RFC 3161 timestamp")
    print("\nOriginal implementation (timestamp_tsa.py):")
    print("  - 385 lines of code")
    print("  - Manual ASN.1 encoding/decoding")
    print("  - Manual HTTP request handling")
    print("  - Manual certificate parsing")
    print("  - Complex error handling")

    print("\nWith tsp-client (this demo):")
    print("  - 4 lines for core functionality:")
    print("    signer = TSPSigner()")
    print("    token = signer.sign(data)")
    print("    verifier = TSPVerifier()")
    print("    valid = verifier.verify(token, message=data)")
    print("  - All complexity handled internally")
    print("  - Production-ready with DigiCert TSA")

    print("\n=== Trade-offs ===")
    print("Benefits of tsp-client:")
    print("  ✓ 90% less code for basic timestamping")
    print("  ✓ Battle-tested with production TSA (DigiCert)")
    print("  ✓ Automatic certificate chain validation")
    print("  ✓ Clean, simple API")

    print("\nLimitations:")
    print("  ✗ Limited to TSAs that follow DigiCert's protocol")
    print("  ✗ No support for custom HTTP headers (needed for FreeTSA)")
    print("  ✗ Less control over request parameters")
    print("  ✗ DigiCert endpoint doesn't use HTTPS encryption")

    print("\nRecommendation:")
    print("  - Use tsp-client for production with DigiCert TSA")
    print("  - Use manual implementation for FreeTSA or custom TSAs")


def main():
    # type: () -> None
    """
    Main function - supports both demo mode and TSA testing mode.
    """
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Test all TSA servers
        results = test_all_tsa_servers()
        print_summary(results)
    else:
        # Original demo
        demo_basic_usage()


if __name__ == "__main__":
    main()
