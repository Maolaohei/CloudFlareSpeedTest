"""TCP latency test (TCPing).

Mirrors tcping.go exactly:
- Opens TCP connection to ip:port, measures connect time
- N attempts per IP, calculates avg delay and loss rate
- No TLS, no HTTP — pure TCP dial, fast and reliable
"""

import asyncio
import time

from config import Config


class LatencyResult:
    def __init__(self, ip: str):
        self.ip = ip
        self.avg_latency: float = 0.0
        self.loss_rate: float = 0.0
        self.min_latency: float = 9999.0
        self.max_latency: float = 0.0
        self.latencies: list[float] = []
        self.colo: str = ""


async def _tcping_one(
    ip: str,
    port: int,
    count: int,
    interval_ms: float,
    sem: asyncio.Semaphore,
    timeout: float = 1.0,
) -> LatencyResult:
    """TCP ping: open TCP connection, measure time, close. Like Go tcping()."""
    result = LatencyResult(ip)

    async with sem:
        for i in range(count):
            try:
                t0 = time.monotonic()
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(ip, port),
                    timeout=timeout,
                )
                elapsed = (time.monotonic() - t0) * 1000
                writer.close()
                await writer.wait_closed()
                result.latencies.append(elapsed)
                if elapsed < result.min_latency:
                    result.min_latency = elapsed
                if elapsed > result.max_latency:
                    result.max_latency = elapsed
            except (asyncio.TimeoutError, OSError, Exception):
                pass

            if i < count - 1:
                await asyncio.sleep(interval_ms / 1000.0)

    total = len(result.latencies)
    if count > 0:
        result.loss_rate = (count - total) / count
    if total > 0:
        result.avg_latency = sum(result.latencies) / total
    else:
        result.avg_latency = 9999.0
        result.loss_rate = 1.0
        result.min_latency = 9999.0

    return result


def _format_result(r: LatencyResult) -> str:
    if r.avg_latency >= 9998:
        return f"{r.ip:<16} [全部超时]"
    return (
        f"{r.ip:<16} 均:{r.avg_latency:>6.1f}ms "
        f"底:{r.min_latency:>5.0f}ms "
        f"大:{r.max_latency:>5.0f}ms "
        f"丢:{r.loss_rate*100:>4.0f}%"
    )


async def run_latency_tests(
    ips: list[str],
    config: Config,
    progress_callback=None,
) -> list[LatencyResult]:
    port = 443  # Like Go's default TCPPort

    print(f"\n[*] 开始 TCP 延迟测试 ({len(ips)} 个 IP, 端口: {port}, 每IP {config.latency_test_count} 次)")
    print(f"    并发: {config.concurrency}, 间隔: {config.ping_interval_ms}ms, 超时: 1s")
    print(f"    淘汰阈值: 平均>{config.max_latency}ms")
    print()

    sem = asyncio.Semaphore(config.concurrency)

    tasks = [
        _tcping_one(ip, port, config.latency_test_count,
                     config.ping_interval_ms, sem, timeout=1.0)
        for ip in ips
    ]

    results: list[LatencyResult] = []
    completed = 0
    total = len(tasks)

    print(f"  {'IP':<16} {'平均':>7} {'最低':>6} {'最高':>6} {'丢包':>5}")
    print(f"  {'-'*16} {'-'*7} {'-'*6} {'-'*6} {'-'*5}")

    for coro in asyncio.as_completed(tasks):
        r = await coro
        results.append(r)
        completed += 1

        if progress_callback:
            progress_callback(completed, total)

        # Show samples: every 50, or good IPs (<100ms)
        if completed % 50 == 0 or completed == total or r.avg_latency < 100:
            print(f"  [{completed:>4}/{total}] {_format_result(r)}")

        # Summary at milestones
        if completed % 200 == 0 or completed == total:
            alive = [x for x in results if x.avg_latency < 9998]
            passed = [x for x in alive if x.avg_latency <= config.max_latency]
            if alive:
                best = min(alive, key=lambda x: x.avg_latency)
                print(f"  {'─'*50}")
                print(f"  [汇总] 已测:{completed}  存活:{len(alive)}  "
                      f"达标(≤{config.max_latency}ms):{len(passed)}  "
                      f"最佳: {best.ip} {best.avg_latency:.1f}ms")
                print()

    # Final summary
    alive = [x for x in results if x.avg_latency < 9998]
    passed = [x for x in alive if x.avg_latency <= config.max_latency]

    print(f"  {'='*50}")
    print(f"  [延迟测试完成]")
    print(f"    总数: {len(results)}  存活: {len(alive)}  死IP: {len(results)-len(alive)}")
    print(f"    达标(≤{config.max_latency}ms): {len(passed)}")
    if alive:
        best5 = sorted(alive, key=lambda x: x.avg_latency)[:5]
        print(f"  Top 5 最低延迟:")
        for i, r in enumerate(best5):
            print(f"    [{i+1}] {r.ip}  均:{r.avg_latency:.1f}ms  "
                  f"底:{r.min_latency:.0f}ms  丢:{r.loss_rate*100:.0f}%")
    print()

    return results


def run_latency_tests_sync(ips: list[str], config: Config) -> list[LatencyResult]:
    return asyncio.run(run_latency_tests(ips, config))
