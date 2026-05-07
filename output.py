import csv
import os
from datetime import datetime

from scorer import ScoredIP


def write_result_csv(
    scored: list[ScoredIP],
    output_file: str = "result.csv",
) -> str:
    """Write scored results to CSV. Returns the file path."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Use utf-8-sig for Excel compatibility
    with open(output_file, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["IP", "Speed(MB/s)", "Loss(%)", "Latency(ms)", "Score", "RecordTime"])
        for r in scored:
            writer.writerow([
                r.ip,
                f"{r.speed:.2f}",
                f"{r.loss * 100:.1f}",
                f"{r.latency:.1f}",
                f"{r.score:.2f}",
                now,
            ])

    full_path = os.path.abspath(output_file)
    print(f"\n[*] 结果已保存到: {full_path}")
    return full_path


def print_results(scored: list[ScoredIP], top_n: int = 20):
    """Print formatted results to console."""
    sep = "─" * 63
    print(f"\n  {sep}")
    print(f"  {'#':<4} {'IP':<15}  {'Speed':>10}  {'Latency':>9}  {'Loss':>7}  {'Score':>7}")
    print(f"  {sep}")
    for i, r in enumerate(scored[:top_n]):
        sp = f"{r.speed:.1f} MB/s"
        la = f"{r.latency:.1f} ms"
        lo = f"{r.loss*100:.1f}%"
        sc = f"{r.score:.2f}"
        print(f"  [{i+1:02d}] {r.ip:<15}  {sp:>10}  {la:>9}  {lo:>7}  {sc:>7}")
    print(f"  {sep}")
