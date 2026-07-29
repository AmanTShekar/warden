"""
Warden — GPU power/telemetry capture harness (rocm-smi wrapper).

Captures power (W), GPU utilization (%), VRAM usage (MB), and temperature
at a fixed interval while a benchmark scenario runs. Computes total joules
(avg watts × elapsed seconds) so we can directly compare
adaptive-routing vs always-heavy scenarios.

Usage as a context manager (preferred):

    with PowerBenchmark(output_path="adaptive.csv") as bench:
        for prompt in prompts:
            router.route(prompt)
    summary = bench.summary  # {"joules": ..., "avg_watts": ..., ...}

Or run standalone for ad-hoc monitoring:

    python benchmarks/measure_power.py -o gpu.csv -d 60 -i 100

Run on AMD Radeon Cloud or any ROCm-enabled box. Falls back gracefully on
hosts without rocm-smi (writes an empty CSV + warning) so unit tests still
pass on Windows dev machines.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PowerSummary:
    """Aggregate telemetry summary for one benchmark scenario.

    `joules` is derived: avg_watts × duration_s — the headline metric.
    """
    output_csv: str = ""
    duration_s: float = 0.0
    samples: int = 0
    avg_watts: float = 0.0
    max_watts: float = 0.0
    avg_gpu_util_pct: float = 0.0
    max_gpu_util_pct: float = 0.0
    avg_vram_mb: float = 0.0
    max_vram_mb: float = 0.0
    avg_temp_c: float = 0.0
    gpu_name: str = ""
    rocm_available: bool = True

    @property
    def joules(self) -> float:
        """Total energy: avg_watts × duration_s. (Headline comparison number.)"""
        return self.avg_watts * self.duration_s

    def as_dict(self) -> dict:
        d = asdict(self)
        d["joules"] = self.joules  # add derived property to serialization
        return d


class PowerBenchmark:
    """
    Wrapper around rocm-smi to capture GPU telemetry.

    Uses --json mode for robust parsing (the old --csv column-order
    varies by rocm-smi version). Thread-safe: can run in the background
    while the foreground thread drives router.route() calls.
    """

    def __init__(self, output_path: str = "gpu_telemetry.csv", interval_ms: int = 100):
        self.output_path = output_path
        self.interval = interval_ms / 1000.0
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._rows: list[dict] = []
        self.summary: Optional[PowerSummary] = None
        self._start_time: float = 0.0

    # --- Context-manager API (preferred) ---

    def __enter__(self) -> "PowerBenchmark":
        self.start_monitoring()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop_monitoring()

    def start_monitoring(self) -> None:
        """Begin polling rocm-smi on a background thread."""
        self._stop_event.clear()
        self._rows = []
        self._start_time = time.perf_counter()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info(f"rocm-smi polling started → {self.output_path} @ {self.interval*1000:.0f}ms")

    def stop_monitoring(self) -> PowerSummary:
        """Stop polling and compute the summary."""
        if self._thread is None:
            return PowerSummary()
        self._stop_event.set()
        self._thread.join(timeout=5.0)
        self._thread = None
        self.summary = self._compute_summary()
        self._write_csv()
        return self.summary

    # --- Polling internals ---

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            sample = self._sample_rocm_smi()
            self._rows.append(sample)
            # Respect interval but respond quickly to stop signal.
            self._stop_event.wait(self.interval)

    def _sample_rocm_smi(self) -> dict:
        """One rocm-smi snapshot. Returns dict with normalized keys.

        Tries --json first (cleanest); falls back to --csv; finally to
        an "unavailable" row so the harness degrades gracefully off-GPU.
        """
        ts = datetime.now(timezone.utc).isoformat()
        if not self._rocmdsmi_available():
            return {
                "timestamp": ts,
                "power_w": None,
                "gpu_util_pct": None,
                "vram_used_mb": None,
                "temp_c": None,
                "available": False,
            }

        # Try JSON mode first — robust against column reordering.
        try:
            result = subprocess.run(
                ["rocm-smi", "--showpower", "--showuse", "--showmemuse", "--showtemp", "--json"],
                capture_output=True, text=True, timeout=5.0,
            )
            if result.returncode == 0 and result.stdout.strip():
                return self._parse_json_output(result.stdout, ts)
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            logger.debug(f"rocm-smi --json failed: {e}")

        # Fallback: plain CSV mode.
        try:
            result = subprocess.run(
                ["rocm-smi", "--showpower", "--showuse", "--showmemuse", "--showtemp", "--csv"],
                capture_output=True, text=True, timeout=5.0,
            )
            if result.returncode == 0 and result.stdout.strip():
                return self._parse_csv_output(result.stdout, ts)
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            logger.debug(f"rocm-smi --csv failed: {e}")

        return {
            "timestamp": ts,
            "power_w": None,
            "gpu_util_pct": None,
            "vram_used_mb": None,
            "temp_c": None,
            "available": False,
        }

    @staticmethod
    def _rocmdsmi_available() -> bool:
        """Fast PATH check so we don't fork+exec on every poll when missing."""
        from shutil import which
        return which("rocm-smi") is not None

    @staticmethod
    def _parse_json_output(stdout: str, ts: str) -> dict:
        """Parse rocm-smi --json output — keys vary by version, so we
        pattern-match substring against field names to be version-tolerant.
        """
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return {"timestamp": ts, "power_w": None, "gpu_util_pct": None,
                    "vram_used_mb": None, "temp_c": None, "available": False}

        # rocm-smi --json returns { "card0": { "Average Graphics Package Power (W)": "42", ... } }
        # Pull the first card's dict.
        card = next(iter(data.values())) if isinstance(data, dict) else data
        if not isinstance(card, dict):
            card = {}

        def find(key_substr: str) -> Optional[float]:
            for k, v in card.items():
                if key_substr.lower() in k.lower():
                    try:
                        # Strip units, leave numeric.
                        if isinstance(v, str):
                            v = v.strip().rstrip("W").rstrip("%").rstrip("C").rstrip("MB").strip()
                            return float(v)
                        return float(v)
                    except (TypeError, ValueError):
                        return None
            return None

        return {
            "timestamp": ts,
            "power_w": find("power") or find("(W)"),
            "gpu_util_pct": find("use") or find("util") or find("(%)"),
            "vram_used_mb": find("vram") or find("(MB)"),
            "temp_c": find("temp") or find("(C)"),
            "available": True,
        }

    @staticmethod
    def _parse_csv_output(stdout: str, ts: str) -> dict:
        """Best-effort CSV fallback — header line indicates columns."""
        lines = stdout.strip().splitlines()
        if len(lines) < 2:
            return {"timestamp": ts, "power_w": None, "gpu_util_pct": None,
                    "vram_used_mb": None, "temp_c": None, "available": False}
        header = [h.strip().lower() for h in lines[0].split(",")]
        vals = lines[-1].split(",")

        def col(*substrs: str) -> Optional[float]:
            for i, h in enumerate(header):
                if any(s in h for s in substrs):
                    try:
                        return float(vals[i].strip().rstrip("W%CM B"))
                    except (IndexError, ValueError):
                        return None
            return None

        return {
            "timestamp": ts,
            "power_w": col("power"),
            "gpu_util_pct": col("use", "util"),
            "vram_used_mb": col("vram"),
            "temp_c": col("temp"),
            "available": True,
        }

    # --- Summary + persistence ---

    def _compute_summary(self) -> PowerSummary:
        duration_s = time.perf_counter() - self._start_time
        available_rows = [r for r in self._rows if r.get("available") and r.get("power_w") is not None]
        if not available_rows:
            return PowerSummary(
                output_csv=self.output_path,
                duration_s=duration_s,
                samples=len(self._rows),
                rocm_available=bool(self._rows) and self._rows[0].get("available", False),
            )

        powers = [r["power_w"] or 0.0 for r in available_rows]
        utils = [r.get("gpu_util_pct") or 0.0 for r in available_rows]
        vrams = [r.get("vram_used_mb") or 0.0 for r in available_rows]
        temps = [r.get("temp_c") or 0.0 for r in available_rows]

        # Try to pick up the GPU product name for the report header.
        gpu_name = ""
        try:
            r = subprocess.run(["rocm-smi", "--showproductname"],
                               capture_output=True, text=True, timeout=5.0)
            if r.returncode == 0:
                for line in r.stdout.splitlines():
                    if "Card series" in line or "Device" in line.lower():
                        gpu_name = line.split(":", 1)[-1].strip()
                        break
        except Exception:
            pass

        avg_w = sum(powers) / len(powers) if powers else 0.0
        return PowerSummary(
            output_csv=self.output_path,
            duration_s=duration_s,
            samples=len(self._rows),
            avg_watts=avg_w,
            max_watts=max(powers) if powers else 0.0,
            avg_gpu_util_pct=(sum(utils) / len(utils) if utils else 0.0),
            max_gpu_util_pct=max(utils) if utils else 0.0,
            avg_vram_mb=(sum(vrams) / len(vrams) if vrams else 0.0),
            max_vram_mb=max(vrams) if vrams else 0.0,
            avg_temp_c=(sum(temps) / len(temps) if temps else 0.0),
            gpu_name=gpu_name,
            rocm_available=True,
        )

    def _write_csv(self) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.output_path)), exist_ok=True)
        with open(self.output_path, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["timestamp", "power_w", "gpu_util_pct", "vram_used_mb", "temp_c", "available"],
            )
            writer.writeheader()
            writer.writerows(self._rows)
        logger.info(f"Telemetry written → {self.output_path} ({len(self._rows)} samples)")

    def write_summary_json(self, summary_path: str) -> None:
        """Write a sidecar JSON summary (one row per scenario)."""
        if self.summary is None:
            self.summary = self._compute_summary()
        os.makedirs(os.path.dirname(os.path.abspath(summary_path)), exist_ok=True)
        with open(summary_path, "w") as f:
            json.dump(self.summary.as_dict(), f, indent=2)
        logger.info(f"Summary JSON → {summary_path}")


# --- CLI for ad-hoc standalone use ---

def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Warden GPU power/telemetry capture harness")
    parser.add_argument("--output", "-o", default="gpu_telemetry.csv", help="Output CSV path")
    parser.add_argument("--summary-json", "-s", default=None, help="Optional sidecar JSON summary path")
    parser.add_argument("--duration", "-d", type=float, default=60.0, help="Duration in seconds")
    parser.add_argument("--interval", "-i", type=int, default=100, help="Interval in milliseconds")
    args = parser.parse_args()

    bench = PowerBenchmark(output_path=args.output, interval_ms=args.interval)
    bench.start_monitoring()
    print(f"Capturing for {args.duration}s → {args.output} (Ctrl-C to stop early)")
    try:
        time.sleep(args.duration)
    except KeyboardInterrupt:
        pass
    summary = bench.stop_monitoring()
    if args.summary_json:
        bench.write_summary_json(args.summary_json)
    print("\n=== Summary ===")
    print(json.dumps(summary.as_dict(), indent=2))


if __name__ == "__main__":
    _main()
