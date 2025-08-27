"""TSA (RFC 3161) timestamping demo using tsp-client library."""

import hashlib
import os

from tsp_client import TSPSigner, TSPVerifier


def main():
    # type: () -> None
    """
    Minimal demo showing tsp-client library usage.
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


if __name__ == "__main__":
    main()
