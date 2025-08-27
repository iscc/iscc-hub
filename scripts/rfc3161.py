"""TSA (RFC 3161) timestamping demo using FreeTSA.org"""

import hashlib
import os
from datetime import datetime

import niquests
from asn1crypto import algos, cms, core, tsp, x509

# FreeTSA.org timestamp server URL
FREETSA_URL = "https://freetsa.org/tsr"

# FreeTSA.org certificate URL for verification
FREETSA_CERT_URL = "https://freetsa.org/files/cacert.pem"
FREETSA_TSA_CERT_URL = "https://freetsa.org/files/tsa.crt"


def create_timestamp_request(data, hash_algorithm="sha256"):
    # type: (bytes, str) -> bytes
    """
    Create a RFC 3161 timestamp request.

    :param data: Data to timestamp
    :param hash_algorithm: Hash algorithm to use (sha256, sha512)
    :return: DER encoded timestamp request
    """
    # Hash the data
    if hash_algorithm == "sha256":
        hasher = hashlib.sha256()
        algo_oid = "2.16.840.1.101.3.4.2.1"  # SHA-256 OID
    elif hash_algorithm == "sha512":
        hasher = hashlib.sha512()
        algo_oid = "2.16.840.1.101.3.4.2.3"  # SHA-512 OID
    else:
        raise ValueError(f"Unsupported hash algorithm: {hash_algorithm}")

    hasher.update(data)
    message_digest = hasher.digest()

    # Create timestamp request
    req = tsp.TimeStampReq(
        {
            "version": "v1",
            "message_imprint": tsp.MessageImprint(
                {"hash_algorithm": algos.DigestAlgorithm({"algorithm": algo_oid}), "hashed_message": message_digest}
            ),
            "cert_req": True,  # Request TSA certificate in response
            "nonce": core.Integer(int.from_bytes(os.urandom(8), "big")),  # Random nonce
        }
    )

    return req.dump()


def submit_timestamp_request(request_bytes, tsa_url=FREETSA_URL):
    # type: (bytes, str) -> bytes | None
    """
    Submit timestamp request to TSA server.

    :param request_bytes: DER encoded timestamp request
    :param tsa_url: TSA server URL
    :return: DER encoded timestamp response or None on error
    """
    headers = {"Content-Type": "application/timestamp-query", "Accept": "application/timestamp-reply"}

    try:
        response = niquests.post(tsa_url, data=request_bytes, headers=headers, timeout=30)

        if response.status_code == 200:
            print(f"✓ Timestamp request successful (status: {response.status_code})")
            return response.content
        else:
            print(f"✗ Timestamp request failed (status: {response.status_code})")
            print(f"  Response: {response.text[:200]}")
            return None

    except niquests.RequestException as e:
        print(f"✗ Network error: {e}")
        return None


def parse_timestamp_response(response_bytes):
    # type: (bytes) -> dict | None
    """
    Parse and extract information from timestamp response.

    :param response_bytes: DER encoded timestamp response
    :return: Dictionary with timestamp information or None on error
    """
    try:
        # Parse the timestamp response
        ts_resp = tsp.TimeStampResp.load(response_bytes)

        # Check status
        status = ts_resp["status"]["status"].native
        if status != "granted":
            status_string = ts_resp["status"].get("status_string")
            if status_string:
                print(f"✗ Timestamp request not granted: {status_string[0].native}")
            else:
                print(f"✗ Timestamp request not granted: {status}")
            return None

        # Extract timestamp token
        tst = ts_resp["time_stamp_token"]

        # Parse the CMS signed data
        signed_data = tst["content"]

        # Get the encapsulated TSTInfo
        encap_content_info = signed_data["encap_content_info"]
        tst_info_bytes = encap_content_info["content"].parsed.dump()
        tst_info = tsp.TSTInfo.load(tst_info_bytes)

        # Extract timestamp details
        result = {
            "status": status,
            "time": tst_info["gen_time"].native,
            "accuracy": None,
            "serial_number": tst_info["serial_number"].native,
            "tsa_name": None,
            "message_imprint": {
                "algorithm": tst_info["message_imprint"]["hash_algorithm"]["algorithm"].dotted,
                "digest": tst_info["message_imprint"]["hashed_message"].native.hex(),
            },
            "nonce": tst_info["nonce"].native if "nonce" in tst_info and tst_info["nonce"] else None,
        }

        # Extract accuracy if present
        if "accuracy" in tst_info and tst_info["accuracy"]:
            accuracy = tst_info["accuracy"]
            result["accuracy"] = {
                "seconds": accuracy["seconds"].native if "seconds" in accuracy and accuracy["seconds"] else None,
                "millis": accuracy["millis"].native if "millis" in accuracy and accuracy["millis"] else None,
                "micros": accuracy["micros"].native if "micros" in accuracy and accuracy["micros"] else None,
            }

        # Extract TSA name from certificate if available
        if "certificates" in signed_data and signed_data["certificates"]:
            for cert_choice in signed_data["certificates"]:
                cert = cert_choice.chosen
                if isinstance(cert, x509.Certificate):
                    subject = cert.subject.native
                    if "common_name" in subject:
                        result["tsa_name"] = subject["common_name"]
                        break

        return result

    except Exception as e:
        print(f"✗ Failed to parse timestamp response: {e}")
        return None


def save_timestamp(response_bytes, filename):
    # type: (bytes, str) -> None
    """
    Save timestamp response to file.

    :param response_bytes: DER encoded timestamp response
    :param filename: Output filename
    """
    with open(filename, "wb") as f:
        f.write(response_bytes)
    print(f"Saved timestamp to {filename} ({len(response_bytes)} bytes)")


def load_timestamp(filename):
    # type: (str) -> bytes
    """
    Load timestamp response from file.

    :param filename: Timestamp file to load
    :return: DER encoded timestamp response
    """
    with open(filename, "rb") as f:
        return f.read()


def verify_timestamp(response_bytes, original_data, ca_cert_path=None):
    # type: (bytes, bytes, str | None) -> bool
    """
    Verify a timestamp response against original data.

    :param response_bytes: DER encoded timestamp response
    :param original_data: Original data that was timestamped
    :param ca_cert_path: Path to CA certificate for verification
    :return: True if verification successful, False otherwise
    """
    try:
        # Parse timestamp response
        ts_resp = tsp.TimeStampResp.load(response_bytes)

        # Check status
        if ts_resp["status"]["status"].native != "granted":
            print("✗ Timestamp was not granted")
            return False

        # Get timestamp token
        tst = ts_resp["time_stamp_token"]
        signed_data = tst["content"]

        # Extract TSTInfo
        encap_content_info = signed_data["encap_content_info"]
        tst_info_bytes = encap_content_info["content"].parsed.dump()
        tst_info = tsp.TSTInfo.load(tst_info_bytes)

        # Verify message imprint
        algo_oid = tst_info["message_imprint"]["hash_algorithm"]["algorithm"].dotted
        stored_digest = tst_info["message_imprint"]["hashed_message"].native

        # Compute hash of original data
        if algo_oid == "2.16.840.1.101.3.4.2.1":  # SHA-256
            computed_digest = hashlib.sha256(original_data).digest()
        elif algo_oid == "2.16.840.1.101.3.4.2.3":  # SHA-512
            computed_digest = hashlib.sha512(original_data).digest()
        else:
            print(f"✗ Unsupported hash algorithm: {algo_oid}")
            return False

        if stored_digest != computed_digest:
            print("✗ Message digest mismatch")
            print(f"  Expected: {computed_digest.hex()}")
            print(f"  Got:      {stored_digest.hex()}")
            return False

        print("✓ Message digest verified")

        # Basic signature structure validation
        # Note: Full cryptographic verification would require validating
        # the certificate chain and CMS signature, which is complex
        if "signer_infos" in signed_data and signed_data["signer_infos"]:
            print("✓ Signature present (cryptographic verification not implemented)")
            print("  Note: For production use, implement full PKI verification")

        # Display timestamp info
        timestamp_time = tst_info["gen_time"].native
        serial = tst_info["serial_number"].native
        print("✓ Timestamp verified:")
        print(f"  Time: {timestamp_time}")
        print(f"  Serial: {serial}")

        if "accuracy" in tst_info and tst_info["accuracy"]:
            accuracy = tst_info["accuracy"]
            if "seconds" in accuracy:
                print(f"  Accuracy: ±{accuracy['seconds'].native} seconds")

        return True

    except Exception as e:
        print(f"✗ Verification failed: {e}")
        return False


def download_freetsa_certificates():
    # type: () -> tuple[bool, str, str]
    """
    Download FreeTSA certificates for verification.

    :return: Tuple of (success, ca_cert_path, tsa_cert_path)
    """
    ca_cert_path = "freetsa_ca.pem"
    tsa_cert_path = "freetsa_tsa.crt"

    try:
        # Download CA certificate
        print("Downloading FreeTSA CA certificate...")
        response = niquests.get(FREETSA_CERT_URL)
        if response.status_code == 200:
            with open(ca_cert_path, "wb") as f:
                f.write(response.content)
            print(f"✓ CA certificate saved to {ca_cert_path}")
        else:
            print(f"✗ Failed to download CA certificate: {response.status_code}")
            return False, "", ""

        # Download TSA certificate
        print("Downloading FreeTSA TSA certificate...")
        response = niquests.get(FREETSA_TSA_CERT_URL)
        if response.status_code == 200:
            with open(tsa_cert_path, "wb") as f:
                f.write(response.content)
            print(f"✓ TSA certificate saved to {tsa_cert_path}")
        else:
            print(f"✗ Failed to download TSA certificate: {response.status_code}")
            return False, "", ""

        return True, ca_cert_path, tsa_cert_path

    except niquests.RequestException as e:
        print(f"✗ Failed to download certificates: {e}")
        return False, "", ""


def main():
    # type: () -> None
    """
    Main demo function showing complete TSA timestamping workflow.
    """
    print("=== TSA (RFC 3161) Timestamping Demo using FreeTSA.org ===\n")

    # 1) Create test payload
    payload = os.urandom(32)
    print(f"Test payload: {payload.hex()}")
    print(f"Payload size: {len(payload)} bytes\n")

    # 2) Create timestamp request
    print("--- Creating Timestamp Request ---")
    try:
        request_bytes = create_timestamp_request(payload, "sha256")
        print(f"✓ Created timestamp request ({len(request_bytes)} bytes)")

        # Display request hash for reference
        digest = hashlib.sha256(payload).digest()
        print(f"  Message digest (SHA-256): {digest.hex()}\n")

    except Exception as e:
        print(f"✗ Failed to create request: {e}")
        return

    # 3) Submit to TSA server
    print("--- Submitting to FreeTSA.org ---")
    response_bytes = submit_timestamp_request(request_bytes)

    if response_bytes is None:
        print("\n✗ Failed to get timestamp response")
        return

    print(f"✓ Received timestamp response ({len(response_bytes)} bytes)\n")

    # 4) Parse and display timestamp info
    print("--- Parsing Timestamp Response ---")
    ts_info = parse_timestamp_response(response_bytes)

    if ts_info:
        print("✓ Timestamp parsed successfully:")
        print(f"  Status: {ts_info['status']}")
        print(f"  Time: {ts_info['time']}")
        print(f"  Serial: {ts_info['serial_number']}")
        if ts_info["tsa_name"]:
            print(f"  TSA: {ts_info['tsa_name']}")
        if ts_info["accuracy"]:
            acc = ts_info["accuracy"]
            if acc["seconds"]:
                print(f"  Accuracy: ±{acc['seconds']} seconds")
        print(f"  Algorithm: {ts_info['message_imprint']['algorithm']}")
        print(f"  Digest: {ts_info['message_imprint']['digest'][:32]}...")
        if ts_info["nonce"]:
            print(f"  Nonce: {ts_info['nonce']}")
        print()
    else:
        print("✗ Failed to parse timestamp\n")
        return

    # 5) Save timestamp
    timestamp_file = f"timestamp_{payload.hex()[:16]}.tsr"
    save_timestamp(response_bytes, timestamp_file)
    print()

    # 6) Verify timestamp
    print("--- Verifying Timestamp ---")
    print(f"Loading timestamp from {timestamp_file}...")
    loaded_response = load_timestamp(timestamp_file)

    print("Verifying against original data...")
    is_valid = verify_timestamp(loaded_response, payload)

    if is_valid:
        print("\n✅ Timestamp verification successful!")
        print(f"The data {payload.hex()[:32]}... was provably")
        print(f"timestamped at {ts_info['time']} by FreeTSA.org")
    else:
        print("\n✗ Timestamp verification failed!")

    # 7) Optional: Download certificates for future use
    print("\n--- Certificate Download (Optional) ---")
    success, ca_path, tsa_path = download_freetsa_certificates()
    if success:
        print("\n📜 Certificates downloaded for future verification")
        print("Note: Full PKI verification requires additional implementation")


if __name__ == "__main__":
    main()
