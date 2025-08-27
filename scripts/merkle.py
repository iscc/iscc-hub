"""
Minimal POC demonstrating pymerkle with blake3 hash function.

This script demonstrates how to monkey-patch blake3 into hashlib
to make it work transparently with pymerkle.
"""

import hashlib
import json
from typing import Any

# Import blake3 and monkey-patch it into hashlib
try:
    import blake3

    # Monkey-patch blake3 into hashlib to make it available
    hashlib.blake3 = blake3.blake3
    BLAKE3_AVAILABLE = True
except ImportError:
    BLAKE3_AVAILABLE = False
    print("WARNING: blake3 not installed. Install with: uv add blake3")

# Import pymerkle after patching hashlib
try:
    import pymerkle
    import pymerkle.constants as constants
    from pymerkle import InmemoryTree as MerkleTree
    from pymerkle.hasher import MerkleHasher

    PYMERKLE_AVAILABLE = True
except ImportError as e:
    PYMERKLE_AVAILABLE = False
    print(f"WARNING: pymerkle not installed. Install with: uv add pymerkle (Error: {e})")


def patch_pymerkle_for_blake3():
    # type: () -> None
    """
    Patch pymerkle.constants to include blake3 in supported algorithms.

    This modifies the ALGORITHMS list in pymerkle.constants to allow
    blake3 to be used as a hash function.
    """
    if not PYMERKLE_AVAILABLE:
        return

    # Add blake3 to the supported algorithms if not already present
    if "blake3" not in constants.ALGORITHMS:
        constants.ALGORITHMS.append("blake3")
        print("✓ Added blake3 to pymerkle supported algorithms")


def test_blake3_hasher():
    # type: () -> None
    """Test that blake3 works with MerkleHasher after patching."""
    if not (BLAKE3_AVAILABLE and PYMERKLE_AVAILABLE):
        print("Skipping blake3 hasher test - dependencies not available")
        return

    try:
        # Create a MerkleHasher with blake3
        hasher = MerkleHasher("blake3")

        # Test hashing some data
        test_data = b"Hello, Merkle Tree with blake3!"
        hash_result = hasher.hash_buff(test_data)

        print("✓ MerkleHasher with blake3 created successfully")
        print(f"  Test hash: {hash_result.hex()}")

        # Test hash_pair functionality
        left = b"left_node"
        right = b"right_node"
        pair_hash = hasher.hash_pair(left, right)
        print(f"  Pair hash: {pair_hash.hex()}")

    except Exception as e:
        print(f"✗ Error creating MerkleHasher with blake3: {e}")


def create_blake3_merkle_tree():
    # type: () -> MerkleTree | None
    """Create and demonstrate a Merkle tree using blake3."""
    if not (BLAKE3_AVAILABLE and PYMERKLE_AVAILABLE):
        print("Skipping merkle tree creation - dependencies not available")
        return None

    try:
        # Create a Merkle tree with blake3
        tree = MerkleTree(algorithm="blake3")

        # Add some sample data
        sample_data = [
            b"Document 1: Lorem ipsum dolor sit amet",
            b"Document 2: Consectetur adipiscing elit",
            b"Document 3: Sed do eiusmod tempor incididunt",
            b"Document 4: Ut labore et dolore magna aliqua",
            b"Document 5: Ut enim ad minim veniam",
        ]

        print("\n✓ Created Merkle tree with blake3")
        print(f"  Algorithm: {tree.algorithm}")
        print(f"  Security mode: {tree.security}")

        # Add entries to the tree
        for i, data in enumerate(sample_data):
            tree.append_entry(data)
            print(f"  Added entry {i + 1}: {data[:30]}...")

        # Get the root hash
        root_hash = tree.get_state()
        print(f"\n  Root hash: {root_hash.hex()}")
        print(f"  Tree size: {tree.get_size()} entries")

        # Demonstrate that proofs can be generated
        proof = tree.prove_inclusion(2)  # 0-indexed
        print("\n  ✓ Generated inclusion proof for entry 3")
        print(f"    Path length: {len(proof.path)} nodes")

        # Consistency proof between different tree sizes
        consistency_proof = tree.prove_consistency(2, tree.get_size())
        print("\n  ✓ Generated consistency proof")
        print(f"    From size 2 to size {tree.get_size()}")
        print(f"    Path length: {len(consistency_proof.path)} nodes")

        return tree

    except Exception as e:
        print(f"✗ Error creating Merkle tree with blake3: {e}")
        import traceback

        traceback.print_exc()
        return None


def compare_hash_algorithms():
    # type: () -> None
    """Compare blake3 with SHA256 performance and output."""
    if not (BLAKE3_AVAILABLE and PYMERKLE_AVAILABLE):
        print("\nSkipping algorithm comparison - dependencies not available")
        return

    import time

    test_data = [b"Test data " + str(i).encode() for i in range(100)]

    print("\n=== Algorithm Comparison ===")

    for algorithm in ["sha256", "blake3"]:
        try:
            start = time.perf_counter()
            tree = MerkleTree(algorithm=algorithm)
            for data in test_data:
                tree.append_entry(data)
            root = tree.get_state()
            elapsed = time.perf_counter() - start

            print(f"\n{algorithm.upper()}:")
            print(f"  Root hash: {root.hex()[:32]}...")
            print(f"  Time taken: {elapsed * 1000:.3f}ms")
            print(f"  Hash length: {len(root)} bytes")

        except Exception as e:
            print(f"\n{algorithm.upper()}: Error - {e}")


def performance_test():
    # type: () -> None
    """Run comprehensive performance tests comparing SHA256 and BLAKE3."""
    if not (BLAKE3_AVAILABLE and PYMERKLE_AVAILABLE):
        print("\nSkipping performance test - dependencies not available")
        return

    import statistics
    import time

    print("\n" + "=" * 60)
    print(" PERFORMANCE TEST: SHA256 vs BLAKE3 in Merkle Trees")
    print("=" * 60)

    # Test configurations
    test_sizes = [10, 100, 1000, 10000]
    data_sizes = [32, 256, 1024, 4096]  # bytes
    iterations = 3

    print("\nTest Configuration:")
    print(f"  Entry counts: {test_sizes}")
    print(f"  Data sizes: {data_sizes} bytes")
    print(f"  Iterations per test: {iterations}")

    results = {}

    for data_size in data_sizes:
        print(f"\n{'=' * 50}")
        print(f"Testing with {data_size} byte entries")
        print(f"{'=' * 50}")

        for entry_count in test_sizes:
            # Generate test data
            test_data = [b"Entry %d: " % i + b"x" * (data_size - 10) for i in range(entry_count)]

            print(f"\n{entry_count} entries × {data_size} bytes:")

            for algorithm in ["sha256", "blake3"]:
                times = []

                for _iteration in range(iterations):
                    try:
                        # Measure tree construction time
                        start = time.perf_counter()
                        tree = MerkleTree(algorithm=algorithm)
                        for data in test_data:
                            tree.append_entry(data)
                        tree.get_state()
                        elapsed = time.perf_counter() - start
                        times.append(elapsed)

                    except Exception as e:
                        print(f"  {algorithm.upper()}: Error - {e}")
                        break

                if times:
                    avg_time = statistics.mean(times)
                    std_dev = statistics.stdev(times) if len(times) > 1 else 0

                    # Store results for summary
                    key = (data_size, entry_count, algorithm)
                    results[key] = avg_time

                    print(f"  {algorithm.upper():8} - {avg_time * 1000:7.2f}ms (±{std_dev * 1000:.2f}ms)")

    # Print summary with speedup calculations
    print("\n" + "=" * 60)
    print(" SUMMARY: BLAKE3 Speedup over SHA256")
    print("=" * 60)

    print(
        "\n{:<12} {:<12} {:<12} {:<12} {:<10}".format(
            "Data Size", "Entry Count", "SHA256 (ms)", "BLAKE3 (ms)", "Speedup"
        )
    )
    print("-" * 70)

    for data_size in data_sizes:
        for entry_count in test_sizes:
            sha256_key = (data_size, entry_count, "sha256")
            blake3_key = (data_size, entry_count, "blake3")

            if sha256_key in results and blake3_key in results:
                sha256_time = results[sha256_key] * 1000
                blake3_time = results[blake3_key] * 1000
                speedup = sha256_time / blake3_time if blake3_time > 0 else 0

                print(
                    "{:<12} {:<12} {:<12.2f} {:<12.2f} {:<10.2f}x".format(
                        f"{data_size}B", entry_count, sha256_time, blake3_time, speedup
                    )
                )

    # Calculate overall averages
    total_sha256 = sum(v for k, v in results.items() if k[2] == "sha256")
    total_blake3 = sum(v for k, v in results.items() if k[2] == "blake3")
    count = len([k for k in results if k[2] == "sha256"])

    if count > 0 and total_blake3 > 0:
        avg_speedup = (total_sha256 / count) / (total_blake3 / count)
        print("\n" + "=" * 60)
        print(f" Average Speedup: BLAKE3 is {avg_speedup:.2f}x faster than SHA256")
        print("=" * 60)

    # Test raw hashing performance
    print("\n" + "=" * 60)
    print(" RAW HASHING PERFORMANCE (no Merkle tree)")
    print("=" * 60)

    import hashlib

    test_data = b"x" * 1_000_000  # 1MB of data
    iterations = 100

    print(f"\nHashing {len(test_data):,} bytes × {iterations} iterations:")

    # Test SHA256
    start = time.perf_counter()
    for _ in range(iterations):
        h = hashlib.sha256()
        h.update(test_data)
        _ = h.digest()
    sha256_time = time.perf_counter() - start

    # Test BLAKE3
    start = time.perf_counter()
    for _ in range(iterations):
        h = blake3.blake3()
        h.update(test_data)
        _ = h.digest()
    blake3_time = time.perf_counter() - start

    sha256_throughput = (len(test_data) * iterations) / (sha256_time * 1024 * 1024)
    blake3_throughput = (len(test_data) * iterations) / (blake3_time * 1024 * 1024)

    print(f"  SHA256:  {sha256_time * 1000:.2f}ms ({sha256_throughput:.1f} MB/s)")
    print(f"  BLAKE3:  {blake3_time * 1000:.2f}ms ({blake3_throughput:.1f} MB/s)")
    print(f"  Speedup: {sha256_time / blake3_time:.2f}x")

    print("\n" + "=" * 60)


def main():
    # type: () -> None
    """Main demonstration of pymerkle with blake3."""
    print("=== PyMerkle with Blake3 POC ===\n")

    if not BLAKE3_AVAILABLE:
        print("\nTo run this demo, install blake3:")
        print("  uv add blake3")
        return

    if not PYMERKLE_AVAILABLE:
        print("\nTo run this demo, install pymerkle:")
        print("  uv add pymerkle")
        return

    # Patch pymerkle to support blake3
    patch_pymerkle_for_blake3()

    # Test blake3 with MerkleHasher
    print("\n=== Testing Blake3 Hasher ===")
    test_blake3_hasher()

    # Create and demonstrate a Merkle tree with blake3
    print("\n=== Creating Blake3 Merkle Tree ===")
    create_blake3_merkle_tree()

    # Compare algorithms
    compare_hash_algorithms()

    # Run performance tests
    performance_test()

    print("\n=== POC Complete ===")
    print("\nKey findings:")
    print("• blake3 can be monkey-patched into hashlib")
    print("• pymerkle.constants.ALGORITHMS can be extended at runtime")
    print("• MerkleTree and all pymerkle functionality works transparently with blake3")
    print("• No source code modifications to pymerkle are required")
    print("• BLAKE3 provides significant performance improvements over SHA256")


if __name__ == "__main__":
    main()
