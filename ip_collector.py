import os
import socket

from config import Config
from utils import is_ip, is_cidr, expand_cidr, is_cf_ip, load_cf_ranges


def collect_ips(
    config: Config,
    http_txt: str = "http.txt",
    user_ip_txt: str = "userip.txt",
    inject_ips: list[str] | None = None,
) -> list[str]:
    """Collect candidate IPs from all sources and return a deduplicated list."""
    ips: set[str] = set()

    # Inject existing CF DNS IPs
    if inject_ips:
        for ip in inject_ips:
            ips.add(ip)

    # Parse http.txt (mixed domains / IPs / CIDRs)
    if os.path.exists(http_txt):
        print(f"\n[*] 正在读取 {http_txt} 并解析...")
        with open(http_txt, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()

        cidr_ips: set[str] = set()
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Remove URL prefix
            cleaned = line
            if cleaned.startswith("http://"):
                cleaned = cleaned[7:]
            if cleaned.startswith("https://"):
                cleaned = cleaned[8:]
            cleaned = cleaned.split("/")[0]

            if is_cidr(cleaned):
                expanded = expand_cidr(cleaned, config.random_pick_count)
                print(f"  [CIDR] {cleaned} → 随机挑选 {len(expanded)} 个 IP")
                for ip in expanded:
                    cidr_ips.add(ip)
            elif is_ip(cleaned):
                ips.add(cleaned)
            else:
                # Treat as domain name
                try:
                    resolved = socket.gethostbyname(cleaned)
                    ips.add(resolved)
                except socket.gaierror:
                    pass

        # Apply random pick limit across all CIDR IPs
        if len(cidr_ips) > config.random_pick_count:
            import random
            cidr_ips = set(random.sample(list(cidr_ips), config.random_pick_count))
            print(f"  [CIDR] 总计超过 {config.random_pick_count}，随机缩减")
        ips.update(cidr_ips)
    else:
        print(f"[警告] 找不到 {http_txt}")

    # Parse userip.txt
    if os.path.exists(user_ip_txt):
        print(f"[*] 正在追加自定义 IP 文件 {user_ip_txt}...")
        with open(user_ip_txt, "r", encoding="utf-8") as f:
            for line in f:
                u_ip = line.strip()
                if u_ip and is_ip(u_ip):
                    ips.add(u_ip)

    if not ips:
        print("[警告] 没有提取到任何有效 IP")
        return []

    # Filter: keep only Cloudflare IPs
    cf_ranges = load_cf_ranges()
    if cf_ranges:
        all_count = len(ips)
        ips = {ip for ip in ips if is_cf_ip(ip)}
        removed = all_count - len(ips)
        if removed:
            print(f"  [过滤] 排除非 CF IP: {removed} 个")

    result = list(ips)
    print(f"[*] 汇总完成，共 {len(result)} 个 IP 进入测速环节")
    return result
