import os
from dataclasses import dataclass, field


@dataclass
class Config:
    # Cloudflare API
    api_token: str = ""
    zone_id: str = ""
    domains: list[str] = field(default_factory=list)
    domain_counts: dict[str, int] = field(default_factory=dict)

    # Thresholds
    latency_gap: int = 20
    speed_weight: float = 50.0
    latency_weight: float = 30.0
    loss_weight: float = 20.0

    max_latency: int = 140

    # Test parameters
    latency_test_count: int = 20
    ping_interval_ms: int = 100
    speed_test_duration: int = 10
    concurrency: int = 200

    # Selection
    random_pick_count: int = 100
    top_n: int = 20

    # Speed test URL
    test_url: str = "https://speed.cloudflare.com/__down?bytes=100000000"

    def total_needed(self) -> int:
        return sum(self.domain_counts.values()) or 1


def load_env(env_file: str = "env.txt") -> Config:
    config = Config()

    if not os.path.exists(env_file):
        print(f"[警告] 找不到配置文件: {env_file}，使用默认值")
        return config

    raw: dict[str, str] = {}
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            line = line.replace("：", ":")
            if ":" in line:
                key, val = line.split(":", 1)
                raw[key.strip()] = val.strip()

    def _get(k: str, default=None):
        return raw.get(k, default)

    config.api_token = _get("CF API 令牌", "")
    config.zone_id = _get("CF Zone ID", "")

    # Parse domains
    domain_str = _get("CF 解析域名", "")
    for item in domain_str.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            d, c = item.split(":", 1)
            d = d.strip()
            config.domains.append(d)
            config.domain_counts[d] = int(c.strip())
        else:
            config.domains.append(item)
            config.domain_counts[item] = 1

    config.latency_gap = int(_get("CF 延迟差距", "20"))
    config.speed_weight = float(_get("CF 速度权重", "50"))
    config.latency_weight = float(_get("CF 延迟权重", "30"))
    config.loss_weight = float(_get("CF 丢包权重", "20"))

    config.max_latency = int(_get("CF 平均延迟", "140"))
    config.latency_test_count = int(_get("CF 延迟测试次数", "20"))
    config.ping_interval_ms = int(_get("CF 丢包测试频率", "100"))
    config.speed_test_duration = int(_get("CF 速度测试时间", "10"))
    config.test_url = _get("CF 测速URL", "https://speed.cloudflare.com/__down?bytes=100000000")
    config.random_pick_count = int(_get("CF 随机挑选数量", "100"))
    config.top_n = int(_get("CF 入选数量", "20"))
    config.concurrency = int(_get("CF 并发线程", "200"))

    return config
