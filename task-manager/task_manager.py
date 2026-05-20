"""
任务管理器：监控 magnet.txt，通过 aria2 RPC 自动添加下载任务，
下载完成后同步文件到 media 目录。
"""
import os
import re
import json
import time
import shutil
import requests
from pathlib import Path

# ==================== 配置（支持环境变量覆盖） ====================
ARIA2_RPC_URL = os.environ.get("ARIA2_RPC_URL", "http://localhost:6800/jsonrpc")
ARIA2_SECRET = os.environ.get("ARIA2_SECRET", "")
MAGNET_FILE = os.environ.get("MAGNET_FILE", "/app/data/magnet.txt")
COMPLETED_FILE = os.environ.get("COMPLETED_FILE", "/app/data/completed.txt")
ARIA2_DOWNLOAD_DIR = os.environ.get("ARIA2_DOWNLOAD_DIR", "/downloads")
MEDIA_DIR = os.environ.get("MEDIA_DIR", "/media")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "10"))
TRACKERS_FILE = os.environ.get("TRACKERS_FILE", "/app/data/trackers.txt")
TRACKERS_URL = os.environ.get(
    "TRACKERS_URL",
    "https://raw.githubusercontent.com/adysec/tracker/main/trackers_best_udp.txt"
)
# ===================================================================

MAGNET_BTIH_PATTERN = re.compile(r"xt=urn:btih:([A-Fa-f0-9]{40})", re.IGNORECASE)


def rpc_call(method, params=None):
    """调用 aria2 JSON-RPC 接口。"""
    payload = {
        "jsonrpc": "2.0",
        "id": "supermedia",
        "method": method,
        "params": ["token:" + ARIA2_SECRET] if ARIA2_SECRET else [],
    }
    if params:
        payload["params"].extend(params)

    try:
        resp = requests.post(ARIA2_RPC_URL, json=payload, timeout=10)
        result = resp.json()
        if "error" in result:
            print(f"❌ RPC 错误: {result['error']}")
            return None
        return result.get("result")
    except Exception as e:
        print(f"❌ RPC 请求失败: {e}")
        return None


def extract_btih_id(magnet):
    """从磁力链接中提取 BTIH ID。"""
    match = MAGNET_BTIH_PATTERN.search(magnet)
    if match:
        return match.group(1).upper()
    return magnet[:40].replace(":", "").replace("/", "").replace("?", "").upper()[:40]


def load_completed():
    """加载已完成记录。"""
    if not os.path.exists(COMPLETED_FILE):
        return set()
    with open(COMPLETED_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def save_completed(magnet):
    """追加已完成记录。"""
    with open(COMPLETED_FILE, "a", encoding="utf-8") as f:
        f.write(magnet + "\n")


def load_magnets():
    """从 magnet.txt 加载磁力链接。"""
    if not os.path.exists(MAGNET_FILE):
        return []
    with open(MAGNET_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip().startswith("magnet:")]


def load_trackers():
    """加载 trackers 列表。"""
    if not os.path.exists(TRACKERS_FILE):
        return []
    with open(TRACKERS_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]


def get_active_gids():
    """获取当前活跃的下载任务 GID 列表。"""
    result = rpc_call("aria2.tellActive", [["gid"]])
    if not result:
        return set()
    return {item["gid"] for item in result}


def get_all_tasks():
    """获取所有任务（等待中 + 活跃 + 已完成）。"""
    all_tasks = {}
    
    # tellWaiting/tellActive: 只需要 keys 参数
    for method in ["aria2.tellWaiting", "aria2.tellActive"]:
        result = rpc_call(method, [["gid", "status", "bittorrent"]])
        if result:
            for item in result:
                gid = item.get("gid")
                if gid:
                    all_tasks[gid] = item
    
    # tellStopped: 需要 offset, num, keys
    offset = 0
    while True:
        result = rpc_call("aria2.tellStopped", [offset, 200, ["gid", "status", "bittorrent"]])
        if not result:
            break
        for item in result:
            gid = item.get("gid")
            if gid:
                all_tasks[gid] = item
        if len(result) < 200:
            break
        offset += 200
    
    return all_tasks


def add_magnet(magnet, trackers):
    """通过 RPC 添加磁力链接下载任务。"""
    btih_id = extract_btih_id(magnet)

    # 检查是否已在 aria2 中
    all_tasks = get_all_tasks()
    for task in all_tasks.values():
        # 从 bittorrent info 或 files 中匹配
        bt_info = task.get("bittorrent", {}).get("info", {})
        if bt_info and bt_info.lower() == btih_id.lower():
            print(f"⏭️  已存在: {btih_id}")
            return True

    # 构建选项
    options = {
        "dir": ARIA2_DOWNLOAD_DIR,
        "seed-time": "0",
        "bt-tracker": trackers if trackers else None,
    }
    # 过滤 None 值
    options = {k: v for k, v in options.items() if v is not None}

    result = rpc_call("aria2.addUri", [[magnet], options])
    if result:
        print(f"✅ 已添加: {btih_id}")
        return True
    else:
        print(f"❌ 添加失败: {btih_id}")
        return False


def sync_completed_to_media():
    """检查已完成任务，将下载文件同步到 media 目录。"""
    result = rpc_call("aria2.tellStopped", [0, 200, ["gid", "status", "files", "bittorrent", "dir"]])
    if not result:
        return

    completed = load_completed()

    for task in result:
        if task.get("status") != "complete":
            continue

        files = task.get("files", [])
        if not files:
            continue

        # 用第一个文件的路径来识别任务
        first_file = files[0]
        file_path = first_file.get("path", "")
        if not file_path or not os.path.exists(file_path):
            continue

        # 获取磁力链接信息
        bt_info = task.get("bittorrent", {}).get("info", "")
        magnet_uri = ""
        if bt_info:
            magnet_uri = f"magnet:?xt=urn:btih:{bt_info}"

        # 检查是否已同步
        if magnet_uri and magnet_uri in completed:
            continue

        # 源目录：文件所在目录
        src_dir = os.path.dirname(file_path)
        if not os.path.isdir(src_dir):
            # 单文件下载，文件直接在 /data 下
            src_dir = ARIA2_DOWNLOAD_DIR

        # 目标目录：以 BTIH ID 命名
        btih_id = bt_info.upper() if bt_info else os.path.basename(src_dir)
        dest_dir = os.path.join(MEDIA_DIR, btih_id)
        os.makedirs(dest_dir, exist_ok=True)

        # 同步文件
        try:
            # 列出源目录下所有文件
            items = os.listdir(src_dir) if os.path.isdir(src_dir) else [os.path.basename(file_path)]

            synced = False
            for item in items:
                src_path = os.path.join(src_dir, item)
                dest_path = os.path.join(dest_dir, item)

                if os.path.isfile(src_path) and not os.path.exists(dest_path):
                    shutil.copy2(src_path, dest_path)
                    synced = True
                elif os.path.isdir(src_path) and not os.path.exists(dest_path):
                    shutil.copytree(src_path, dest_path)
                    synced = True

            if synced:
                print(f"📁 已同步到 media: {btih_id}")

            # 保存磁力链接信息
            if magnet_uri:
                info_file = os.path.join(dest_dir, "magnet.txt")
                with open(info_file, "w", encoding="utf-8") as f:
                    f.write(magnet_uri + "\n")
                save_completed(magnet_uri)

        except Exception as e:
            print(f"❌ 同步失败 {btih_id}: {e}")


def update_trackers():
    """从远程下载最新的 trackers 列表。"""
    print(f"📥 更新 trackers: {TRACKERS_URL}")
    try:
        resp = requests.get(TRACKERS_URL, timeout=30)
        if resp.status_code == 200 and resp.text.strip():
            with open(TRACKERS_FILE, "w", encoding="utf-8") as f:
                f.write(resp.text)
            count = len([l for l in resp.text.strip().split("\n") if l.strip() and not l.startswith("#")])
            print(f"✅ Trackers 更新成功，共 {count} 条")
        else:
            print(f"⚠️  Trackers 下载内容为空")
    except Exception as e:
        print(f"⚠️  Trackers 下载失败: {e}")


def main():
    print("📋 任务管理器已启动")
    print(f"   ARIA2_RPC_URL    = {ARIA2_RPC_URL}")
    print(f"   MAGNET_FILE      = {MAGNET_FILE}")
    print(f"   COMPLETED_FILE   = {COMPLETED_FILE}")
    print(f"   ARIA2_DOWNLOAD   = {ARIA2_DOWNLOAD_DIR}")
    print(f"   MEDIA_DIR        = {MEDIA_DIR}")
    print(f"   CHECK_INTERVAL   = {CHECK_INTERVAL}")

    # 启动时更新 trackers
    update_trackers()

    # 等待 aria2 RPC 就绪
    print("⏳ 等待 aria2 RPC 服务就绪...")
    for i in range(30):
        version = rpc_call("aria2.getVersion")
        if version:
            print(f"✅ aria2 RPC 已就绪 (版本: {version.get('version', 'unknown')})")
            break
        print(f"   等待中... ({i+1}/30)")
        time.sleep(2)
    else:
        print("❌ aria2 RPC 连接超时，请检查 aria2 服务")
        return

    while True:
        try:
            # 1. 同步已完成任务到 media
            sync_completed_to_media()

            # 2. 检查新磁力链接并添加
            completed = load_completed()
            magnets = load_magnets()
            new_magnets = [m for m in magnets if m not in completed]

            if new_magnets:
                trackers = load_trackers()
                tracker_str = ",".join(trackers) if trackers else ""
                print(f"\n🔍 发现 {len(new_magnets)} 个新任务")
                for magnet in new_magnets:
                    add_magnet(magnet, tracker_str)

        except Exception as e:
            print(f"❌ 主循环异常: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
