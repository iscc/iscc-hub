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
from django.db.models import Count  # noqa: E402

from iscc_hub.iscc_id import IsccID  # noqa: E402
from iscc_hub.models import IsccDeclaration, LogRecord, LogState  # noqa: E402
from iscc_hub.sequencer import sequence_iscc_note  # noqa: E402

ISCC_NOTE_SCHEMA = "http://purl.org/iscc/schema/iscc-note-0.8.0.json"

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
        "$schema": ISCC_NOTE_SCHEMA,
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

    # Clear the log, the materialized view, and the sequencer state (run in a
    # thread to avoid async context issues). Removing LogState resets tree_size so
    # the next run's leaf indices start at 0.
    def clear_db():
        IsccDeclaration.objects.all().delete()
        LogRecord.objects.all().delete()
        LogState.objects.all().delete()

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
        # Records ordered by their 0-based leaf index; iscc_id reads back as a string.
        records = list(LogRecord.objects.order_by("index").values_list("index", "iscc_id"))
        count = len(records)

        # Check for gaps in the gapless leaf-index sequence.
        if count > 0:
            indices = [idx for idx, _ in records]
            min_seq, max_seq = indices[0], indices[-1]
            expected_count = max_seq - min_seq + 1
            present = set(indices)
            gaps = [i for i in range(min_seq, max_seq + 1) if i not in present]
            print(f"Sequence gaps: {'FAILED ❌' if gaps else 'PASSED ✓'}")
            print(f"  Sequences: {min_seq} to {max_seq}")
            print(f"  Count: {count} (expected: {expected_count})")
            if gaps:
                print(f"  First gaps at: {gaps[:10]}")

        # Check for duplicate nonces (the nonce is a dedicated unique column now).
        duplicates = LogRecord.objects.values("nonce").annotate(n=Count("nonce")).filter(n__gt=1)
        dup_count = duplicates.count()
        print(f"Unique nonces: {'FAILED ❌' if dup_count else 'PASSED ✓'}")
        if dup_count:
            print(f"  Found {dup_count} duplicate nonces")

        # Check for monotonic timestamps encoded in the ISCC-IDs.
        non_monotonic = []
        prev_timestamp = 0
        for seq, iscc_id in records:
            timestamp = IsccID(iscc_id).timestamp_micros  # 52-bit µs timestamp, 12-bit hub-id
            if timestamp <= prev_timestamp:
                non_monotonic.append((seq, timestamp, prev_timestamp))
            prev_timestamp = timestamp

        print(f"Monotonic timestamps: {'FAILED ❌' if non_monotonic else 'PASSED ✓'}")
        if non_monotonic:
            print(f"  Found {len(non_monotonic)} non-monotonic timestamps")
            for seq, ts, prev_ts in non_monotonic[:5]:
                print(f"    Seq {seq}: {ts} <= {prev_ts}")

        # Check materialized declaration-view consistency.
        declaration_count = IsccDeclaration.objects.count()
        print(f"Declaration entries: {declaration_count} (should match record count: {count})")

        # Check for declarations with no backing log record.
        orphaned = IsccDeclaration.objects.exclude(iscc_id__in=LogRecord.objects.values("iscc_id")).count()
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
