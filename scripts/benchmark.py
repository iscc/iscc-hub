"""
High-performance benchmark script for ISCC Hub sandbox deployment.

Tests concurrent declaration performance against https://sb0.iscc.id using:
- Thousands of random but valid IsccNote declarations
- niquests with HTTP/2 multiplexing for maximum throughput
- aiomultiprocess for parallel payload generation and request execution
- Comprehensive performance reporting
"""

import argparse
import asyncio
import json
import os
import random
import string
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import aiomultiprocess
import niquests

# Add project root to path for imports
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Import ISCC libraries after path setup
import iscc_core as ic  # noqa: E402
import iscc_crypto as icr  # noqa: E402

# Note: Could alternatively import from demo_declare:
# from scripts.demo_declare import generate_random_iscc_note
# But we use a modified version here that supports indexing for benchmarks


def generate_random_iscc_note(index=None):
    # type: (int | None) -> dict[str, Any]
    """
    Generate a random but valid IsccNote for benchmarking.

    Based on the generate_random_iscc_note from demo_declare.py but adapted
    for benchmark testing with optional index for deterministic content.
    """
    # Generate random or indexed content
    if index is not None:
        # For benchmarking: deterministic but unique content based on index
        random_text = f"Benchmark content {index} - Random data: {os.urandom(32).hex()}"
        random_title = f"Benchmark Test {index}"
        random_description = f"Automated benchmark test declaration number {index}"
        controller = f"did:web:benchmark{index % 100}.example.com"
        gateway_url = f"https://benchmark.example.com/item/{index}"
    else:
        # For demo: fully random content like in demo_declare.py
        random_text = "".join(random.choices(string.ascii_letters + string.digits + " ", k=random.randint(50, 200)))
        random_title = "".join(random.choices(string.ascii_letters + " ", k=random.randint(10, 30)))
        random_description = "".join(random.choices(string.ascii_letters + " ", k=random.randint(20, 50)))
        controller = f"did:web:demo-{random.randint(1000, 9999)}.example.com"
        nonce_prefix = icr.create_nonce(0)[:8]
        gateway_url = f"https://example.com/demo/{nonce_prefix}"

    # Generate ISCC components
    text_bytes = random_text.encode("utf-8")
    mcode = ic.gen_meta_code(random_title, random_description, bits=256)
    ccode = ic.gen_text_code(random_text, bits=256)
    dcode = ic.gen_data_code(BytesIO(text_bytes), bits=256)
    icode = ic.gen_instance_code(BytesIO(text_bytes), bits=256)

    # Generate composite ISCC code from all units including instance
    iscc_code = ic.gen_iscc_code([mcode["iscc"], ccode["iscc"], dcode["iscc"], icode["iscc"]])["iscc"]

    # Create nonce with hub_id 0 (sandbox)
    nonce = icr.create_nonce(0)

    # Create timestamp with millisecond precision
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    # Create the IsccNote
    note = {
        "iscc_code": iscc_code,
        "datahash": icode["datahash"],
        "nonce": nonce,
        "timestamp": timestamp,
        "gateway": gateway_url,
        "metahash": mcode["metahash"],
        "units": [mcode["iscc"], ccode["iscc"], dcode["iscc"]],  # META, CONTENT, DATA units (NOT instance)
    }

    # Generate keypair and sign the note
    keypair = icr.key_generate(controller=controller)
    signed_note = icr.sign_json(note, keypair)

    return signed_note


def generate_payloads_batch(batch_info):
    # type: (tuple[int, int]) -> list[dict[str, Any]]
    """Generate a batch of payloads in a separate process."""
    start_idx, count = batch_info
    return [generate_random_iscc_note(start_idx + i) for i in range(count)]


async def send_declaration(session, payload, semaphore, target_url):
    # type: (niquests.AsyncSession, dict[str, Any], asyncio.Semaphore, str) -> tuple[niquests.Response, float, dict[str, Any]]
    """Send a single declaration and return the lazy response and timing info."""
    async with semaphore:
        start_time = time.perf_counter()
        try:
            # Send the request - returns a lazy response when multiplexed=True
            declaration_url = f"{target_url.rstrip('/')}/declaration"
            response = await session.post(
                declaration_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30,  # 30 second timeout per request
            )
            elapsed = time.perf_counter() - start_time
            # Return the lazy response - we'll access properties after gather()
            return response, elapsed, payload
        except TimeoutError:
            elapsed = time.perf_counter() - start_time
            return None, elapsed, payload
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            print(f"Request exception: {e}")
            return None, elapsed, payload


async def benchmark_declarations(payloads, target_url, max_concurrent=100):
    # type: (list[dict[str, Any]], str, int) -> tuple[list[tuple[bool, int, float, str]], float]
    """Send all declarations concurrently using niquests with HTTP/2."""
    print(f"Sending {len(payloads)} declarations with {max_concurrent} max concurrent requests...")

    # Create semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(max_concurrent)

    # Process in batches to avoid overwhelming the system with large payloads
    batch_size = 1000  # Process in smaller batches for better memory management
    all_results = []
    start_time = time.perf_counter()

    for i in range(0, len(payloads), batch_size):
        batch = payloads[i : i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(payloads) + batch_size - 1) // batch_size
        print(f"  Processing batch {batch_num}/{total_batches} ({len(batch)} requests)...")

        # Use niquests AsyncSession with multiplexing enabled for maximum performance
        async with niquests.AsyncSession(multiplexed=True) as session:
            # Create all tasks for this batch
            tasks = [send_declaration(session, payload, semaphore, target_url) for payload in batch]

            # Execute all tasks concurrently - returns lazy responses
            lazy_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Gather all lazy responses to resolve them
            await session.gather()

            # Now process the resolved responses
            for result in lazy_results:
                if isinstance(result, Exception):
                    all_results.append((False, 0, 0.0, str(result)))
                elif result is None:
                    # Timeout or error case
                    all_results.append((False, 0, 0.0, "Request failed"))
                else:
                    response, elapsed, payload = result
                    if response is None:
                        all_results.append((False, 0, elapsed, "Request timeout or error"))
                    else:
                        # Now we can safely access response properties
                        try:
                            status_code = response.status_code
                            if status_code == 400:
                                # Log details of 400 errors for debugging
                                error_body = response.text
                                all_results.append((True, status_code, elapsed, error_body))
                            else:
                                all_results.append((True, status_code, elapsed, ""))
                        except Exception as e:
                            all_results.append((False, 0, elapsed, str(e)))

    total_time = time.perf_counter() - start_time
    return all_results, total_time


async def run_benchmark(target_url, num_declarations=2000, batch_size=500, max_concurrent=100):
    # type: (str, int, int, int) -> None
    """Run the complete benchmark."""
    print(f"\n{'=' * 80}")
    print("ISCC Hub Benchmark")
    print(f"{'=' * 80}")
    print(f"Target: {target_url}")
    print(f"Declarations: {num_declarations}")
    print(f"Batch size: {batch_size}")
    print(f"Max concurrent: {max_concurrent}")
    print(f"{'=' * 80}\n")

    # Step 1: Generate all payloads using multiprocessing
    print("Step 1: Generating payloads...")
    payload_start = time.perf_counter()

    # Create batch information for multiprocessing
    batches = []
    for i in range(0, num_declarations, batch_size):
        count = min(batch_size, num_declarations - i)
        batches.append((i, count))

    # Generate payloads in parallel using ProcessPoolExecutor
    all_payloads = []
    with ProcessPoolExecutor() as executor:
        batch_results = executor.map(generate_payloads_batch, batches)
        for batch_payloads in batch_results:
            all_payloads.extend(batch_payloads)

    payload_time = time.perf_counter() - payload_start
    print(f"Generated {len(all_payloads)} payloads in {payload_time:.3f}s")

    # Step 2: Send all declarations concurrently
    print("\nStep 2: Sending declarations...")
    results, request_time = await benchmark_declarations(all_payloads, target_url, max_concurrent)

    # Step 3: Analyze results
    print("\nStep 3: Results Analysis")
    print(f"{'=' * 80}")

    # Basic stats
    total_requests = len(results)
    successful = sum(1 for success, _, _, _ in results if success)
    failed = total_requests - successful

    # Response time stats
    response_times = [elapsed for success, _, elapsed, _ in results if success]
    status_codes = {}
    errors = {}
    error_400_details = {}

    failed_timings = []
    for success, status_code, elapsed, error in results:
        if success:
            status_codes[status_code] = status_codes.get(status_code, 0) + 1
            if status_code == 400 and error:
                # Parse and categorize 400 errors
                error_msg = error[:200] if len(error) > 200 else error
                error_400_details[error_msg] = error_400_details.get(error_msg, 0) + 1
                failed_timings.append(elapsed)
        else:
            error_type = error.split(":")[0] if error else "Unknown"
            errors[error_type] = errors.get(error_type, 0) + 1

    # Print performance metrics
    total_time = payload_time + request_time
    print(f"Total time: {total_time:.3f}s (generation: {payload_time:.3f}s, requests: {request_time:.3f}s)")
    print(f"Throughput: {successful / request_time:.1f} successful requests/sec")
    print(f"Success rate: {successful}/{total_requests} ({100 * successful / total_requests:.1f}%)")
    print(f"Failed requests: {failed}")

    if response_times:
        avg_response = sum(response_times) / len(response_times)
        min_response = min(response_times)
        max_response = max(response_times)
        sorted_times = sorted(response_times)
        p50 = sorted_times[len(sorted_times) // 2]
        p90 = sorted_times[int(len(sorted_times) * 0.90)]
        p95 = sorted_times[int(len(sorted_times) * 0.95)]
        p99 = sorted_times[int(len(sorted_times) * 0.99)]

        print("\nLatency Statistics:")
        print(f"  Average: {avg_response:.4f}s")
        print(f"  Min: {min_response:.4f}s")
        print(f"  Max: {max_response:.4f}s")
        print(f"  P50: {p50:.4f}s")
        print(f"  P90: {p90:.4f}s")
        print(f"  P95: {p95:.4f}s")
        print(f"  P99: {p99:.4f}s")

    if status_codes:
        print("\nStatus Code Distribution:")
        for code, count in sorted(status_codes.items()):
            print(f"  {code}: {count} ({100 * count / successful:.1f}%)")

    if errors:
        print("\nError Breakdown:")
        for error_type, count in sorted(errors.items(), key=lambda x: x[1], reverse=True):
            print(f"  {error_type}: {count}")

    if error_400_details:
        print("\n400 Error Details:")
        for error_msg, count in sorted(error_400_details.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  [{count}x] {error_msg}")

        if failed_timings:
            print("\n400 Error Response Times:")
            print(f"  Average: {sum(failed_timings) / len(failed_timings):.3f}s")
            print(f"  Min: {min(failed_timings):.3f}s")
            print(f"  Max: {max(failed_timings):.3f}s")

    # Performance rating
    if successful > 0:
        rps = successful / request_time
        print("\nPerformance Rating:")
        if rps > 100:
            print(f"  🚀 EXCELLENT: {rps:.0f} req/s")
        elif rps > 50:
            print(f"  ✅ GOOD: {rps:.0f} req/s")
        elif rps > 20:
            print(f"  ⚠️  FAIR: {rps:.0f} req/s")
        else:
            print(f"  ❌ POOR: {rps:.0f} req/s")


async def main():
    # type: () -> None
    """Main benchmark runner with different test configurations."""
    parser = argparse.ArgumentParser(description="Benchmark an ISCC hub for performance testing")
    parser.add_argument(
        "target_url",
        nargs="?",
        default="http://localhost:8000",
        help="Hub URL to benchmark (default: http://localhost:8000)",
    )

    args = parser.parse_args()
    target_url = args.target_url

    configurations = [
        (500, 100, 50),  # Warm-up: 500 declarations, 50 concurrent
        (2000, 500, 80),  # Standard: 2000 declarations, 80 concurrent
        (5000, 500, 100),  # Heavy: 5000 declarations, 100 concurrent (reduced from 200)
    ]

    for i, (num_declarations, batch_size, max_concurrent) in enumerate(configurations):
        if i > 0:
            print(f"\n\n{'=' * 80}")
            print("Waiting 10 seconds before next test...")
            print(f"{'=' * 80}")
            await asyncio.sleep(10)

        await run_benchmark(target_url, num_declarations, batch_size, max_concurrent)


if __name__ == "__main__":
    # Set event loop policy for Windows compatibility
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    asyncio.run(main())
