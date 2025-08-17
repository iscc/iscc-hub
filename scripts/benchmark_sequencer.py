"""
Benchmark and test script for the ISCC Hub sequencer.

Tests concurrent access, performance, and correctness of:
- Gapless sequence numbering
- Unique nonce enforcement
- Monotonic timestamp generation
- Atomic transaction handling
"""

import asyncio
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

import django

# Setup Django
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
sys.path.insert(0, str(BASE_DIR))

# Set test environment variables
os.environ.update(
    {
        "DJANGO_SETTINGS_MODULE": "iscc_hub.settings",
        "DJANGO_DEBUG": "True",
        "DJANGO_SECRET_KEY": "test-secret-key-for-testing-only",
        "ISCC_HUB_DB_NAME": "benchmark_test.sqlite3",
        "ISCC_HUB_DOMAIN": "testserver",
        "ISCC_HUB_SECKEY": "z3u2hnGm6Vp6zXdB4x51vp2VMGqHfB6BcF3cvgkC5aDxPsJR",
        "ISCC_HUB_ID": "1",
        "DJANGO_ALLOWED_HOSTS": "testserver,localhost",
    }
)

django.setup()

# Import after Django setup
import iscc_core as ic  # noqa: E402
import iscc_crypto as icr  # noqa: E402
from asgiref.sync import sync_to_async  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.db import connection  # noqa: E402

from iscc_hub.sequencer import sequence_iscc_note  # noqa: E402

# Create tables if they don't exist
try:
    call_command("migrate", "--run-syncdb", verbosity=0, interactive=False)
except Exception:
    pass


def generate_test_note(index, worker_id):
    # type: (int, int) -> dict
    """Generate a unique test IsccNote."""
    from io import BytesIO

    # Create unique content for each note
    text = f"Test content {worker_id}-{index}"
    text_bytes = text.encode("utf-8")

    # Generate ISCC components
    mcode = ic.gen_meta_code(text, f"Test {index}", bits=256)
    ccode = ic.gen_text_code(text, bits=256)
    dcode = ic.gen_data_code(BytesIO(text_bytes), bits=256)
    icode = ic.gen_instance_code(BytesIO(text_bytes), bits=256)
    iscc_code = ic.gen_iscc_code([mcode["iscc"], ccode["iscc"], dcode["iscc"], icode["iscc"]])["iscc"]

    # Generate unique nonce (first 12 bits = 001 for hub_id 1)
    nonce_bytes = os.urandom(16)
    # Set first 12 bits to 001 (hub_id 1)
    nonce_bytes = bytes([0x00, 0x10]) + nonce_bytes[2:]
    nonce = nonce_bytes.hex()

    # Create IsccNote
    note = {
        "iscc_code": iscc_code,
        "datahash": icode["datahash"],  # datahash comes from instance code
        "nonce": nonce,
        "timestamp": f"2025-01-15T12:00:{index % 60:02d}.{worker_id:03d}Z",
        "gateway": f"https://example.com/worker{worker_id}/item{index}",
        "metahash": mcode["metahash"],
    }

    # Sign the note
    controller = f"did:web:worker{worker_id}.example.com"
    keypair = icr.key_generate(controller=controller)
    signed_note = icr.sign_json(note, keypair)

    return signed_note


async def sequence_worker(worker_id, num_requests):
    # type: (int, int) -> list[tuple[bool, str, float]]
    """Worker that submits sequencing requests."""
    results = []

    for i in range(num_requests):
        note = generate_test_note(i, worker_id)
        start_time = time.perf_counter()

        try:
            seq, iscc_id = await sync_to_async(sequence_iscc_note)(note)
            elapsed = time.perf_counter() - start_time
            results.append((True, f"seq={seq}, iscc_id={iscc_id}", elapsed))
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            import traceback

            error_msg = f"{type(e).__name__}: {str(e)}"
            # On first error, print traceback for debugging
            if i == 0 and worker_id == 0:
                print(f"Debug - Full traceback:\n{traceback.format_exc()}")
            results.append((False, error_msg, elapsed))

    return results


async def run_benchmark(num_workers=10, requests_per_worker=50):
    # type: (int, int) -> None
    """Run the benchmark with concurrent workers."""
    print(f"\n{'=' * 60}")
    print("Sequencer Benchmark")
    print(f"{'=' * 60}")
    print(f"Workers: {num_workers}")
    print(f"Requests per worker: {requests_per_worker}")
    print(f"Total requests: {num_workers * requests_per_worker}")
    print(f"{'=' * 60}\n")

    # Clear the database (run in thread to avoid async context issues)
    def clear_db():
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM iscc_event")
            cursor.execute("DELETE FROM iscc_declaration")
            connection.commit()

    await sync_to_async(clear_db)()

    # Run workers concurrently
    start_time = time.perf_counter()

    # Create tasks for all workers
    tasks = [sequence_worker(worker_id, requests_per_worker) for worker_id in range(num_workers)]

    # Run all workers concurrently
    all_results = await asyncio.gather(*tasks)

    total_time = time.perf_counter() - start_time

    # Analyze results
    total_success = 0
    total_failure = 0
    response_times = []
    errors = {}

    for worker_results in all_results:
        for success, message, elapsed in worker_results:
            if success:
                total_success += 1
                response_times.append(elapsed)
            else:
                total_failure += 1
                error_type = message.split(":")[0]
                errors[error_type] = errors.get(error_type, 0) + 1
                # Print first error for debugging
                if len(errors) == 1 and errors[error_type] == 1:
                    print(f"First error: {message}")

    # Print results
    print("Results:")
    print(f"{'=' * 60}")
    print(f"Total time: {total_time:.3f} seconds")
    print(f"Throughput: {(total_success + total_failure) / total_time:.1f} requests/sec")
    print(f"Success: {total_success}")
    print(f"Failures: {total_failure}")

    if response_times:
        avg_response = sum(response_times) / len(response_times)
        min_response = min(response_times)
        max_response = max(response_times)
        p50 = sorted(response_times)[len(response_times) // 2]
        p95 = sorted(response_times)[int(len(response_times) * 0.95)]
        p99 = sorted(response_times)[int(len(response_times) * 0.99)]

        print("\nLatency (seconds):")
        print(f"  Average: {avg_response:.4f}")
        print(f"  Min: {min_response:.4f}")
        print(f"  Max: {max_response:.4f}")
        print(f"  P50: {p50:.4f}")
        print(f"  P95: {p95:.4f}")
        print(f"  P99: {p99:.4f}")

    if errors:
        print("\nError breakdown:")
        for error_type, count in errors.items():
            print(f"  {error_type}: {count}")

    # Validate correctness
    print(f"\n{'=' * 60}")
    print("Correctness Validation")
    print(f"{'=' * 60}")

    def validate():
        with connection.cursor() as cursor:
            # Check for gaps in sequence
            cursor.execute("""
                SELECT COUNT(*) as count, MIN(seq) as min_seq, MAX(seq) as max_seq
                FROM iscc_event
            """)
            row = cursor.fetchone()
            count, min_seq, max_seq = row

            if count > 0:
                expected_count = max_seq - min_seq + 1
                has_gaps = count != expected_count
                print(f"Sequence gaps: {'FAILED ❌' if has_gaps else 'PASSED ✓'}")
                print(f"  Sequences: {min_seq} to {max_seq}")
                print(f"  Count: {count} (expected: {expected_count})")

                if has_gaps:
                    # Find gaps
                    cursor.execute("""
                        SELECT seq + 1 as gap_start
                        FROM iscc_event e1
                        WHERE NOT EXISTS (
                            SELECT 1 FROM iscc_event e2 WHERE e2.seq = e1.seq + 1
                        )
                        AND seq < (SELECT MAX(seq) FROM iscc_event)
                        ORDER BY seq
                        LIMIT 10
                    """)
                    gaps = cursor.fetchall()
                    if gaps:
                        print(f"  First gaps at: {[g[0] for g in gaps]}")

            # Check for duplicate nonces
            cursor.execute("""
                SELECT json_extract(iscc_note, '$.nonce') as nonce, COUNT(*) as count
                FROM iscc_event
                GROUP BY json_extract(iscc_note, '$.nonce')
                HAVING count > 1
            """)
            duplicates = cursor.fetchall()
            print(f"Unique nonces: {'FAILED ❌' if duplicates else 'PASSED ✓'}")
            if duplicates:
                print(f"  Found {len(duplicates)} duplicate nonces")

            # Check for monotonic timestamps in ISCC-IDs
            cursor.execute("""
                SELECT seq, iscc_id
                FROM iscc_event
                ORDER BY seq
            """)
            rows = cursor.fetchall()

            non_monotonic = []
            prev_timestamp = 0
            for seq, iscc_id_bytes in rows:
                # Extract timestamp from ISCC-ID (52-bit timestamp, 12-bit hub_id)
                timestamp = int.from_bytes(iscc_id_bytes, "big") >> 12
                if timestamp <= prev_timestamp:
                    non_monotonic.append((seq, timestamp, prev_timestamp))
                prev_timestamp = timestamp

            print(f"Monotonic timestamps: {'FAILED ❌' if non_monotonic else 'PASSED ✓'}")
            if non_monotonic:
                print(f"  Found {len(non_monotonic)} non-monotonic timestamps")
                for seq, ts, prev_ts in non_monotonic[:5]:
                    print(f"    Seq {seq}: {ts} <= {prev_ts}")

            # Check declaration table consistency
            cursor.execute("""
                SELECT COUNT(*) FROM iscc_declaration
            """)
            declaration_count = cursor.fetchone()[0]
            print(f"Declaration entries: {declaration_count} (should match event count: {count})")

            # Check for orphaned declarations
            cursor.execute("""
                SELECT COUNT(*)
                FROM iscc_declaration d
                WHERE NOT EXISTS (
                    SELECT 1 FROM iscc_event e WHERE e.iscc_id = d.iscc_id
                )
            """)
            orphaned = cursor.fetchone()[0]
            print(f"Orphaned declarations: {'FAILED ❌' if orphaned > 0 else 'PASSED ✓'} ({orphaned})")

    # Run validation using sync_to_async
    await sync_to_async(validate)()


async def main():
    # type: () -> None
    """Main entry point."""
    # Test different configurations
    configs = [
        (5, 20),  # Light load
        (10, 50),  # Medium load
        (20, 100),  # Heavy load
    ]

    for num_workers, requests_per_worker in configs:
        await run_benchmark(num_workers, requests_per_worker)
        print("\n")


if __name__ == "__main__":
    asyncio.run(main())
