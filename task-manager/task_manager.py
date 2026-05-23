"""
任务管理器：监控 magnet.txt，通过 aria2 RPC 自动添加下载任务，
只下载视频文件，下载完成后同步到 media 目录。
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
# 视频文件扩展名（小写）
VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".wmv", ".flv", ".mov", ".rmvb", ".rm",
    ".ts", ".m4v", ".mpg", ".mpeg", ".3gp", ".webm", ".vob", ".f4v",
}
# 图片扩展名（保留的图片文件）
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}
# ===================================================================

MAGNET_BTIH_PATTERN = re.compile(r"xt=urn:btih:([A-Fa-f0-9]{40})", re.IGNORECASE)
# 匹配文件名中嵌入的视频扩展名（如 1.mp4 或 video.mkv）
VIDEO_EXT_PATTERN = re.compile(r"\.(mp4|mkv|avi|wmv|flv|mov|rmvb|rm|ts|m4v|mpg|mpeg|3gp|webm|vob|f4v)\b", re.IGNORECASE)


def rpc_call(method, params=None):
    """调用 aria2 JSON-RPC 接口。

    params 可以是:
      - None: 无额外参数
      - 简单列表 [a, b, c]: 每个元素作为独立参数追加到 secret 后
      - 嵌套列表 [[a, b]]: 第一个元素作为整体参数追加（用于 keys=array 的情况）
    """
    payload = {
        "jsonrpc": "2.0",
        "id": "supermedia",
        "method": method,
        "params": ["token:" + ARIA2_SECRET] if ARIA2_SECRET else [],
    }
    if params:
        if params and isinstance(params[0], list):
            # 嵌套数组：第一个元素是数组，需要作为整体追加（如 keys=[array]）
            # [["gid", "status"]] -> ["token:secret", ["gid", "status"]]
            payload["params"].append(params[0])
        else:
            # 普通参数：每个元素独立追加 [0, 200, ["gid"]] -> ["token:secret", 0, 200, ["gid"]]
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


def is_video_file(filename):
    """判断文件名是否为视频文件（支持嵌入扩展名）。"""
    # 方法1：Path().suffix（标准扩展名）
    if Path(filename).suffix.lower() in VIDEO_EXTENSIONS:
        return True
    # 方法2：正则匹配嵌入在文件名中的扩展名（如 "video.mp4"）
    if VIDEO_EXT_PATTERN.search(filename):
        return True
    return False


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


def get_active_tasks():
    """获取活跃和等待中的任务（不包括已停止的）。"""
    tasks = {}

    # tellActive: 不需要参数
    result = rpc_call("aria2.tellActive")
    if result:
        for item in result:
            gid = item.get("gid")
            if gid:
                tasks[gid] = item

    # tellWaiting: 需要 offset, num, keys
    offset = 0
    while True:
        result = rpc_call("aria2.tellWaiting", [offset, 200, ["gid", "status", "bittorrent"]])
        if not result:
            break
        for item in result:
            gid = item.get("gid")
            if gid:
                tasks[gid] = item
        if len(result) < 200:
            break
        offset += 200

    return tasks


def get_all_tasks():
    """获取所有任务（等待中 + 活跃 + 已完成）。"""
    all_tasks = {}

    # tellWaiting: 需要 offset, num, keys
    offset = 0
    while True:
        result = rpc_call("aria2.tellWaiting", [offset, 200, ["gid", "status", "bittorrent"]])
        if not result:
            break
        for item in result:
            gid = item.get("gid")
            if gid:
                all_tasks[gid] = item
        if len(result) < 200:
            break
        offset += 200

    # tellActive: 不需要参数
    result = rpc_call("aria2.tellActive")
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
    """通过 RPC 添加磁力链接，元数据下载完成后自动选择视频文件。"""
    btih_id = extract_btih_id(magnet)

    # 检查是否已在 aria2 活跃任务中
    active_tasks = get_active_tasks()
    for task in active_tasks.values():
        bt_info = task.get("bittorrent", {})
        info_dict = bt_info.get("info", {})
        # info dict 不为空说明是 BT 任务
        if info_dict:
            print(f"⏭️  已存在: {btih_id}")
            return True

    # 构建选项
    options = {
        "dir": ARIA2_DOWNLOAD_DIR,
        "seed-time": "0",
    }
    if trackers:
        options["bt-tracker"] = trackers

    result = rpc_call("aria2.addUri", [[magnet], options])
    if result:
        print(f"✅ 已添加: {btih_id}")
        # 立即记录到 completed.txt，防止重复下发
        save_completed(magnet)
        return True
    else:
        print(f"❌ 添加失败: {btih_id}")
        return False


def process_metadata_tasks():
    """
    检查需要文件过滤的任务：对于 BT 任务，如果还没有选择文件，
    则获取文件列表，过滤视频文件后设置 select-file。
    """
    # 获取活跃 + 等待中的任务
    all_gids = []

    # tellActive: 需要显式请求 files 字段，否则可能不在响应中
    result = rpc_call("aria2.tellActive", [["gid", "status", "totalLength", "files", "bittorrent"]])
    if result:
        all_gids.extend([(g.get("gid"), g) for g in result])

    # tellWaiting: 需要 offset, num, keys
    offset = 0
    while True:
        result = rpc_call("aria2.tellWaiting", [offset, 200, ["gid", "status", "totalLength", "files", "bittorrent"]])
        if not result:
            break
        all_gids.extend([(g.get("gid"), g) for g in result])
        if len(result) < 200:
            break
        offset += 200

    # 调试：统计任务状态
    active_count = len(all_gids)
    if active_count > 0:
        print(f"🔍 检查 {active_count} 个活跃任务...")

    # 检查每个任务
    for gid, task in all_gids:
        total_len = int(task.get("totalLength", 0))
        files = task.get("files", [])
        bt_info = task.get("bittorrent", {})
        info = bt_info.get("info", {})

        # 检查是否需要文件过滤（总大小 > 0 但没有 torrent info）
        # 或者总大小等于元数据大小（< 1MB），说明还在下载元数据
        if total_len > 0 and total_len < 1024 * 1024 and not info:
            # 还在下载元数据，跳过
            continue

        # 如果有文件列表但没有 torrent info，说明是普通 HTTP 下载，不需要过滤
        if not info:
            continue

        # 有 torrent info，检查文件列表
        if not files:
            # 文件列表还没解析出来，跳过，等下次
            continue

        # 检查每个文件，过滤视频文件
        video_indices = []
        non_video_indices = []
        already_filtered = False  # 是否已经设置过 select-file
        for idx, f in enumerate(files):
            fname = f.get("path", "").split("/")[-1]
            selected = f.get("selected", "true") == "true"
            if is_video_file(fname):
                video_indices.append(idx + 1)
            else:
                non_video_indices.append(idx + 1)
                # 非视频文件未被选中，说明已经过滤过了
                if not selected:
                    already_filtered = True

        if not video_indices:
            # 没有视频文件，移除该任务
            print(f"⚠️  无视频文件，移除: {gid}")
            rpc_call("aria2.remove", [gid])
            continue

        # 如果所有文件都是视频格式，或者已经设置过 select-file，跳过
        if not non_video_indices or already_filtered:
            continue

        # 设置只下载视频文件
        select_str = ",".join(str(i) for i in video_indices)
        options = {"select-file": select_str}
        result = rpc_call("aria2.changeOption", [gid, options])
        if result == "OK":
            print(f"🎬 选择视频文件 [{select_str}]，移除非视频文件 {non_video_indices}: {gid}")
            for idx in non_video_indices[:3]:
                fname = files[idx - 1].get("path", "").split("/")[-1][:40]
                print(f"  移除: {fname}")
        else:
            print(f"⚠️  设置 select-file 失败: {gid} -> {result}")



def get_next_media_index():
    """获取 media 目录下一个可用的序号（001, 002, ...）。"""
    if not os.path.exists(MEDIA_DIR):
        return 1
    indices = []
    for name in os.listdir(MEDIA_DIR):
        if os.path.isdir(os.path.join(MEDIA_DIR, name)):
            try:
                indices.append(int(name))
            except ValueError:
                pass
    return max(indices, default=0) + 1


def generate_movie_nfo(dest_dir, original_title, original_files, magnet_uri=""):
    """生成 Jellyfin 可识别的 movie.nfo 文件。"""
    nfo_content = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<movie>
    <title>{original_title}</title>
    <originaltitle>{original_title}</originaltitle>
    <sorttitle>{original_title}</sorttitle>
    <comment>Magnet: {magnet_uri}</comment>
</movie>
"""
    nfo_path = os.path.join(dest_dir, "movie.nfo")
    with open(nfo_path, "w", encoding="utf-8") as f:
        f.write(nfo_content)


def sync_completed_to_media():
    """检查已完成任务，将下载文件同步到 media 目录，并规范化命名。"""
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

        # 只处理实际下载的文件（有路径且长度>0）
        downloaded_files = [
            f for f in files
            if f.get("path") and int(f.get("length", 0)) > 0
        ]
        if not downloaded_files:
            continue

        first_file = downloaded_files[0]
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

        # 源目录
        src_dir = os.path.dirname(file_path)
        if not os.path.isdir(src_dir):
            src_dir = ARIA2_DOWNLOAD_DIR

        # 获取原始目录名（用于 NFO）
        info_dict = bt_info.get("info", {}) if isinstance(bt_info, dict) else {}
        original_title = info_dict.get("name") if info_dict else os.path.basename(src_dir)
        if not original_title:
            original_title = "Unknown"

        # 生成序号目录名（001, 002, ...）
        media_index = get_next_media_index()
        dest_dir_name = f"{media_index:03d}"
        dest_dir = os.path.join(MEDIA_DIR, dest_dir_name)
        os.makedirs(dest_dir, exist_ok=True)

        # 收集原始文件名信息用于 NFO
        original_file_names = []

        # 同步并规范化文件
        try:
            synced = False

            for f in downloaded_files:
                src_path = f.get("path", "")
                if not src_path or not os.path.exists(src_path):
                    continue

                fname = os.path.basename(src_path)
                fext = Path(fname).suffix.lower()

                # 只保留视频和图片文件
                if fext not in VIDEO_EXTENSIONS and fext not in IMAGE_EXTENSIONS:
                    continue

                original_file_names.append(fname)

                # 保留原始文件名
                dest_path = os.path.join(dest_dir, fname)

                if os.path.isfile(src_path) and not os.path.exists(dest_path):
                    shutil.copy2(src_path, dest_path)
                    synced = True
                elif os.path.isdir(src_path):
                    if not os.path.exists(dest_path):
                        shutil.copytree(src_path, dest_path)
                        synced = True

            if synced:
                print(f"📁 已同步到 media/{dest_dir_name}: {original_title[:50]}")

                # 生成 NFO 文件
                generate_movie_nfo(dest_dir, original_title, original_file_names, magnet_uri)

                # 保存磁力链接信息
                if magnet_uri:
                    save_completed(magnet_uri)

            # 同步完成后删除 downloads 中的源目录
            if synced and src_dir != ARIA2_DOWNLOAD_DIR and os.path.isdir(src_dir):
                try:
                    shutil.rmtree(src_dir)
                    print(f"🗑️  已删除源目录: {src_dir}")
                except Exception as del_err:
                    print(f"⚠️  删除源目录失败 {src_dir}: {del_err}")

        except Exception as e:
            print(f"❌ 同步失败 {original_title}: {e}")


def cleanup_stale_tasks():
    """清理僵尸任务：超过12小时、进度<50%、已下载<600M。"""
    # 获取活跃 + 等待中的任务（需要时间信息）
    all_gids = []

    result = rpc_call("aria2.tellActive", [["gid", "status", "totalLength", "completedLength", "downloadSpeed", "connections", "numSeeders", "dir", "files", "bittorrent"]])
    if result:
        all_gids.extend(result)

    offset = 0
    while True:
        result = rpc_call("aria2.tellWaiting", [offset, 200, ["gid", "status", "totalLength", "completedLength", "downloadSpeed", "connections", "numSeeders", "dir", "files", "bittorrent"]])
        if not result:
            break
        all_gids.extend(result)
        if len(result) < 200:
            break
        offset += 200

    if not all_gids:
        return

    cleaned = 0
    now = time.time()
    stale_threshold = 12 * 3600  # 12小时（秒）
    max_downloaded = 600 * 1024 * 1024  # 600MB

    for task in all_gids:
        gid = task.get("gid", "")
        total_len = int(task.get("totalLength", 0))
        completed_len = int(task.get("completedLength", 0))
        download_speed = int(task.get("downloadSpeed", 0))

        # 跳过正在下载的任务（有速度说明活跃）
        if download_speed > 0:
            continue

        # 跳过总大小为0的任务（可能还在获取元数据）
        if total_len <= 0:
            continue

        # 计算进度
        progress = completed_len / total_len if total_len > 0 else 0

        # 判断是否为僵尸任务：进度<50% 且 已下载<600M
        if progress >= 0.5 or completed_len >= max_downloaded:
            continue

        # 检查是否超过12小时没有进展
        # 通过检查下载目录的修改时间来判断
        dir_path = task.get("dir", "")
        if dir_path and os.path.isdir(dir_path):
            try:
                dir_mtime = os.path.getmtime(dir_path)
                idle_seconds = now - dir_mtime
                if idle_seconds < stale_threshold:
                    continue
            except OSError:
                continue
        else:
            continue

        # 符合清理条件，移除任务
        bt_info = task.get("bittorrent", {})
        info_dict = bt_info.get("info", {}) if isinstance(bt_info, dict) else {}
        task_name = info_dict.get("name", gid)[:50]
        progress_pct = progress * 100
        downloaded_mb = completed_len / (1024 * 1024)
        idle_hours = (now - dir_mtime) / 3600

        print(f"🧹 清理僵尸任务: {task_name}")
        print(f"   进度: {progress_pct:.1f}%, 已下载: {downloaded_mb:.1f}MB, 空闲: {idle_hours:.1f}h")

        # 强制移除任务
        rpc_call("aria2.remove", [gid])

        # 删除下载目录中的残留文件
        if dir_path and os.path.isdir(dir_path) and dir_path != ARIA2_DOWNLOAD_DIR:
            try:
                shutil.rmtree(dir_path)
                print(f"   已删除残留目录: {dir_path}")
            except Exception as e:
                print(f"   删除残留目录失败: {e}")

        cleaned += 1

    if cleaned > 0:
        print(f"🧹 本次清理了 {cleaned} 个僵尸任务")


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
    print(f"   视频格式         = {', '.join(sorted(VIDEO_EXTENSIONS))}")

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
            # 1. 处理元数据就绪的任务（选择视频文件）
            process_metadata_tasks()

            # 2. 同步已完成任务到 media
            sync_completed_to_media()

            # 3. 清理僵尸任务（每轮都检查）
            cleanup_stale_tasks()

            # 4. 检查新磁力链接并添加
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
