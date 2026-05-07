# CloudflareSpeedTest

Cloudflare IP 优选测速工具，通过 TCP 延迟测试 + 下载速度测试筛选最快的 Cloudflare IP，并自动更新 Cloudflare DNS 记录。


虽然已经有了XIU2/CloudflareSpeedTest这么优秀的工具，但是感觉不太适合我，于是自己vibe了一个适合自己需求的。

## 功能

- **IP 收集** — 从域名解析、CIDR 段随机采样、自定义 IP 列表等多源收集候选 IP
- **TCP 延迟测试** — 高并发 TCPing，测试每个 IP 的平均延迟和丢包率
- **下载速度测试** — DNS 劫持 + EWMA 时间片测量，精确评估带宽
- **综合评分** — 速度 / 延迟 / 丢包率加权评分，自动选出最优 IP
- **自动更新 DNS** — 通过 Cloudflare API 将优选 IP 分发到指定的解析域名
- **GUI 界面** — 基于 CustomTkinter 的现代化图形界面
- **命令行支持** — 完整 CLI，可集成到定时任务或脚本

## 快速开始

### 方式一：直接运行 exe

1. 下载 `CFSpeedTest.exe`
2. 在同目录下准备好配置文件 `env.txt` 和 IP 列表 `http.txt`
3. 双击运行（启动 GUI），或在终端中运行：

```bash
CFSpeedTest.exe                  # 默认配置运行
CFSpeedTest.exe --gui            # 启动 GUI
CFSpeedTest.exe --no-dns         # 仅测速，不更新 DNS
CFSpeedTest.exe --update-only    # 从 result.csv 更新 DNS
```

### 方式二：Python 源码运行

```bash
pip install -r requirements.txt
python main.py                  # CLI 模式
python main.py --gui            # GUI 模式
```

## 命令行参数

| 参数 | 说明 |
|------|------|
| `-c, --config FILE` | 配置文件路径（默认 `env.txt`） |
| `-f, --file FILE` | HTTP 域名/IP 列表文件（默认 `http.txt`） |
| `--no-dns` | 仅测速，不更新 Cloudflare DNS |
| `--update-only` | 仅从 `result.csv` 读取结果并更新 DNS |
| `--gui` | 启动图形界面 |

## 配置文件

### env.txt — 主配置

```ini
CF API 令牌: <your-api-token>
CF Zone ID: <your-zone-id>
CF 解析域名: example.com:2, sub.example.com:1
CF 测速URL: https://cf.xiu2.xyz/url
CF 平均延迟: 9999
CF 延迟差距: 20
CF 速度权重: 50
CF 延迟权重: 30
CF 丢包权重: 20
CF 延迟测试次数: 30
CF 丢包测试频率: 100
CF 速度测试时间: 12
CF 并发线程: 200
CF 随机挑选数量: 100
CF 入选数量: 40
```

| 字段 | 说明 |
|------|------|
| `CF API 令牌` | Cloudflare API Token（需 DNS 编辑权限） |
| `CF Zone ID` | Cloudflare 区域 ID |
| `CF 解析域名` | 格式 `域名:IP数量`，多个用逗号分隔 |
| `CF 测速URL` | 用于速度测试的下载地址 |
| `CF 平均延迟` | 平均延迟上限（ms），超过则淘汰 |
| `CF 延迟差距` | 允许与最优延迟的差距（ms） |
| `CF 速度权重` | 速度评分权重 |
| `CF 延迟权重` | 延迟评分权重 |
| `CF 丢包权重` | 丢包率评分权重 |
| `CF 延迟测试次数` | 每个 IP 的 TCPing 次数 |
| `CF 丢包测试频率` | Ping 间隔（ms） |
| `CF 速度测试时间` | 每个 IP 下载测试时长（秒） |
| `CF 并发线程` | 延迟测试并发数 |
| `CF 随机挑选数量` | 从每个 CIDR 段随机选取的 IP 数 |
| `CF 入选数量` | 进入速度测试的 IP 数量 |

### http.txt — 候选源

每行一个，支持三种格式：

```
# 域名（自动解析为 IP）
cloudflare.com

# 单个 IP
1.1.1.1

# CIDR 段（随机采样 N 个 IP）
104.16.0.0/13
```

### cf_ip_ranges.txt — Cloudflare IP 范围

用于过滤非 Cloudflare IP，内置了 CF 官方 IP 段。

### userip.txt — 自定义 IP

每行一个 IP，会追加到候选列表。

## 工作流程

```
配置加载 → 获取当前 DNS IP → 收集候选 IP → TCP 延迟测试
→ 延迟过滤 → 速度测试 → 综合评分 → 输出 CSV → 更新 DNS
```

## 输出

测速完成后生成 `result.csv`：

| IP | Speed(MB/s) | Loss(%) | Latency(ms) | Score | RecordTime |
|----|-------------|---------|-------------|-------|------------|
| 104.16.x.x | 45.20 | 0.0 | 12.5 | 85.32 | 2026-05-07 14:30:00 |

## 依赖

- Python 3.10+
- customtkinter >= 5.2
- aiohttp >= 3.9

## 构建 exe

```bash
pip install pyinstaller customtkinter aiohttp
pyinstaller --onefile --console --name "CFSpeedTest" --hidden-import customtkinter --hidden-import aiohttp main.py
```

生成的 exe 在 `dist/` 目录下。将 `env.txt`、`http.txt` 等文件放在 exe 同目录即可运行。

## 感谢项目

https://github.com/XIU2/CloudflareSpeedTest
