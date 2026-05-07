"""Download speed test with EWMA time-sliced measurement.

Mirrors download.go:
- DNS hijack via socket.getaddrinfo (like Go's getDialContext)
- Lets urllib handle TLS/SNI/headers normally, only overrides TCP target IP
- Time-slices download into 100 intervals with EWMA smoothing
"""

import time
import socket
import urllib.request
import ssl
from urllib.parse import urlparse

from config import Config


class SpeedResult:
    def __init__(self, ip: str):
        self.ip = ip
        self.speed_mbps: float = 0.0
        self.colo: str = ""


class _EWMA:
    """Simple Exponential Weighted Moving Average (like Go's VividCortex/ewma)."""

    def __init__(self, alpha: float = 0.3):
        self.alpha = alpha
        self.value: float | None = None

    def add(self, val: float):
        if self.value is None:
            self.value = val
        else:
            self.value = self.alpha * val + (1 - self.alpha) * self.value

    def get(self) -> float:
        return self.value if self.value is not None else 0.0


def _dns_hijack(hostname: str, target_ip: str):
    """Temporarily hijack socket.getaddrinfo so `hostname` resolves to `target_ip`.

    Like Go's getDialContext in download.go — all DNS resolution for
    a specific host is redirected to our target IP, while TLS SNI and
    HTTP Host header still use the original hostname correctly.
    """
    import socket as _socket
    _orig = _socket.getaddrinfo

    def _patched(host, port, family=0, type=0, proto=0, flags=0):
        if host == hostname:
            host = target_ip
        return _orig(host, port, family, type, proto, flags)

    _socket.getaddrinfo = _patched
    return _orig


def _restore_dns(orig):
    socket.getaddrinfo = orig


def _measure_speed(ip: str, test_url: str, duration: int) -> tuple[float, str]:
    """Download via DNS-hijacked urllib with EWMA time-slicing."""
    parsed = urlparse(test_url)
    hostname = parsed.hostname or ""

    # Warm-up: 2s to let TCP slow-start settle, then measure
    warmup = 2.0 if duration >= 6 else 0.0
    measure_time = duration - warmup
    S = measure_time / 100  # time slice

    time_start = time.monotonic()
    measure_start = time_start + warmup
    time_end = time_start + duration

    ewma = _EWMA()
    bytes_total = 0
    last_bytes = 0
    time_counter = 1
    next_slice = measure_start + S * time_counter
    colo = ""

    try:
        orig_getaddrinfo = _dns_hijack(hostname, ip)

        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            https_handler = urllib.request.HTTPSHandler(context=ctx)
            opener = urllib.request.build_opener(https_handler)

            req = urllib.request.Request(test_url, headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_6) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/98.0.4758.80 Safari/537.36"
                ),
                "Accept": "*/*",
            })

            resp = opener.open(req, timeout=duration + 5)
            colo = resp.headers.get("cf-colo", resp.headers.get("colo", ""))

            while True:
                now = time.monotonic()

                # Check time slice before reading (like Go: check time, then Read)
                if now >= measure_start and now >= next_slice:
                    time_counter += 1
                    next_slice = measure_start + S * time_counter
                    ewma.add(bytes_total - last_bytes)
                    last_bytes = bytes_total

                if now >= time_end:
                    break

                chunk = resp.read(65536)
                if not chunk:
                    if now >= measure_start:
                        ewma.add(bytes_total - last_bytes)
                    break
                bytes_total += len(chunk)

        finally:
            _restore_dns(orig_getaddrinfo)

        if ewma.get() > 0:
            speed_mbps = (ewma.get() / S) / (1024 * 1024)
        else:
            # Fallback: use full download duration (avoid negative elapsed
            # when download completes during warmup before measure_start)
            elapsed = time.monotonic() - time_start
            speed_mbps = (bytes_total / elapsed) / (1024 * 1024) if elapsed > 0 else 0.0

    except urllib.request.HTTPError as e:
        speed_mbps = 0.0
        print(f"\n    [HTTP {e.code}] {ip}", end="")
    except Exception as e:
        speed_mbps = 0.0
        print(f"\n    [{type(e).__name__}] {ip}: {e!r}", end="")

    return speed_mbps, colo


def run_speed_tests(
    ips: list[str],
    config: Config,
    progress_callback=None,
) -> list[SpeedResult]:
    print(f"\n[*] 开始下载速度测试 ({len(ips)} 个 IP, 每IP {config.speed_test_duration} 秒)")
    warmup = 2 if config.speed_test_duration >= 6 else 0
    measure = config.speed_test_duration - warmup
    print(f"    预热: {warmup}s + 测量: {measure}s (EWMA 时间片: {measure/100*1000:.0f}ms x 100)")

    results = []
    for i, ip in enumerate(ips):
        print(f"  [{i+1}/{len(ips)}] 测速 {ip} ...", end=" ", flush=True)
        speed, colo = _measure_speed(ip, config.test_url, config.speed_test_duration)
        r = SpeedResult(ip)
        r.speed_mbps = speed
        r.colo = colo
        results.append(r)
        colo_str = f" [{colo}]" if colo else ""
        print(f"{speed:.1f} MB/s{colo_str}")
        if progress_callback:
            progress_callback(i + 1, len(ips))

    print("[*] 速度测试完成")
    return results
