import json
import urllib.request
import urllib.error
from config import Config


def _headers(config: Config) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {config.api_token}",
        "Content-Type": "application/json",
    }


def get_dns_ips(config: Config) -> list[str]:
    """Fetch current A-record IPs from Cloudflare for all configured domains."""
    if not config.api_token or not config.zone_id or not config.domains:
        return []

    ips: set[str] = set()
    print("\n[*] 正在从 Cloudflare 获取当前 DNS 解析 IP...")

    for domain in config.domains:
        url = (
            f"https://api.cloudflare.com/client/v4/zones/{config.zone_id}"
            f"/dns_records?name={domain}&type=A&per_page=100"
        )
        req = urllib.request.Request(url, headers=_headers(config))
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                if data.get("success"):
                    records = data["result"]
                    for rec in records:
                        ips.add(rec["content"])
                    print(f"  [成功] {domain} 当前绑定 {len(records)} 个 IP")
                else:
                    print(f"  [错误] {domain} 获取失败: {data.get('errors')}")
        except Exception as e:
            print(f"  [错误] {domain} 请求异常: {e}")

    return list(ips)


def _get_existing_records(config: Config, domain: str) -> list[dict]:
    url = (
        f"https://api.cloudflare.com/client/v4/zones/{config.zone_id}"
        f"/dns_records?name={domain}&type=A"
    )
    req = urllib.request.Request(url, headers=_headers(config))
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
        if data.get("success"):
            return data["result"]
        return []


def _update_record(config: Config, record_id: str, domain: str, ip: str):
    url = (
        f"https://api.cloudflare.com/client/v4/zones/{config.zone_id}"
        f"/dns_records/{record_id}"
    )
    body = json.dumps({"content": ip, "name": domain, "type": "A", "ttl": 60}).encode()
    req = urllib.request.Request(url, data=body, headers=_headers(config), method="PUT")
    with urllib.request.urlopen(req, timeout=15):
        pass


def _create_record(config: Config, domain: str, ip: str):
    url = f"https://api.cloudflare.com/client/v4/zones/{config.zone_id}/dns_records"
    body = json.dumps({"content": ip, "name": domain, "type": "A", "ttl": 60}).encode()
    req = urllib.request.Request(url, data=body, headers=_headers(config), method="POST")
    with urllib.request.urlopen(req, timeout=15):
        pass


def _delete_record(config: Config, record_id: str):
    url = (
        f"https://api.cloudflare.com/client/v4/zones/{config.zone_id}"
        f"/dns_records/{record_id}"
    )
    req = urllib.request.Request(url, headers=_headers(config), method="DELETE")
    with urllib.request.urlopen(req, timeout=15):
        pass


def update_dns(config: Config, best_ips: list[str]) -> bool:
    """Distribute best IPs across configured domains and update Cloudflare DNS."""
    if not best_ips or not config.domains or not config.api_token or not config.zone_id:
        return False

    domains = config.domains
    total_ips = len(best_ips)
    num_domains = len(domains)

    # Build allocation
    allocation: list[list[str]] = []
    print("\n[*] DNS 分配策略:")

    if total_ips == 1:
        allocation = [[best_ips[0]] for _ in range(num_domains)]
        print(f"  仅 1 个 IP，所有 {num_domains} 个域名共享")
    else:
        base = total_ips // num_domains
        remainder = total_ips % num_domains
        idx = 0
        for i in range(num_domains):
            count = base + (1 if i < remainder else 0)
            if count > 0:
                allocated = best_ips[idx:idx + count]
                allocation.append(allocated)
                idx += count
            else:
                allocation.append([best_ips[i % total_ips]])
        for i, d in enumerate(domains):
            print(f"  [{d}] 分配 {len(allocation[i])} 个 IP: {', '.join(allocation[i])}")

    # Apply
    for i, domain in enumerate(domains):
        domain_ips = allocation[i]
        try:
            existing = _get_existing_records(config, domain)
        except Exception as e:
            print(f"  [DNS 失败] {domain} 获取现有记录: {e}")
            continue

        max_len = max(len(domain_ips), len(existing))
        for j in range(max_len):
            try:
                if j < len(domain_ips) and j < len(existing):
                    if existing[j]["content"] != domain_ips[j]:
                        _update_record(config, existing[j]["id"], domain, domain_ips[j])
                        print(f"  [更新] {domain}: {existing[j]['content']} -> {domain_ips[j]}")
                elif j < len(domain_ips):
                    _create_record(config, domain, domain_ips[j])
                    print(f"  [新增] {domain}: {domain_ips[j]}")
                elif j < len(existing):
                    _delete_record(config, existing[j]["id"])
                    print(f"  [删除] {domain}: {existing[j]['content']}")
            except Exception as e:
                print(f"  [DNS 失败] {domain}: {e}")

    return True
