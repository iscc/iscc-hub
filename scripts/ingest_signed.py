"""
Ingest a directory of pre-signed IsccNote declarations into a running ISCC Hub.

Reads every ``*.iscc.sig.json`` file from a directory and POSTs each verbatim to the
Hub's ``/declaration`` endpoint over HTTP at a bounded concurrency, then reports
end-to-end throughput (declarations per second), latency percentiles, and a full
breakdown of HTTP status codes and transport errors. Each file is a complete, real
signed declaration, so the Hub performs full signature verification, ISCC validation,
duplicate checking, and an atomic sequenced write for every request.

This is a measurement/smoke tool: it never generates or mutates declarations, it only
replays the signed files exactly as they are on disk. The body bytes are read up front
so file I/O never competes with the server during the timed run.
"""

import argparse
import asyncio
import json
import math
import statistics
import sys
import time
from pathlib import Path

import httpx


def load_bodies(directory, limit=None):
    # type: (Path, int|None) -> list[bytes]
    """Read signed declaration files into raw JSON request bodies, ordered by filename."""
    paths = sorted(directory.glob("*.iscc.sig.json"))
    if limit is not None:
        paths = paths[:limit]
    return [p.read_bytes() for p in paths]


def _percentile(ordered, p):
    # type: (list[float], float) -> float
    """Return the nearest-rank percentile (p in 0..1) from a pre-sorted ascending list."""
    idx = min(len(ordered) - 1, max(0, math.ceil(p * len(ordered)) - 1))
    return ordered[idx]


def percentiles(values_ms):
    # type: (list[float]) -> dict
    """Compute latency summary statistics (milliseconds) from a list of samples."""
    if not values_ms:
        return {"avg": 0.0, "min": 0.0, "max": 0.0, "p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0}
    ordered = sorted(values_ms)
    return {
        "avg": statistics.fmean(ordered),
        "min": ordered[0],
        "max": ordered[-1],
        "p50": _percentile(ordered, 0.50),
        "p90": _percentile(ordered, 0.90),
        "p95": _percentile(ordered, 0.95),
        "p99": _percentile(ordered, 0.99),
    }


async def send_one(client, sem, body):
    # type: (httpx.AsyncClient, asyncio.Semaphore, bytes) -> tuple[int|None, float, str|None]
    """POST a single declaration body and return (status, latency_ms, error)."""
    async with sem:
        start = time.perf_counter()
        try:
            resp = await client.post("/declaration", content=body, headers={"content-type": "application/json"})
            return resp.status_code, (time.perf_counter() - start) * 1000.0, None
        except Exception as exc:  # network/timeout errors are recorded, not raised
            return None, (time.perf_counter() - start) * 1000.0, type(exc).__name__


async def ingest(url, bodies, concurrency):
    # type: (str, list[bytes], int) -> tuple[list[tuple[int|None, float, str|None]], float]
    """Replay all bodies against the Hub with at most ``concurrency`` requests in flight."""
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    timeout = httpx.Timeout(120.0)
    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(base_url=url, limits=limits, timeout=timeout) as client:
        start = time.perf_counter()
        results = await asyncio.gather(*(send_one(client, sem, b) for b in bodies))
        wall = time.perf_counter() - start
    return results, wall


def summarize(results, wall, concurrency):
    # type: (list[tuple[int|None, float, str|None]], float, int) -> dict
    """Aggregate per-request results into a throughput + status/error report."""
    status_codes = {}  # type: dict[str, int]
    errors = {}  # type: dict[str, int]
    latencies = []  # type: list[float]
    created = 0
    for status, latency_ms, error in results:
        if status is None:
            errors[error] = errors.get(error, 0) + 1
            continue
        # Every HTTP response (including 409 duplicates and 500s) contributes to the latency
        # distribution; transport failures are counted separately above and left out so a single
        # timeout cannot dominate the tail.
        status_codes[str(status)] = status_codes.get(str(status), 0) + 1
        latencies.append(latency_ms)
        if status == 201:
            created += 1
    total = len(results)
    return {
        "concurrency": concurrency,
        "total": total,
        "created": created,
        "failed": total - created,
        "wall_seconds": wall,
        "throughput_decl_s": created / wall if wall > 0 else 0.0,
        "latency_ms": percentiles(latencies),
        "status_codes": status_codes,
        "errors": errors,
    }


def print_report(report):
    # type: (dict) -> None
    """Print a human-readable summary of an ingestion run."""
    pct = report["latency_ms"]
    print("\n=== Ingestion report ===")
    print(f"  concurrency:   {report['concurrency']}")
    print(f"  declarations:  {report['total']}")
    print(f"  created (201): {report['created']}")
    print(f"  failed:        {report['failed']}")
    print(f"  wall time:     {report['wall_seconds']:.2f} s")
    print(f"  throughput:    {report['throughput_decl_s']:.1f} decl/s")
    latency = "  ".join(f"{k} {pct[k]:.0f}" for k in ("avg", "p50", "p95", "p99", "max"))
    print(f"  latency (ms):  {latency}")
    print(f"  status codes:  {report['status_codes']}")
    if report["errors"]:
        print(f"  errors:        {report['errors']}")


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


async def run(args):
    # type: (argparse.Namespace) -> None
    """Load the signed declarations, replay them against the Hub, and report results."""
    bodies = load_bodies(Path(args.dir), args.limit)
    if not bodies:
        raise SystemExit(f"No *.iscc.sig.json files found in {args.dir}")
    print(f"Loaded {len(bodies)} signed declarations from {args.dir}")
    await wait_healthy(args.url)
    print(f"Ingesting into {args.url} at concurrency {args.concurrency} ...")
    results, wall = await ingest(args.url, bodies, args.concurrency)
    report = summarize(results, wall, args.concurrency)
    print_report(report)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"  wrote {out_path}")


def main():
    # type: () -> None
    """Parse arguments and run the ingestion."""
    parser = argparse.ArgumentParser(description="Ingest pre-signed ISCC declarations into a running Hub")
    parser.add_argument("--dir", required=True, help="Directory containing *.iscc.sig.json files")
    parser.add_argument(
        "--url", default="http://localhost:8000", help="Base URL of the running Hub (default: http://localhost:8000)"
    )
    parser.add_argument("--concurrency", type=int, default=16, help="Max simultaneous in-flight requests")
    parser.add_argument("--limit", type=int, default=None, help="Ingest only the first N files (probe runs)")
    parser.add_argument("--out", default=None, help="Optional path to write the JSON report")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    main()
