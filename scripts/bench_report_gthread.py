"""
Build a standalone HTML report for the gthread-vs-sync benchmark experiment.

Where scripts/bench_report.py renders a single SQLite-vs-PostgreSQL pairwise comparison,
this report consumes N labeled result files from scripts/bench_load.py and answers one
question: does running Gunicorn with threads (gthread) beat the plain sync worker config?

It shows two stories:

- Part A (write-only): throughput and write-latency vs concurrency for every config. The
  honest expectation is gthread approximately equal to sync, since the single-writer
  sequencer bounds write throughput regardless of how requests are dispatched.
- Part B (mixed read+write): read-latency vs concurrency, sync vs gthread. This is the
  experiment that justifies gthread — under write contention a parked sync worker is
  idle-but-occupied and reads queue behind it, while a gthread worker keeps serving reads
  on other threads. A collapsing sync read p95 next to a flat gthread read p95 is the win.

The page is fully self-contained (inline CSS and SVG, no external assets) and reuses the
chart and style helpers from scripts/bench_report.py so both reports look identical.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import bench_report as br

# Distinct on-brand colours, one per labeled config (cycles if there are more than six).
PALETTE = ["#16a3b8", "#0054b2", "#e8833a", "#0a8a3a", "#8e44ad", "#c0392b"]


def is_mixed(result):
    # type: (dict) -> bool
    """Return True when the result was produced by a mixed read+write run."""
    return result.get("read_fraction", 0.0) > 0.0


def config_label(result):
    # type: (dict) -> str
    """Human label for a config, taken verbatim from the run's backend tag."""
    return result["backend"]


def worker_shape(result):
    # type: (dict) -> str
    """Render the worker x thread shape, e.g. '4 x 4'."""
    return f"{result.get('workers', 4)} x {result.get('threads', 1)}"


def level_at(result, concurrency):
    # type: (dict, int) -> dict
    """Return the per-level metrics dict at a given concurrency (or the peak as a fallback)."""
    for level in result["levels"]:
        if level["concurrency"] == concurrency:
            return level
    return max(result["levels"], key=lambda level: level["throughput"])


def throughput_of(level):
    # type: (dict) -> float
    """Accepted operations per second at this level."""
    return level["throughput"]


def write_p95_of(level):
    # type: (dict) -> float
    """Write p95 latency (ms); falls back to the generic latency block for write-only runs."""
    return (level.get("write_latency_ms") or level["latency_ms"])["p95"]


def read_p95_of(level):
    # type: (dict) -> float
    """Read p95 latency (ms) for a mixed run (0.0 when the level recorded no reads)."""
    return level.get("read_latency_ms", {}).get("p95", 0.0)


def accept_rate(result):
    # type: (dict) -> float
    """Overall fraction of accepted operations across all measured levels."""
    total = sum(level["count"] for level in result["levels"])
    success = sum(level["success"] for level in result["levels"])
    return success / total if total else 0.0


def status_count(result, code):
    # type: (dict, str) -> int
    """Total number of responses with a given HTTP status code across all levels."""
    return sum(level.get("status_codes", {}).get(code, 0) for level in result["levels"])


def series_for(results, categories, accessor):
    # type: (list[dict], list[str], object) -> list[dict]
    """Build grouped-bar series (one per config) by reading ``accessor`` at each concurrency."""
    return [
        {
            "name": config_label(result),
            "color": PALETTE[index % len(PALETTE)],
            "values": [accessor(level_at(result, int(category))) for category in categories],
        }
        for index, result in enumerate(results)
    ]


def chart_card(title, lede, series, categories, y_suffix, hint):
    # type: (str, str, list[dict], list[str], str, str) -> str
    """Render one titled chart card (grouped bars + legend + hint)."""
    axis_max = br.nice_ceiling(max((value for s in series for value in s["values"]), default=1.0))
    svg = br.grouped_bar_svg(categories, series, axis_max, y_suffix)
    return f"""
  <section>
    <h2>{title}</h2>
    <p class="lede">{lede}</p>
    <div class="card">
      {svg}
      {br.legend_html(series)}
      <p class="hint">{hint}</p>
    </div>
  </section>"""


def summary_table(results):
    # type: (list[dict]) -> str
    """Render the all-configs summary matrix (peak throughput, accept rate, 4xx breakdown)."""
    rows = ""
    for result in results:
        mode = f"mixed ({result['read_fraction']:.0%} reads)" if is_mixed(result) else "write-only"
        unit = "ops/s" if is_mixed(result) else "decl/s"
        rows += f"""
        <tr>
          <td>{config_label(result)}</td>
          <td>{worker_shape(result)}</td>
          <td>{mode}</td>
          <td>{br.human_int(result["peak_throughput"])} {unit}</td>
          <td>{result["peak_concurrency"]}</td>
          <td>{accept_rate(result) * 100:.1f}%</td>
          <td>{status_count(result, "400")}</td>
          <td>{status_count(result, "500")}</td>
        </tr>"""
    return f"""
  <section>
    <h2>All configurations at a glance</h2>
    <div class="card">
      <table>
        <thead>
          <tr>
            <th>Config</th><th>Workers x threads</th><th>Workload</th>
            <th>Peak throughput</th><th>Peak clients</th><th>Accepted</th>
            <th>4xx</th><th>5xx</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
  </section>"""


def part_b_hero(mixed, categories):
    # type: (list[dict], list[str]) -> str
    """Render the Part B punchline: read p95 at the highest concurrency, one card per config."""
    top = int(categories[-1])
    cards = "".join(
        f"""
        <div class="hero-card">
          <p class="label">{config_label(result)}</p>
          <div class="big" style="color:{PALETTE[index % len(PALETTE)]}">
            {read_p95_of(level_at(result, top)):,.0f}</div>
          <div class="unit">read p95 latency (ms)</div>
          <div class="foot">at {top} concurrent clients &middot; {result["read_fraction"]:.0%} reads</div>
        </div>"""
        for index, result in enumerate(mixed)
    )
    return f'<div class="heroes">{cards}</div>'


def build_html(results, generated):
    # type: (list[dict], str) -> str
    """Assemble the full standalone gthread-vs-sync report from all labeled results."""
    categories = [str(level["concurrency"]) for level in results[0]["levels"]]
    write_only = [r for r in results if not is_mixed(r)]
    mixed = [r for r in results if is_mixed(r)]

    sections = [summary_table(results)]

    if write_only:
        sections.append(
            chart_card(
                "Part A &middot; Write throughput as load increases",
                "Write-only workload. The single-writer sequencer bounds the rate, so gthread is "
                "expected to roughly match sync here &mdash; taller is better, but parity is the honest result.",
                series_for(write_only, categories, throughput_of),
                categories,
                "",
                "Accepted declarations per second (higher is better) &middot; X-axis: simultaneous clients",
            )
        )
        sections.append(
            chart_card(
                "Part A &middot; Write response time as load increases",
                "End-to-end write p95 latency at each load. Shorter is better.",
                series_for(write_only, categories, write_p95_of),
                categories,
                " ms",
                "Write p95 latency in milliseconds (lower is better) &middot; X-axis: simultaneous clients",
            )
        )

    hero = ""
    if mixed:
        hero = part_b_hero(mixed, categories)
        sections.append(
            chart_card(
                "Part B &middot; Read latency under write contention",
                "The decisive chart. Mixed read+write load: if reads queue behind occupied sync workers, "
                "sync read p95 climbs with concurrency while gthread stays flat. Shorter is better.",
                series_for(mixed, categories, read_p95_of),
                categories,
                " ms",
                "Read p95 latency in milliseconds (lower is better) &middot; X-axis: simultaneous clients",
            )
        )
        sections.append(
            chart_card(
                "Part B &middot; Write latency under the same mixed load",
                "Write p95 for the same mixed runs &mdash; writes still serialize on the one writer regardless "
                "of dispatch model, so this is the control. Shorter is better.",
                series_for(mixed, categories, write_p95_of),
                categories,
                " ms",
                "Write p95 latency in milliseconds (lower is better) &middot; X-axis: simultaneous clients",
            )
        )

    notes = """
  <section>
    <h2>How we measured this</h2>
    <div class="card method">
      <ul>
        <li><strong>Real work, end to end.</strong> Every write is an independently signed IsccNote that the Hub
          fully verifies (signature + content codes) before an atomic sequenced commit. Every read is a real
          resolution or exact-match search against the live API &mdash; no mocks.</li>
        <li><strong>Identical workload.</strong> All configs replay the exact same pre-generated corpus, and the
          mixed runs use a seeded request sequence so sync and gthread face a byte-for-byte identical mix.</li>
        <li><strong>sync vs gthread.</strong> "sync" is one request per worker process; "gthread" adds threads per
          worker so a thread parked on the writer's lock releases the GIL and other threads keep serving.</li>
        <li><strong>The honest hypothesis.</strong> gthread is not expected to raise the write ceiling (one writer
          bounds it). The payoff, if any, is read latency staying low while writers wait. A null result here is a
          real finding, and means the sync config stands.</li>
      </ul>
    </div>
  </section>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>ISCC Hub - gthread vs sync Performance</title>
<style>{br.CSS}</style>
</head>
<body>
<header class="hero">
  <div class="wrap">
    <p class="eyebrow">ISCC Discovery Protocol &middot; Performance Report</p>
    <h1>Does threading the workers help the ISCC Hub?</h1>
    <p class="sub">Gunicorn sync vs gthread under concurrent load &mdash; write throughput and read latency</p>
  </div>
</header>

<div class="wrap">
  {hero}
  {"".join(sections)}
  {notes}
  <footer>
    Generated {generated} &middot; ISCC Hub reference implementation &middot; benchmark configuration
  </footer>
</div>
</body>
</html>
"""


def main():
    # type: () -> None
    """Read all labeled result files and write the standalone gthread-vs-sync HTML report."""
    parser = argparse.ArgumentParser(description="Build the ISCC Hub gthread-vs-sync performance report")
    parser.add_argument("results", nargs="+", help="Result JSON files from bench_load.py run (any number)")
    parser.add_argument("--out", default="cauldron/gthread-performance.html")
    args = parser.parse_args()

    results = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.results]
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    html = build_html(results, generated)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote report -> {out_path}")


if __name__ == "__main__":
    main()
