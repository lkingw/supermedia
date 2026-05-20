import os
import re
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

# 磁力链接 BTIH ID 正则
MAGNET_BTIH_PATTERN = re.compile(r"xt=urn:btih:([A-Fa-f0-9]{40})", re.IGNORECASE)


def extract_btih_id(magnet):
    """从磁力链接中提取 BTIH ID（40位十六进制）。"""
    match = MAGNET_BTIH_PATTERN.search(magnet)
    if match:
        return match.group(1).upper()
    # 如果无法提取，使用磁力链接前40个字符的哈希
    return magnet[:40].replace(":", "").replace("/", "").replace("?", "").upper()[:40]


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


def build_aria2_cmd(magnet, trackers, task_dir):
    """构建 aria2c 命令行参数。
    
    Args:
        magnet: 磁力链接
        trackers: tracker 列表
        task_dir: 任务专属目录（用于保存日志和进度）
    """
    log_file = os.path.join(task_dir, "download.log")
    session_file = os.path.join(task_dir, "session.dat")
    control_file = os.path.join(task_dir, "aria2.control")
    
    cmd = [
        "aria2c",
        "--seed-time=0",
        f"--dir={SAVE_PATH}",
        "--split=16",
        "--max-connection-per-server=16",
        "--disable-ipv6=true",
        "--enable-dht=true",
        "--dht-file-path=/tmp/dht.dat",
        # 日志输出到文件
        f"--log={log_file}",
        "--log-level=notice",
        # 保存会话/进度
        f"--save-session={session_file}",
        "--save-session-interval=60",
        # 控制文件（用于暂停/恢复）
        f"--stop-with-process={os.getpid()}",
        # 自动保存进度
        "--force-save=true",
        # 下载完成前显示进度
        "--show-console-readout=true",
        # 控制台输出到文件（追加模式）
    ]
    
    # 如果存在之前的 session，尝试恢复
    if os.path.exists(session_file):
        cmd.append(f"--input-file={session_file}")
    
    for t in trackers:
        cmd.append(f"--bt-tracker={t}")
    
    cmd.append(magnet)
    
    return cmd, log_file


def download(magnet, trackers):
    """下载单个磁力链接，输出保存到任务专属目录。"""
    btih_id = extract_btih_id(magnet)
    
    # 创建任务专属目录
    task_dir = os.path.join(SAVE_PATH, btih_id)
    os.makedirs(task_dir, exist_ok=True)
    
    # 保存磁力链接信息
    info_file = os.path.join(task_dir, "magnet.txt")
    with open(info_file, "w", encoding="utf-8") as f:
        f.write(magnet + "\n")
    
    print(f"\n🚀 开始下载：{btih_id}")
    print(f"   📁 任务目录：{task_dir}")
    
    cmd, log_file = build_aria2_cmd(magnet, trackers, task_dir)
    
    try:
        # 打开日志文件用于写入 aria2c 输出
        with open(log_file, "a", encoding="utf-8") as log_f:
            log_f.write(f"\n{'='*60}\n")
            log_f.write(f"启动时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            log_f.write(f"磁力链接: {magnet}\n")
            log_f.write(f"BTIH ID: {btih_id}\n")
            log_f.write(f"{'='*60}\n\n")
            log_f.flush()
            
            # 运行 aria2c，stdout/stderr 都重定向到日志文件
            result = subprocess.run(
                cmd,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                cwd=task_dir
            )
            
            if result.returncode == 0:
                print(f"✅ 下载完成：{btih_id}")
                # 标记完成
                completed_file = os.path.join(task_dir, "completed")
                with open(completed_file, "w", encoding="utf-8") as f:
                    f.write(f"completed at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                save_completed(magnet)
            else:
                print(f"❌ 下载失败（退出码 {result.returncode}）：{btih_id}")
                # 标记失败
                failed_file = os.path.join(task_dir, "failed")
                with open(failed_file, "w", encoding="utf-8") as f:
                    f.write(f"failed at {time.strftime('%Y-%m-%d %H:%M:%S')} with code {result.returncode}\n")
                    
    except Exception as e:
        print(f"❌ 下载异常：{btih_id} - {e}")
        # 记录异常
        error_file = os.path.join(task_dir, "error.log")
        with open(error_file, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {e}\n")


def main():
    print("🏁 自动磁力下载守护进程已启动")
    print(f"   MAGNET_FILE    = {MAGNET_FILE}")
    print(f"   SAVE_PATH      = {SAVE_PATH}")
    print(f"   COMPLETED_FILE = {COMPLETED_FILE}")
    print(f"   TRACKERS_FILE  = {TRACKERS_FILE}")
    print(f"   MAX_PARALLEL   = {MAX_PARALLEL}")
    print(f"   CHECK_INTERVAL = {CHECK_INTERVAL}")
    print(f"   任务目录格式   = {SAVE_PATH}/<BTIH_ID>/")

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
