"""CloudflareSpeedTest GUI — Modern CustomTkinter design"""

import sys
import os
import threading
import queue
import csv
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import customtkinter as ctk
except ImportError:
    print("pip install customtkinter")
    sys.exit(1)

from config import load_env, Config
from cf_api import get_dns_ips, update_dns
from ip_collector import collect_ips
from latency_tester import run_latency_tests_sync
from scorer import filter_by_latency, calculate_scores, select_best_ips
from speed_tester import run_speed_tests
from output import write_result_csv


class LogRedirect:
    def __init__(self, callback):
        self.callback = callback

    def write(self, s):
        if s.strip():
            self.callback(s.strip())

    def flush(self):
        pass


class CFSTApp:
    # ── Init ─────────────────────────────────────────────────
    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.root = ctk.CTk()
        self.root.title("CloudflareSpeedTest")
        self.root.geometry("1060x680")
        self.root.minsize(900, 560)

        self.running = False
        self.config: Config | None = None

        self._build_ui()
        self._load_config()
        self._poll_log()

    # ── Layout ───────────────────────────────────────────────
    def _build_ui(self):
        # Grid: sidebar | main
        self.root.grid_columnconfigure(0, weight=0)  # sidebar fixed
        self.root.grid_columnconfigure(1, weight=1)  # main expands
        self.root.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main()
        self._build_status_bar()

    # ── Sidebar ──────────────────────────────────────────────
    def _build_sidebar(self):
        sidebar = ctk.CTkFrame(self.root, width=200, corner_radius=0, fg_color=("#EBEBEB", "#1A1A1A"))
        sidebar.grid(row=0, column=0, sticky="nsw", rowspan=2)
        sidebar.grid_propagate(False)

        # Logo area
        ctk.CTkLabel(
            sidebar, text="CF SpeedTest",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(25, 5))

        ctk.CTkLabel(
            sidebar, text="Cloudflare IP 优选",
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray60"),
        ).pack(pady=(0, 20))

        sep = ctk.CTkFrame(sidebar, height=1, fg_color=("gray75", "gray25"))
        sep.pack(fill="x", padx=15, pady=(0, 15))

        # Nav buttons
        self.nav_btns: dict[str, ctk.CTkButton] = {}
        nav_items = [
            ("config", "  ⚙  配置", self._show_config),
            ("log",    "  📋  运行", self._show_log),
            ("result", "  📊  结果", self._show_result),
        ]
        for key, label, cmd in nav_items:
            btn = ctk.CTkButton(
                sidebar, text=label, anchor="w", width=170,
                fg_color="transparent",
                text_color=("gray30", "gray80"),
                hover_color=("gray80", "gray25"),
                font=ctk.CTkFont(size=13),
                corner_radius=8,
                command=cmd,
            )
            btn.pack(pady=3, padx=10)
            self.nav_btns[key] = btn

        # Highlight default
        self._set_nav_active("config")

        # Bottom spacer + version
        ctk.CTkLabel(
            sidebar, text="", height=100
        ).pack(side="bottom", pady=5)
        ctk.CTkLabel(
            sidebar, text="v1.0  |  Python Edition",
            font=ctk.CTkFont(size=10),
            text_color=("gray50", "gray50"),
        ).pack(side="bottom", pady=10)

    def _set_nav_active(self, key: str):
        for k, btn in self.nav_btns.items():
            if k == key:
                btn.configure(fg_color=("gray80", "gray25"), text_color=("gray10", "gray95"))
            else:
                btn.configure(fg_color="transparent", text_color=("gray30", "gray80"))

    # ── Main content area ────────────────────────────────────
    def _build_main(self):
        self.main_container = ctk.CTkFrame(self.root, fg_color="transparent")
        self.main_container.grid(row=0, column=1, sticky="nsew", padx=(0, 0))
        self.main_container.grid_columnconfigure(0, weight=1)
        self.main_container.grid_rowconfigure(0, weight=1)

        # Build each page
        self.page_config = self._make_config_page(self.main_container)
        self.page_log = self._make_log_page(self.main_container)
        self.page_result = self._make_result_page(self.main_container)

    # ── Status bar ───────────────────────────────────────────
    def _build_status_bar(self):
        bar = ctk.CTkFrame(self.root, height=32, corner_radius=0, fg_color=("#E0E0E0", "#111111"))
        bar.grid(row=1, column=1, sticky="sew")
        bar.grid_propagate(False)

        self.status_text = ctk.CTkLabel(
            bar, text="●  就绪",
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray60"),
        )
        self.status_text.pack(side="left", padx=15)

        self.progress_bar = ctk.CTkProgressBar(bar, width=200, height=8, corner_radius=4)
        self.progress_bar.pack(side="right", padx=15)
        self.progress_bar.set(0)

    # ═══════════════════════════════════════════════════════════
    #  CONFIG PAGE
    # ═══════════════════════════════════════════════════════════
    def _make_config_page(self, parent):
        page = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)

        self.fields: dict[str, ctk.CTkEntry] = {}

        # Header
        hdr = ctk.CTkFrame(page, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", pady=(5, 15), padx=5)
        ctk.CTkLabel(hdr, text="测速配置", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkButton(
            hdr, text="保存并运行", width=110, height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._start_test,
        ).pack(side="right", padx=3)
        ctk.CTkButton(
            hdr, text="保存配置", width=80, height=34,
            fg_color="transparent", border_width=1,
            font=ctk.CTkFont(size=12),
            command=self._save_config,
        ).pack(side="right", padx=3)

        row = 1
        row = self._card(page, row, "Cloudflare API", [
            ("API 令牌", "CF API 令牌", ""),
            ("Zone ID", "CF Zone ID", ""),
            ("解析域名", "CF 解析域名", "domain:count,domain:count"),
            ("测速 URL", "CF 测速URL", "https://cf.xiu2.xyz/url"),
        ], columns=2)

        row = self._card(page, row, "筛选阈值", [
            ("平均延迟上限 (ms)", "CF 平均延迟", "9999"),
            ("延迟差距 (ms)", "CF 延迟差距", "20"),
        ], columns=2)

        row = self._card(page, row, "评分权重", [
            ("速度权重", "CF 速度权重", "50"),
            ("延迟权重", "CF 延迟权重", "30"),
            ("丢包权重", "CF 丢包权重", "20"),
        ])

        row = self._card(page, row, "测试参数", [
            ("延迟测试次数", "CF 延迟测试次数", "20"),
            ("Ping 间隔 (ms)", "CF 丢包测试频率", "100"),
            ("速度测试时间 (s)", "CF 速度测试时间", "10"),
            ("并发线程", "CF 并发线程", "200"),
        ], columns=2)

        row = self._card(page, row, "数量控制", [
            ("CIDR 随机挑选", "CF 随机挑选数量", "100"),
            ("速度测试入选", "CF 入选数量", "20"),
        ], columns=2)

        return page

    def _card(self, parent, row: int, title: str, entries: list[tuple[str, str, str]], columns: int = 3) -> int:
        """Create a card-style section with labeled entries in a compact grid."""
        card = ctk.CTkFrame(parent, corner_radius=12, border_width=1,
                            border_color=("gray85", "gray20"))
        card.grid(row=row, column=0, sticky="ew", padx=5, pady=(0, 12))
        for c in range(columns):
            card.grid_columnconfigure(c, weight=1)

        # Card header
        ctk.CTkLabel(
            card, text=title,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=("gray40", "gray70"),
        ).grid(row=0, column=0, columnspan=columns, sticky="w", padx=15, pady=(10, 8))

        for i, (label, key, placeholder) in enumerate(entries):
            col = i % columns
            r = (i // columns) * 2 + 1
            ctk.CTkLabel(
                card, text=label,
                font=ctk.CTkFont(size=12),
                text_color=("gray40", "gray70"),
                anchor="w",
            ).grid(row=r, column=col, sticky="w", padx=(20, 10), pady=(3, 0))

            entry = ctk.CTkEntry(
                card, height=30, corner_radius=6,
                font=ctk.CTkFont(size=12),
                placeholder_text=placeholder,
            )
            entry.grid(row=r + 1, column=col, sticky="ew", padx=(20, 15), pady=(2, 6))
            self.fields[key] = entry

        return row + 1

    # ═══════════════════════════════════════════════════════════
    #  LOG PAGE
    # ═══════════════════════════════════════════════════════════
    def _make_log_page(self, parent):
        page = ctk.CTkFrame(parent, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=0)
        page.grid_rowconfigure(1, weight=1)

        # Header
        hdr = ctk.CTkFrame(page, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", pady=(5, 10))
        ctk.CTkLabel(hdr, text="运行日志", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkButton(
            hdr, text="清空", width=60, height=28,
            fg_color="transparent", border_width=1,
            font=ctk.CTkFont(size=11),
            command=self._clear_log,
        ).pack(side="right")

        # Log area
        log_frame = ctk.CTkFrame(page, corner_radius=10, border_width=1,
                                 border_color=("gray85", "gray20"))
        log_frame.grid(row=1, column=0, sticky="nsew")
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(0, weight=1)

        self.log_text = ctk.CTkTextbox(
            log_frame,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="transparent",
            border_width=0,
        )
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        return page

    # ═══════════════════════════════════════════════════════════
    #  RESULT PAGE
    # ═══════════════════════════════════════════════════════════
    def _make_result_page(self, parent):
        page = ctk.CTkFrame(parent, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=0)
        page.grid_rowconfigure(1, weight=1)

        # Header + stats
        hdr = ctk.CTkFrame(page, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", pady=(5, 10))
        ctk.CTkLabel(hdr, text="测速结果", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkButton(
            hdr, text="仅更新 DNS", width=90, height=28,
            font=ctk.CTkFont(size=11),
            command=self._update_dns_only,
        ).pack(side="right", padx=3)

        # Result table area
        res_frame = ctk.CTkFrame(page, corner_radius=10, border_width=1,
                                 border_color=("gray85", "gray20"))
        res_frame.grid(row=1, column=0, sticky="nsew")
        res_frame.grid_columnconfigure(0, weight=1)
        res_frame.grid_rowconfigure(0, weight=1)

        self.result_text = ctk.CTkTextbox(
            res_frame,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="transparent",
            border_width=0,
        )
        self.result_text.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        return page

    # ── Navigation ───────────────────────────────────────────
    def _show_config(self):
        self._set_nav_active("config")
        self.page_config.grid(row=0, column=0, sticky="nsew", padx=25, pady=15)
        self.page_log.grid_forget()
        self.page_result.grid_forget()

    def _show_log(self):
        self._set_nav_active("log")
        self.page_config.grid_forget()
        self.page_log.grid(row=0, column=0, sticky="nsew", padx=25, pady=15)
        self.page_result.grid_forget()

    def _show_result(self):
        self._set_nav_active("result")
        self.page_config.grid_forget()
        self.page_log.grid_forget()
        self.page_result.grid(row=0, column=0, sticky="nsew", padx=25, pady=15)

    # ── Config I/O ───────────────────────────────────────────
    def _load_config(self):
        config = load_env("env.txt")
        defaults = {
            "CF API 令牌": config.api_token,
            "CF Zone ID": config.zone_id,
            "CF 解析域名": ", ".join(f"{d}:{config.domain_counts.get(d, 1)}" for d in config.domains),
            "CF 测速URL": config.test_url,
            "CF 平均延迟": str(config.max_latency),
            "CF 延迟差距": str(config.latency_gap),

            "CF 速度权重": str(int(config.speed_weight)),
            "CF 延迟权重": str(int(config.latency_weight)),
            "CF 丢包权重": str(int(config.loss_weight)),
            "CF 延迟测试次数": str(config.latency_test_count),
            "CF 丢包测试频率": str(config.ping_interval_ms),
            "CF 速度测试时间": str(config.speed_test_duration),
            "CF 并发线程": str(config.concurrency),
            "CF 随机挑选数量": str(config.random_pick_count),
            "CF 入选数量": str(config.top_n),
        }
        for key, entry in self.fields.items():
            if key in defaults:
                entry.delete(0, "end")
                entry.insert(0, defaults[key])

    def _save_config(self):
        lines = [f"{key}: {entry.get().strip()}" for key, entry in self.fields.items()]
        with open("env.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        self._log_msg("✔  配置已保存")

    # ── Log helpers ──────────────────────────────────────────
    def _log_msg(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{ts}] {msg}\n")
        self.log_text.see("end")

    def _clear_log(self):
        self.log_text.delete("1.0", "end")

    def _poll_log(self):
        """Process queued log messages from worker threads."""
        try:
            while True:
                msg = self._msg_queue.get_nowait()
                self._log_msg(msg)
        except (queue.Empty, AttributeError):
            pass
        self.root.after(200, self._poll_log)

    # ── Status bar helpers ───────────────────────────────────
    def _status(self, msg: str, color: str | None = None):
        self.status_text.configure(text=f"●  {msg}")
        if color:
            self.status_text.configure(text_color=color)

    def _progress(self, val: float):
        self.progress_bar.set(val)

    # ── Actions ──────────────────────────────────────────────
    def _start_test(self):
        if self.running:
            return
        self.running = True
        self._save_config()
        self._clear_log()
        self.result_text.delete("1.0", "end")
        self._show_log()
        self._progress(0)
        self._status("启动中...")

        self._msg_queue = queue.Queue()
        self._log_msg("=" * 45)
        self._log_msg("  CloudflareSpeedTest — 开始测速")
        self._log_msg("=" * 45)

        threading.Thread(target=self._run_test, daemon=True).start()

    def _update_dns_only(self):
        threading.Thread(target=self._run_dns_update, daemon=True).start()

    def _run_dns_update(self):
        self._msg_queue.put("[*] 从 result.csv 更新 DNS...")
        if not os.path.exists("result.csv"):
            self._msg_queue.put("[错误] 找不到 result.csv")
            return
        try:
            with open("result.csv", "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                header = next(reader, None)
                ip_idx = 0
                if header:
                    for i, col in enumerate(header):
                        if "IP" in col.upper():
                            ip_idx = i
                            break
                ips = [row[ip_idx] for row in reader if row and len(row) > ip_idx]
            config = load_env("env.txt")
            best = ips[:config.total_needed()]
            update_dns(config, best)
            self._msg_queue.put(f"✔  DNS 已更新: {', '.join(best)}")
        except Exception as e:
            self._msg_queue.put(f"[错误] {e}")

    def _run_test(self):
        old_stdout = sys.stdout
        sys.stdout = LogRedirect(lambda s: self._msg_queue.put(s))

        try:
            config = load_env("env.txt")

            # Stage 1: DNS
            self.root.after(0, lambda: self._status("获取 DNS 记录..."))
            self.root.after(0, lambda: self._progress(0.03))
            cf_ips = get_dns_ips(config)

            # Stage 2: Collect
            self.root.after(0, lambda: self._status("收集候选 IP..."))
            self.root.after(0, lambda: self._progress(0.08))
            if not self.running:
                return
            ips = collect_ips(config, inject_ips=cf_ips)
            if not ips:
                self.root.after(0, lambda: self._status("失败：无可用 IP", "red"))
                return
            self.root.after(0, lambda: self._progress(0.12))

            # Stage 3: Latency
            self.root.after(0, lambda: self._status(f"TCP 延迟测试 ({len(ips)} IP)"))

            def _lp(done, total):
                pct = 0.12 + 0.33 * done / max(total, 1)
                self.root.after(0, lambda: self._progress(pct))

            latency_results = run_latency_tests_sync(ips, config)
            if not self.running:
                return

            # Stage 4: Filter
            self.root.after(0, lambda: self._status("延迟过滤..."))
            self.root.after(0, lambda: self._progress(0.47))
            candidates = filter_by_latency(latency_results, config)
            if not candidates:
                self.root.after(0, lambda: self._status("失败：无 IP 通过过滤", "red"))
                return

            # Stage 5: Speed
            self.root.after(0, lambda: self._status(f"速度测试 ({len(candidates)} IP)"))
            self.root.after(0, lambda: self._progress(0.50))
            if not self.running:
                return

            def _sp(done, total):
                pct = 0.50 + 0.33 * done / max(total, 1)
                self.root.after(0, lambda: self._progress(pct))

            candidate_ips = [r.ip for r in candidates]
            speed_results = run_speed_tests(candidate_ips, config, progress_callback=_sp)
            if not self.running:
                return
            self.root.after(0, lambda: self._progress(0.85))

            # Stage 6: Score
            self.root.after(0, lambda: self._status("评分排序..."))
            scored = calculate_scores(candidates, speed_results, config)
            best_ips = select_best_ips(scored, config.total_needed())

            # Output
            write_result_csv(scored)
            self.root.after(0, lambda: self._show_results(scored))
            self.root.after(0, lambda: self._progress(0.93))

            # DNS
            if best_ips:
                self.root.after(0, lambda: self._status("更新 DNS..."))
                update_dns(config, best_ips)
                self._msg_queue.put(f"✔  DNS 已更新: {', '.join(best_ips)}")

            self.root.after(0, lambda: self._progress(1.0))
            self.root.after(0, lambda: self._status("✓  完成"))

        except Exception as e:
            import traceback
            self._msg_queue.put(f"[异常] {e}")
            self._msg_queue.put(traceback.format_exc())
            self.root.after(0, lambda: self._status("异常", "red"))
        finally:
            sys.stdout = old_stdout
            self.running = False

    def _show_results(self, scored):
        self.result_text.delete("1.0", "end")
        hdr = f"  {'#':<3}  {'IP':<18} {'速度':>7} {'延迟':>7} {'丢包':>6}  {'得分':>7}\n"
        sep = f"  {'—'*60}\n"
        self.result_text.insert("end", hdr + sep)
        for i, r in enumerate(scored[:40]):
            tag = ""
            if r.score < 0:
                tag = "  ✗"
            self.result_text.insert(
                "end",
                f"  [{i+1:02d}] {r.ip:<16} {r.speed:>5.1f}MB/s {r.latency:>5.1f}ms "
                f"{r.loss*100:>4.1f}% {r.score:>7.1f}{tag}\n",
            )
        self._show_result()

    def run(self):
        self._show_config()
        self.root.mainloop()


def launch_gui():
    app = CFSTApp()
    app.run()


if __name__ == "__main__":
    launch_gui()
