from config import Config
from latency_tester import LatencyResult
from speed_tester import SpeedResult


class ScoredIP:
    def __init__(self, ip: str):
        self.ip = ip
        self.speed: float = 0.0
        self.latency: float = 0.0
        self.loss: float = 0.0
        self.score: float = 0.0


def filter_by_latency(
    latency_results: list[LatencyResult],
    config: Config,
) -> list[LatencyResult]:
    if not latency_results:
        return []

    # Layer 1: Absolute threshold
    passed = [
        r for r in latency_results
        if r.avg_latency <= config.max_latency and r.loss_rate < 1.0
    ]
    removed_abs = len(latency_results) - len(passed)
    if removed_abs:
        print(f"  [过滤] 绝对阈值(>{config.max_latency}ms): 淘汰 {removed_abs} 个")

    if not passed:
        print("[警告] 没有IP通过绝对阈值过滤")
        return []

    # Layer 2: Relative threshold
    best_latency = min(r.avg_latency for r in passed)
    filtered = [
        r for r in passed
        if r.avg_latency <= best_latency + config.latency_gap
    ]
    removed_rel = len(passed) - len(filtered)
    if removed_rel:
        print(f"  [过滤] 相对阈值(>{best_latency:.1f}+{config.latency_gap}ms): 淘汰 {removed_rel} 个")

    filtered.sort(key=lambda r: r.avg_latency)
    selected = filtered[:config.top_n]
    print(f"  [入选] 延迟排序后取前 {len(selected)} 个进入速度测试")

    return selected


def calculate_scores(
    latency_results: list[LatencyResult],
    speed_results: list[SpeedResult],
    config: Config,
) -> list[ScoredIP]:
    """Merge latency + speed results, normalize to 0-100, apply weighted scoring.

    Mirrors the 范本 script: each metric is normalized against the best/worst
    in the batch before weighting, so speed and latency contribute fairly
    regardless of their raw value scales.
    """
    speed_map: dict[str, float] = {}
    for sr in speed_results:
        speed_map[sr.ip] = sr.speed_mbps

    scored: list[ScoredIP] = []
    for lr in latency_results:
        s = ScoredIP(lr.ip)
        s.latency = lr.avg_latency
        s.loss = lr.loss_rate
        s.speed = speed_map.get(lr.ip, 0.0)
        scored.append(s)

    if not scored:
        return []

    # ── Penalty rules (only hard failures, not configurable thresholds) ──
    for s in scored:
        if s.loss > 0.3:
            s.score = -999

        if config.max_latency < 9998 and s.latency > config.max_latency:
            s.score = -999

    # ── Normalized scoring (0-100 per metric) ──
    valid = [s for s in scored if s.score > -999]
    if not valid:
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored

    max_speed = max(s.speed for s in valid) or 0.01
    min_lat = min(s.latency for s in valid if s.latency > 0) or 1
    max_loss = max(s.loss for s in valid) or 0.01
    lat_range = max(s.latency for s in valid) - min_lat
    lat_range = max(lat_range, config.latency_gap) or 100

    w_s = config.speed_weight
    w_l = config.latency_weight
    w_loss = config.loss_weight
    total_w = w_s + w_l + w_loss

    for s in valid:
        score_speed = (s.speed / max_speed) * 100
        score_lat = max(0, 100 - ((s.latency - min_lat) / lat_range) * 100)
        score_loss = max(0, 100 - (s.loss / max_loss) * 100) if max_loss > 0 else 100

        s.score = (
            score_speed * w_s +
            score_lat * w_l +
            score_loss * w_loss
        ) / total_w

    scored.sort(key=lambda r: r.score, reverse=True)
    return scored


def get_best_ips(scored: list[ScoredIP], count: int) -> list[str]:
    return [r.ip for r in scored[:count]]


def select_best_ips(scored: list[ScoredIP], count: int, speed_ratio: float = 0.8) -> list[str]:
    """Select best IPs with a speed floor (ratio of max speed in batch).

    IPs slower than speed_ratio * max_speed are excluded.
    If fewer than `count` IPs remain, all qualified IPs are returned
    and the DNS layer handles distribution / sharing.
    """
    if not scored:
        return []

    # Use only valid (non-penalty) IPs for max_speed to avoid inflated floor
    valid = [s for s in scored if s.score > -999] or scored
    max_speed = max(s.speed for s in valid)
    floor = max_speed * speed_ratio
    qualified = [s for s in scored if s.speed >= floor]

    removed = len(scored) - len(qualified)
    if removed > 0:
        print(f"  [筛选] 速度低于最快 {speed_ratio*100:.0f}% ({floor:.1f}MB/s): 淘汰 {removed} 个")

    selected = qualified[:count]
    if len(selected) < count:
        print(f"  [筛选] 合格 IP 仅 {len(selected)} 个 (需要 {count} 个)，将按可用数量分配")

    return [s.ip for s in selected]
