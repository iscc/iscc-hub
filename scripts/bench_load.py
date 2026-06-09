"""
End-to-end declaration write benchmark for a running ISCC Hub.

Measures how fast the Hub accepts signed ISCC declarations over HTTP under concurrent
load, end to end: each request is a real IsccNote with a fresh Ed25519 keypair, so the
server performs full signature verification, ISCC validation, duplicate checking, and an
atomic sequenced write before replying with an ISCC-ID.

Two subcommands keep generation, measurement, and backends cleanly separated:

- ``generate`` builds a reusable corpus of unique, pre-signed IsccNotes and writes it to
  a JSON file. Notes carry no client timestamp (the Hub assigns its own at sequencing
  time), so the exact same corpus replays cleanly against any backend on any day. The
  corpus is generated once and reused for SQLite and PostgreSQL so both backends process
  byte-for-byte identical payloads.

- ``run`` replays a slice of the corpus against ``--url`` at a sweep of concurrency
  levels, records end-to-end latency and throughput per level, and writes a JSON result
  file consumed by scripts/bench_report.py.

Payload generation (CPU heavy) happens entirely up front, never while requests are in
flight, so it never competes with the server during measurement.
"""

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from io import BytesIO
from pathlib import Path

import httpx
import iscc_core as ic
import iscc_crypto as icr

ISCC_NOTE_SCHEMA = "http://purl.org/iscc/schema/iscc-note-0.8.0.json"


def generate_note(index, hub_id=0):
    # type: (int, int) -> dict
    """
    Build one unique, fully signed IsccNote with no client timestamp.

    Unique random content gives every note a distinct datahash and ISCC-CODE; a random
    per-hub nonce makes each declaration unique. A fresh keypair per note is the realistic
    worst case (no signer-key caching on the server).

    :param index: Stable index used to vary metadata for readability.
    :param hub_id: Target Hub id, encoded into the nonce prefix (sandbox Hub is 0).
    :return: A signed IsccNote dict ready to POST to /declaration.
    """
    entropy = os.urandom(32).hex()
    text = f"Benchmark content {index} {entropy}"
    text_bytes = text.encode("utf-8")

    mcode = ic.gen_meta_code(f"Benchmark Item {index}", f"Synthetic declaration {index}", bits=256)
    ccode = ic.gen_text_code(text, bits=256)
    dcode = ic.gen_data_code(BytesIO(text_bytes), bits=256)
    icode = ic.gen_instance_code(BytesIO(text_bytes), bits=256)
    iscc_code = ic.gen_iscc_code([mcode["iscc"], ccode["iscc"], dcode["iscc"], icode["iscc"]])["iscc"]

    note = {
        "$schema": ISCC_NOTE_SCHEMA,
        "iscc_code": iscc_code,
        "datahash": icode["datahash"],
        "nonce": icr.create_nonce(hub_id),
        "gateway": f"https://benchmark.example.com/item/{index}",
        "metahash": mcode["metahash"],
        "units": [mcode["iscc"], ccode["iscc"], dcode["iscc"]],
    }
    keypair = icr.key_generate(controller=f"did:web:benchmark{index % 100}.example.com")
    return icr.sign_json(note, keypair)


def generate_chunk(chunk):
    # type: (tuple[int, int, int]) -> list[dict]
    """Generate a contiguous block of notes in a worker process."""
    start, count, hub_id = chunk
    return [generate_note(start + i, hub_id) for i in range(count)]


def generate_corpus(count, hub_id, out_path):
    # type: (int, int, Path) -> None
    """
    Generate ``count`` unique signed notes across all CPU cores and write them to JSON.

    Nonces are de-duplicated defensively; a collision in 124 random bits is astronomically
    unlikely but cheap to guard against.

    :param count: Number of notes to generate.
    :param hub_id: Target Hub id for the nonce prefix.
    :param out_path: Destination JSON file (a list of signed notes).
    """
    workers = os.cpu_count() or 4
    chunk_size = max(1, (count + workers - 1) // workers)
    chunks = [(i, min(chunk_size, count - i), hub_id) for i in range(0, count, chunk_size)]

    notes = []
    start = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for block in pool.map(generate_chunk, chunks):
            notes.extend(block)
    elapsed = time.perf_counter() - start

    seen = {n["nonce"] for n in notes}
    if len(seen) != len(notes):  # pragma: no cover - defensive, effectively never hit
        raise SystemExit("Nonce collision while generating corpus; rerun generation.")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(notes), encoding="utf-8")
    print(f"Generated {len(notes)} signed notes in {elapsed:.1f}s -> {out_path}")


def percentiles(values_ms):
    # type: (list[float]) -> dict
    """Compute latency summary statistics (milliseconds) from a list of samples."""
    if not values_ms:
        return {"avg": 0.0, "min": 0.0, "max": 0.0, "p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0}
    ordered = sorted(values_ms)

    def at(p):
        # type: (float) -> float
        idx = min(len(ordered) - 1, int(p * len(ordered)))
        return ordered[idx]

    return {
        "avg": statistics.fmean(ordered),
        "min": ordered[0],
        "max": ordered[-1],
        "p50": at(0.50),
        "p90": at(0.90),
        "p95": at(0.95),
        "p99": at(0.99),
    }


async def send_one(client, sem, body):
    # type: (httpx.AsyncClient, asyncio.Semaphore, bytes) -> tuple[int|None, float, str|None]
    """POST a single pre-serialized declaration and return (status, latency_ms, error)."""
    async with sem:
        start = time.perf_counter()
        try:
            resp = await client.post("/declaration", content=body, headers={"content-type": "application/json"})
            return resp.status_code, (time.perf_counter() - start) * 1000.0, None
        except Exception as exc:  # network/timeout errors are recorded, not raised
            return None, (time.perf_counter() - start) * 1000.0, type(exc).__name__


async def run_level(url, bodies, concurrency):
    # type: (str, list[bytes], int) -> dict
    """
    Replay ``bodies`` against ``url`` with at most ``concurrency`` requests in flight.

    :param url: Base URL of the running Hub.
    :param bodies: Pre-serialized declaration payloads (each used exactly once).
    :param concurrency: Maximum simultaneous in-flight requests for this level.
    :return: Per-level metrics dict (throughput, latency percentiles, status breakdown).
    """
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    timeout = httpx.Timeout(60.0)
    sem = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(base_url=url, limits=limits, timeout=timeout) as client:
        start = time.perf_counter()
        results = await asyncio.gather(*(send_one(client, sem, body) for body in bodies))
        wall = time.perf_counter() - start

    status_codes = {}
    errors = {}
    ok_latencies = []
    success = 0
    for status, latency_ms, error in results:
        if status is None:
            errors[error] = errors.get(error, 0) + 1
            continue
        status_codes[str(status)] = status_codes.get(str(status), 0) + 1
        if status == 201:
            success += 1
            ok_latencies.append(latency_ms)
    failed = len(results) - success

    throughput = success / wall if wall > 0 else 0.0
    print(
        f"  concurrency {concurrency:>3}: {success}/{len(results)} ok in {wall:6.2f}s "
        f"=> {throughput:7.1f} decl/s  (p95 {percentiles(ok_latencies)['p95']:.0f} ms)"
    )
    return {
        "concurrency": concurrency,
        "count": len(results),
        "success": success,
        "failed": failed,
        "success_rate": success / len(results) if results else 0.0,
        "wall_seconds": wall,
        "throughput": throughput,
        "latency_ms": percentiles(ok_latencies),
        "status_codes": status_codes,
        "errors": errors,
    }


async def wait_healthy(url, attempts=60):
    # type: (str, int) -> None
    """Poll the Hub /health endpoint until it responds or the attempts run out."""
    async with httpx.AsyncClient(base_url=url, timeout=5.0) as client:
        for _ in range(attempts):
            try:
                resp = await client.get("/health")
                if resp.status_code == 200:
                    return
            except Exception:
                pass
            await asyncio.sleep(1.0)
    raise SystemExit(f"Hub at {url} did not become healthy in time.")


async def run_benchmark(args):
    # type: (argparse.Namespace) -> None
    """Load the corpus, warm up, sweep concurrency levels, and write the result JSON."""
    corpus = json.loads(Path(args.corpus).read_text(encoding="utf-8"))
    levels = [int(x) for x in args.levels.split(",")]
    needed = args.warmup + args.per_level * len(levels)
    if len(corpus) < needed:
        raise SystemExit(f"Corpus has {len(corpus)} notes but {needed} are needed for this sweep.")

    bodies = [json.dumps(note).encode("utf-8") for note in corpus]

    print(f"\n=== Benchmarking {args.backend} at {args.url} ===")
    await wait_healthy(args.url)

    cursor = 0
    if args.warmup:
        print(f"  warming up with {args.warmup} declarations...")
        await run_level(args.url, bodies[cursor : cursor + args.warmup], min(args.warmup, 25))
        cursor += args.warmup

    level_results = []
    for concurrency in levels:
        result = await run_level(args.url, bodies[cursor : cursor + args.per_level], concurrency)
        level_results.append(result)
        cursor += args.per_level

    peak = max(level_results, key=lambda r: r["throughput"])
    payload = {
        "backend": args.backend,
        "url": args.url,
        "workers": args.workers,
        "per_level": args.per_level,
        "warmup": args.warmup,
        "total_declarations": sum(r["count"] for r in level_results),
        "peak_throughput": peak["throughput"],
        "peak_concurrency": peak["concurrency"],
        "levels": level_results,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"  peak: {peak['throughput']:.1f} decl/s at concurrency {peak['concurrency']} -> {out_path}")


def main():
    # type: () -> None
    """Parse arguments and dispatch to the generate or run subcommand."""
    parser = argparse.ArgumentParser(description="ISCC Hub end-to-end declaration write benchmark")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Generate a reusable corpus of signed IsccNotes")
    gen.add_argument("--count", type=int, default=10200)
    gen.add_argument("--hub-id", type=int, default=0)
    gen.add_argument("--out", default="data/bench/corpus.json")

    run = sub.add_parser("run", help="Replay the corpus against a running Hub and record metrics")
    run.add_argument("--backend", required=True, help="Backend label, e.g. SQLite or PostgreSQL")
    run.add_argument("--url", default="http://localhost:8000")
    run.add_argument("--corpus", default="data/bench/corpus.json")
    run.add_argument("--levels", default="10,25,50,100")
    run.add_argument("--per-level", type=int, default=2500)
    run.add_argument("--warmup", type=int, default=200)
    run.add_argument("--workers", type=int, default=4, help="Gunicorn worker count (recorded in the report)")
    run.add_argument("--out", required=True)

    args = parser.parse_args()
    if args.command == "generate":
        generate_corpus(args.count, args.hub_id, Path(args.out))
    else:
        asyncio.run(run_benchmark(args))


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    main()
