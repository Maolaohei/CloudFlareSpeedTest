#!/usr/bin/env python3
"""CloudflareSpeedTest - Python 重写版本
支持 CLI 和 GUI 两种模式。
CLI: python main.py [-c env.txt] [--no-dns] [--update-only]
"""

import argparse
import sys
import os

# Ensure the script can find its modules when run from any directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import load_env, Config
from cf_api import get_dns_ips, update_dns
from ip_collector import collect_ips
from latency_tester import run_latency_tests_sync
from scorer import filter_by_latency, calculate_scores, select_best_ips
from speed_tester import run_speed_tests
from output import write_result_csv, print_results


def run_pipeline(config: Config, http_txt: str = "http.txt", update_dns_flag: bool = True):
    """Execute the full test pipeline."""
    print("=" * 60)
    print("  CloudflareSpeedTest - Python Edition")
    print("=" * 60)

    # Step 1: Config loaded already
    print(f"\n[配置] 域名: {config.domains}")
    print(f"[配置] 延迟差距: {config.latency_gap}ms, 平均延迟上限: {config.max_latency}ms")
    print(f"[配置] 入选数量: {config.top_n}")

    # Step 2: Get current CF DNS IPs
    cf_ips = get_dns_ips(config)
    if cf_ips:
        print(f"[*] 当前 CF DNS 共有 {len(cf_ips)} 个 IP")

    # Step 3: Collect candidate IPs
    ips = collect_ips(config, http_txt=http_txt, inject_ips=cf_ips)
    if not ips:
        print("[错误] 无可用 IP，退出")
        return

    # Step 4: Latency testing
    latency_results = run_latency_tests_sync(ips, config)

    # Step 5: Filter by latency
    candidates = filter_by_latency(latency_results, config)
    if not candidates:
        print("[错误] 没有 IP 通过延迟过滤，退出")
        return

    candidate_ips = [r.ip for r in candidates]
    print(f"[*] {len(candidate_ips)} 个 IP 进入速度测试")

    # Step 6: Speed testing
    speed_results = run_speed_tests(candidate_ips, config)

    # Step 7: Score and rank
    scored = calculate_scores(candidates, speed_results, config)
    best_ips = select_best_ips(scored, config.total_needed())

    # Step 8: Output and DNS update
    write_result_csv(scored)
    print_results(scored, top_n=min(config.top_n, len(scored)))

    if update_dns_flag and best_ips:
        print(f"\n[*] 准备更新 DNS，最佳 IP: {best_ips}")
        update_dns(config, best_ips)
        print("[*] DNS 同步完成")
    elif not update_dns_flag:
        print("\n[*] 跳过 DNS 更新 (--no-dns)")

    return scored, best_ips


def update_only(config: Config):
    """Read existing result.csv and update DNS with top IPs."""
    import csv
    if not os.path.exists("result.csv"):
        print("[错误] 找不到 result.csv，请先运行测速")
        return

    ips = []
    with open("result.csv", "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        ip_idx = 0
        if header:
            for i, col in enumerate(header):
                if "IP" in col.upper():
                    ip_idx = i
                    break
        for row in reader:
            if row and len(row) > ip_idx:
                ips.append(row[ip_idx])

    needed = config.total_needed()
    best = ips[:needed]
    print(f"[*] 从 result.csv 读取到 {len(ips)} 个 IP，取前 {len(best)} 个")
    update_dns(config, best)
    print("[*] DNS 同步完成")


def parse_args():
    p = argparse.ArgumentParser(description="CloudflareSpeedTest - Python Edition")
    p.add_argument("-c", "--config", default="env.txt", help="配置文件路径 (默认 env.txt)")
    p.add_argument("-f", "--file", default="http.txt", help="HTTP 域名/IP 列表文件 (默认 http.txt)")
    p.add_argument("--no-dns", action="store_true", help="仅测速，不更新 Cloudflare DNS")
    p.add_argument("--update-only", action="store_true", help="仅从 result.csv 更新 DNS")
    p.add_argument("--gui", action="store_true", help="启动 GUI 界面")
    return p.parse_args()


def main():
    args = parse_args()

    if args.gui:
        from gui_app import launch_gui
        launch_gui()
        return

    config = load_env(args.config)

    if args.update_only:
        update_only(config)
    else:
        run_pipeline(config, http_txt=args.file, update_dns_flag=not args.no_dns)


if __name__ == "__main__":
    main()
