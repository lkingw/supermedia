import os
import time
import subprocess
from concurrent.futures import ThreadPoolExecutor

# ==================== 核心配置（支持环境变量覆盖） ====================
MAGNET_FILE = os.environ.get("MAGNET_FILE", "/app/data/magnet.txt")
SAVE_PATH = os.environ.get("SAVE_PATH", "/media")
MAX_PARALLEL = int(os.environ.get("MAX_PARALLEL", "5"))
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "10"))
COMPLETED_FILE = os.environ.get("COMPLETED_FILE", "/app/data/completed.txt")
TRACKERS_FILE = os.environ.get("TRACKERS_FILE", "/app/data/trackers.txt")
TRACKERS_URL = os.environ.get(
    "TRACKERS_URL",
    "https://raw.githubusercontent.com/adysec/tracker/main/trackers_best.txt"
)
# ===================================================================

# 硬编码兜底 trackers（网络不可用时使用）
FALLBACK_TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.stealth.si:80/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://explodie.org:6969/announce",
    "udp://tracker.moeking.me:6969/announce",
    "udp://tr.bangumi.moe:6969/announce",
    "udp://share.camoe.cn:8080/announce",
    "udp://tracker.bittorrent.am:6969/announce",
]


def load_completed():
    if not os.path.exists(COMPLETED_FILE):
        return set()
    with open(COMPLETED_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def save_completed(magnet):
    with open(COMPLETED_FILE, "a", encoding="utf-8") as f:
        f.write(magnet + "\n")


def load_magnets():
    if not os.path.exists(MAGNET_FILE):
        return []
    with open(MAGNET_FILE, "r", encoding="utf-8") as f:
        return [
            line.strip()
            for line in f
            if line.strip().startswith("magnet:")
        ]


def load_trackers():
    """从本地文件加载 trackers，网络/文件不可用时返回硬编码兜底列表。"""
    if not os.path.exists(TRACKERS_FILE):
        print(f"⚠️  Trackers 文件不存在，使用兜底列表（共 {len(FALLBACK_TRACKERS)} 条）")
        return FALLBACK_TRACKERS

    with open(TRACKERS_FILE, "r", encoding="utf-8") as f:
        trackers = [
            line.strip()
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]

    if not trackers:
        print(f"⚠️  Trackers 文件为空，使用兜底列表（共 {len(FALLBACK_TRACKERS)} 条）")
        return FALLBACK_TRACKERS

    print(f"✅ 成功加载 {len(trackers)} 条 trackers")
    return trackers


def build_aria2_cmd(magnet, trackers):
    """构建 aria2c 命令行参数。"""
    cmd = [
        "aria2c",
        "--seed-time=0",
        f"--dir={SAVE_PATH}",
        "--split=16",
        "--max-connection-per-server=16",
        "--disable-ipv6=true",
        "--enable-dht=true",
        "--dht-file-path=/tmp/dht.dat",
    ]
    for t in trackers:
        cmd.append(f"--bt-tracker={t}")
    cmd.append(magnet)
    return cmd


def download(magnet, trackers):
    print(f"\n🚀 开始下载：{magnet[:60]}...")
    cmd = build_aria2_cmd(magnet, trackers)

    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        print(f"✅ 下载完成：{magnet[:60]}")
        save_completed(magnet)
    except Exception:
        print(f"❌ 下载失败：{magnet[:60]}")


def main():
    print("🏁 自动磁力下载守护进程已启动")
    print(f"   MAGNET_FILE    = {MAGNET_FILE}")
    print(f"   SAVE_PATH      = {SAVE_PATH}")
    print(f"   COMPLETED_FILE = {COMPLETED_FILE}")
    print(f"   TRACKERS_FILE  = {TRACKERS_FILE}")
    print(f"   MAX_PARALLEL   = {MAX_PARALLEL}")
    print(f"   CHECK_INTERVAL = {CHECK_INTERVAL}")

    while True:
        trackers = load_trackers()
        completed = load_completed()
        magnets = load_magnets()
        new_tasks = [m for m in magnets if m not in completed]

        if new_tasks:
            print(f"\n发现 {len(new_tasks)} 个新任务，trackers={len(trackers)} 条")
            with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as executor:
                for magnet in new_tasks:
                    executor.submit(download, magnet, trackers)
        else:
            print(".", end="", flush=True)

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
