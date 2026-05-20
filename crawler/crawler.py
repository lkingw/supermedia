"""
SuperMedia 爬虫模块
功能：从配置的种子 URL 列表出发，爬取页面并提取磁力链接（magnet:?xt=urn:btih:...），
      支持多深度链接跟随、去重、定时调度。
"""

import os
import re
import time
import logging
import schedule
from urllib.parse import urljoin, urlparse
from datetime import datetime

import requests
from bs4 import BeautifulSoup

# ============================================================
# 日志配置
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ============================================================
# 环境变量 / 默认配置
# ============================================================
URLS_FILE = os.environ.get("URLS_FILE", "/app/data/config/urls.txt")
MAGNET_FILE = os.environ.get("MAGNET_FILE", "/app/data/magnet.txt")
COMPLETED_FILE = os.environ.get("COMPLETED_FILE", "/app/data/completed.txt")
CRAWL_DEPTH = int(os.environ.get("CRAWL_DEPTH", "1"))
CRAWL_INTERVAL = os.environ.get("CRAWL_INTERVAL", "6h")

# 请求超时（秒）
REQUEST_TIMEOUT = 30

# 请求头，模拟浏览器访问
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 磁力链接正则表达式
MAGNET_PATTERN = re.compile(r"magnet:\?xt=urn:btih:[A-Za-z0-9]{32,40}[^\s\"'<>]*", re.IGNORECASE)


# ============================================================
# 工具函数
# ============================================================

def parse_interval(interval_str: str) -> int:
    """
    解析时间间隔字符串，返回秒数。
    支持格式：1h, 30m, 2h, 6h 等。
    """
    interval_str = interval_str.strip().lower()
    if interval_str.endswith("h"):
        return int(interval_str[:-1]) * 3600
    elif interval_str.endswith("m"):
        return int(interval_str[:-1]) * 60
    elif interval_str.endswith("s"):
        return int(interval_str[:-1])
    else:
        # 默认按小时解析
        try:
            return int(interval_str) * 3600
        except ValueError:
            logger.warning("无法解析 CRAWL_INTERVAL='%s'，使用默认值 6 小时", interval_str)
            return 6 * 3600


def read_urls(filepath: str) -> list[str]:
    """
    从文件中读取 URL 列表。
    每行一个 URL，忽略空行和 # 开头的注释行。
    """
    urls = []
    if not os.path.isfile(filepath):
        logger.warning("URL 文件不存在: %s", filepath)
        return urls

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            urls.append(line)

    logger.info("从 %s 读取到 %d 个种子 URL", filepath, len(urls))
    return urls


def read_existing_magnets(filepath: str) -> set[str]:
    """
    读取已有的磁力链接集合（用于去重）。
    如果文件不存在则返回空集合。
    """
    magnets = set()
    if not os.path.isfile(filepath):
        return magnets

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                magnets.add(line)

    return magnets


def extract_magnets_from_text(text: str) -> list[str]:
    """
    从文本中使用正则提取所有磁力链接。
    """
    return MAGNET_PATTERN.findall(text)


def is_same_domain(url: str, base_url: str) -> bool:
    """
    判断两个 URL 是否属于同一域名，避免爬取到外部网站。
    """
    try:
        parsed_url = urlparse(url)
        parsed_base = urlparse(base_url)
        return parsed_url.netloc == parsed_base.netloc
    except Exception:
        return False


def normalize_url(url: str) -> str:
    """
    规范化 URL，去除片段标识符。
    """
    try:
        parsed = urlparse(url)
        return parsed._replace(fragment="").geturl()
    except Exception:
        return url


# ============================================================
# 核心爬取逻辑
# ============================================================

def fetch_page(url: str) -> str:
    """
    请求并返回页面 HTML 内容。
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, verify=False)
        resp.raise_for_status()
        # 尝试自动检测编码
        if resp.encoding and resp.encoding.lower() != "iso-8859-1":
            return resp.text
        else:
            # 使用 apparent_encoding 作为备选
            resp.encoding = resp.apparent_encoding
            return resp.text
    except requests.RequestException as e:
        logger.error("请求页面失败 [%s]: %s", url, e)
        return ""


def extract_links(html: str, base_url: str) -> list[str]:
    """
    从 HTML 中提取同域名下的所有链接。
    """
    links = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue
            # 将相对 URL 转为绝对 URL
            full_url = urljoin(base_url, href)
            full_url = normalize_url(full_url)
            # 只保留同域名链接和 http/https 协议
            if full_url.startswith(("http://", "https://")) and is_same_domain(full_url, base_url):
                links.append(full_url)
    except Exception as e:
        logger.error("解析页面链接失败 [%s]: %s", base_url, e)
    return links


def crawl_url(url: str, depth: int, max_depth: int, visited: set[str], existing_magnets: set[str]) -> list[str]:
    """
    递归爬取单个 URL，提取磁力链接。
    - depth: 当前深度
    - max_depth: 最大爬取深度
    - visited: 已访问 URL 集合（避免循环）
    - existing_magnets: 已有磁力链接集合（用于去重）
    返回：新发现的磁力链接列表
    """
    new_magnets = []

    # 规范化 URL
    url = normalize_url(url)

    # 避免重复访问
    if url in visited:
        return new_magnets
    visited.add(url)

    logger.info("正在爬取 [深度 %d/%d]: %s", depth, max_depth, url)

    # 请求页面
    html = fetch_page(url)
    if not html:
        return new_magnets

    # 从页面文本中提取磁力链接
    page_magnets = extract_magnets_from_text(html)
    for magnet in page_magnets:
        if magnet not in existing_magnets:
            new_magnets.append(magnet)
            existing_magnets.add(magnet)
            logger.info("发现新磁力链接: %s", magnet[:80] + "..." if len(magnet) > 80 else magnet)

    # 如果还有剩余深度，继续跟随链接
    if depth < max_depth:
        links = extract_links(html, url)
        for link in links:
            if link not in visited:
                sub_magnets = crawl_url(link, depth + 1, max_depth, visited, existing_magnets)
                new_magnets.extend(sub_magnets)

    return new_magnets


def run_crawl():
    """
    执行一次完整的爬取任务。
    """
    logger.info("=" * 60)
    logger.info("开始执行爬取任务 | 深度: %d | 时间: %s", CRAWL_DEPTH, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("=" * 60)

    # 读取种子 URL
    seed_urls = read_urls(URLS_FILE)
    if not seed_urls:
        logger.warning("没有可用的种子 URL，跳过本次爬取")
        return

    # 读取已有磁力链接（去重用）
    existing_magnets = read_existing_magnets(MAGNET_FILE)
    existing_magnets |= read_existing_magnets(COMPLETED_FILE)
    logger.info("已有磁力链接数量: %d", len(existing_magnets))

    # 已访问 URL 集合
    visited = set()

    # 所有新发现的磁力链接
    all_new_magnets = []

    # 对每个种子 URL 执行爬取
    for seed_url in seed_urls:
        try:
            new_magnets = crawl_url(
                url=seed_url,
                depth=0,
                max_depth=CRAWL_DEPTH,
                visited=visited,
                existing_magnets=existing_magnets,
            )
            all_new_magnets.extend(new_magnets)
        except Exception as e:
            logger.error("爬取种子 URL 失败 [%s]: %s", seed_url, e)

    # 写入新磁力链接
    if all_new_magnets:
        # 去重（可能从不同页面提取到相同链接）
        unique_magnets = list(dict.fromkeys(all_new_magnets))
        logger.info("共发现 %d 条新磁力链接（去重后 %d 条）", len(all_new_magnets), len(unique_magnets))

        # 确保目录存在
        os.makedirs(os.path.dirname(MAGNET_FILE), exist_ok=True)

        # 追加写入
        with open(MAGNET_FILE, "a", encoding="utf-8") as f:
            for magnet in unique_magnets:
                f.write(magnet + "\n")

        logger.info("新磁力链接已追加写入: %s", MAGNET_FILE)
    else:
        logger.info("本次爬取未发现新磁力链接")

    logger.info("爬取任务完成 | 访问页面数: %d | 新磁力链接数: %d", len(visited), len(all_new_magnets))


# ============================================================
# 定时调度
# ============================================================

def main():
    """
    主入口：启动定时调度爬虫。
    """
    logger.info("SuperMedia 爬虫模块启动")
    logger.info("配置信息:")
    logger.info("  URLS_FILE      = %s", URLS_FILE)
    logger.info("  MAGNET_FILE    = %s", MAGNET_FILE)
    logger.info("  COMPLETED_FILE = %s", COMPLETED_FILE)
    logger.info("  CRAWL_DEPTH    = %d", CRAWL_DEPTH)
    logger.info("  CRAWL_INTERVAL = %s", CRAWL_INTERVAL)

    # 解析调度间隔
    interval_seconds = parse_interval(CRAWL_INTERVAL)
    logger.info("  调度间隔      = %d 秒 (%.1f 小时)", interval_seconds, interval_seconds / 3600)

    # 启动时立即执行一次
    logger.info("首次启动，立即执行一次爬取...")
    try:
        run_crawl()
    except Exception as e:
        logger.error("首次爬取执行出错: %s", e)

    # 设置定时任务
    schedule.every(interval_seconds).seconds.do(run_crawl)

    logger.info("定时调度已设置，等待下次执行...")

    # 持续运行调度循环
    while True:
        try:
            schedule.run_pending()
            time.sleep(10)
        except KeyboardInterrupt:
            logger.info("收到中断信号，爬虫停止运行")
            break
        except Exception as e:
            logger.error("调度循环异常: %s，等待下次调度周期重试", e)
            time.sleep(60)


if __name__ == "__main__":
    # 禁用 requests 的 SSL 警告
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    main()
