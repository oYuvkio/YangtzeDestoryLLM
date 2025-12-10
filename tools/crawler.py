"""
新华网新闻爬取工具（API搜索+正文抓取，内置去重与断点续跑）。

设计要点：
- 来源：新华网搜索API (so.news.cn/getNews) 按关键词搜索。
- 反爬规避：随机 UA、抖动等待、超时/重试、遇到 403/429 指数退避。
- 正文抓取：默认开启，从新闻详情页提取正文内容。
- 去重/断点续跑：读取已有 jsonl，按 contentId 去重，新 run 不重复抓取。
- 保存：默认输出到 data/docs_for_kg/all_kg_corpus/科普 & 新闻/新闻/xinhua_news.jsonl，并创建文本备份（可选）。

使用示例：
python tools/crawler.py \
  --keywords "长江 防汛抗旱" "长江 洪水" "长江 干旱" \
  --max-pages 5 \
  --output data/docs_for_kg/all_kg_corpus/科普\ \&\ 新闻/新闻/xinhua_news.jsonl \
  --save-txt
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import math
import json
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Dict, Any, Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup  # type: ignore


# ==============================================================================
# 日志配置
# ==============================================================================
class FlushingFileHandler(logging.FileHandler):
    """每次写入后立即刷盘的 FileHandler"""
    
    def emit(self, record):
        super().emit(record)
        self.flush()


def setup_logger(
    name: str = "crawler",
    level: int = logging.INFO,
    log_file: Optional[Path] = None,
) -> logging.Logger:
    """配置并返回 logger"""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件输出（使用 FlushingFileHandler 确保实时刷盘）
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = FlushingFileHandler(log_file, encoding="utf-8", mode="a")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger.propagate = False
    return logger


logger = setup_logger()


# 新华网搜索API配置
XINHUA_API_BASE = "https://so.news.cn/getNews"
XINHUA_SEARCH_PAGE = "https://so.news.cn/"
XINHUA_REFERER = "https://so.news.cn/"
XINHUA_HOST = "so.news.cn"

# 全局 Session（保持 Cookie 和连接）
_session: Optional[requests.Session] = None

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
]


def rand_ua() -> str:
    return random.choice(USER_AGENTS)


def sleep_brief(min_ms: int = 500, max_ms: int = 1500) -> None:
    """短暂等待（增加间隔避免触发反爬）"""
    time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


def sleep_long(min_s: float = 2.0, max_s: float = 5.0) -> None:
    """较长的随机等待，用于页面间隔"""
    time.sleep(random.uniform(min_s, max_s))


def generate_wdcid() -> str:
    """生成随机的 wdcid Cookie 值"""
    import random
    chars = '0123456789abcdef'
    return ''.join(random.choice(chars) for _ in range(16))


def get_session() -> requests.Session:
    """获取或创建全局 Session（带 Cookie 保持）"""
    global _session
    if _session is None:
        _session = requests.Session()
        
        # 设置必要的 Cookie（模拟浏览器）
        _session.cookies.set('wdcid', generate_wdcid(), domain='.news.cn')
        _session.cookies.set('xinhuatoken', 'news', domain='.news.cn')
        _session.cookies.set('wdlast', str(int(time.time())), domain='.news.cn')
        
        _session.headers.update({
            "User-Agent": rand_ua(),
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        })
        
        # 先访问新华网首页建立会话
        try:
            logger.info("正在初始化会话（模拟浏览器访问）...")
            # 先访问主站
            resp = _session.get("https://www.news.cn/", timeout=10, headers={
                "User-Agent": rand_ua(),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            })
            sleep_long(1.0, 2.0)
            
            # 再访问搜索页
            resp = _session.get(XINHUA_SEARCH_PAGE, timeout=10, headers={
                "User-Agent": rand_ua(),
                "Referer": "https://www.news.cn/",
            })
            if resp.status_code == 200:
                logger.info(f"会话初始化成功，Cookie: {dict(_session.cookies)}")
            else:
                logger.warning(f"会话初始化状态码: {resp.status_code}")
            
            sleep_long(1.0, 2.0)  # 等待一下再开始搜索
        except Exception as e:
            logger.warning(f"会话初始化失败: {e}")
    return _session


def get_xinhua_headers() -> Dict[str, str]:
    """获取新华网 API 请求头"""
    return {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Connection": "keep-alive",
        "Host": XINHUA_HOST,
        "Referer": XINHUA_REFERER,
        "User-Agent": rand_ua(),
        "sec-ch-ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }


def make_search_url(keyword: str, page: int = 1, sort_field: int = 1) -> str:
    """
    构造新华网搜索API地址。
    - keyword: 关键词
    - page: 页码（从1开始）
    - sort_field: 排序方式（0=时间排序, 1=相关度排序）
    """
    encoded_kw = quote(keyword, safe="")
    return f"{XINHUA_API_BASE}?lang=cn&curPage={page}&searchFields=0&sortField={sort_field}&keyword={encoded_kw}"


def hash_id(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:16]


def fetch_search_page(keyword: str, page: int = 1, retries: int = 3, timeout: int = 15) -> Dict[str, Any]:
    """
    调用新华网搜索API获取一页结果。
    返回: {"results": [...], "pageCount": N, "resultCount": N} 或空字典
    """
    url = make_search_url(keyword, page)
    session = get_session()
    backoff = 1.0
    
    for attempt in range(retries):
        try:
            headers = get_xinhua_headers()
            resp = session.get(url, headers=headers, timeout=timeout)
            
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except json.JSONDecodeError:
                    logger.warning(f"JSON 解析失败，响应内容: {resp.text[:200]}")
                    return {}
                    
                if data.get("code") == 200 and data.get("content"):
                    content = data["content"]
                    return {
                        "results": content.get("results", []),
                        "pageCount": content.get("pageCount", 0),
                        "resultCount": content.get("resultCount", 0),
                        "keyword": content.get("keyword", keyword),
                    }
                logger.warning(f"API返回异常: code={data.get('code')}")
                return {}
            
            if resp.status_code in (403, 429):
                logger.warning(f"遇到限流 {resp.status_code}，重置会话并等待退避...")
                # 重置 session，获取新的 Cookie
                global _session
                _session = None
                sleep_long(3.0, 6.0)
                backoff *= 2
                time.sleep(min(backoff, 30))
                get_session()  # 重新初始化会话
            elif resp.status_code == 500:
                logger.warning(f"服务器错误 500 (尝试 {attempt + 1}/{retries})，等待后重试...")
                sleep_long(2.0, 4.0)
            else:
                logger.warning(f"请求失败: {resp.status_code}")
                sleep_brief(500, 1000)
                
        except requests.exceptions.Timeout:
            logger.warning(f"请求超时 (尝试 {attempt + 1}/{retries})")
            sleep_brief(500, 1000)
        except Exception as e:
            logger.warning(f"请求异常: {e}")
            sleep_brief(300, 800)
    
    return {}


def fetch_article_body(url: str, timeout: int = 15, retries: int = 3) -> str:
    """
    从新华网新闻页面抓取正文内容。
    新华网正文通常在 <div id="detail"> 或 <div class="main"> 等容器内。
    """
    session = get_session()
    backoff = 1.0
    
    for attempt in range(retries):
        try:
            headers = {
                "User-Agent": rand_ua(),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Connection": "keep-alive",
            }
            resp = session.get(url, headers=headers, timeout=timeout)
            
            if resp.status_code != 200:
                if resp.status_code in (403, 429):
                    logger.warning(f"正文抓取限流 {resp.status_code}: {url}")
                    sleep_brief(800, 1800)
                    backoff *= 2
                    time.sleep(min(backoff, 8))
                else:
                    sleep_brief()
                continue
            
            # 设置正确的编码
            resp.encoding = resp.apparent_encoding or "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # 新华网正文容器选择器（按优先级尝试）
            content_selectors = [
                "#detail",
                ".detail",
                "#article",
                ".article-content",
                ".main-aticle",
                ".content",
                "article",
            ]
            
            content_div = None
            for selector in content_selectors:
                content_div = soup.select_one(selector)
                if content_div:
                    break
            
            if content_div:
                # 移除脚本和样式
                for tag in content_div.find_all(["script", "style", "noscript"]):
                    tag.decompose()
                
                # 提取段落文本
                paragraphs = []
                for p in content_div.find_all("p"):
                    text = p.get_text(strip=True)
                    if text and len(text) > 5:
                        paragraphs.append(text)
                
                if paragraphs:
                    return "\n\n".join(paragraphs)
            
            # 回退：直接提取所有 <p> 标签
            paragraphs = []
            for p in soup.find_all("p"):
                text = p.get_text(strip=True)
                if text and len(text) > 10:
                    paragraphs.append(text)
            
            if paragraphs:
                return "\n\n".join(paragraphs)
                
        except requests.exceptions.Timeout:
            logger.warning(f"正文抓取超时: {url}")
            sleep_brief(500, 1000)
        except Exception as e:
            logger.warning(f"正文抓取异常: {e}")
            sleep_brief()
    
    return ""


def clean_html_tags(text: str) -> str:
    """清理HTML标签（如高亮标记）"""
    # 移除 <font> 等HTML标签
    text = re.sub(r"<[^>]+>", "", text)
    # 处理HTML实体
    text = text.replace("&nbsp;", " ")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&amp;", "&")
    return text.strip()


def crawl_keyword(
    keyword: str, 
    max_pages: int = 10, 
    fetch_content: bool = True,
    seen_ids: set | None = None,
    out_file = None,
) -> int:
    """
    爬取指定关键词的新华网新闻（实时写入模式）。
    
    Args:
        keyword: 搜索关键词
        max_pages: 最大爬取页数
        fetch_content: 是否抓取正文
        seen_ids: 已见过的ID集合（用于跳过）
        out_file: 打开的文件句柄，用于实时写入
    
    Returns:
        新增条目数量
    """
    new_count = 0
    seen_ids = seen_ids or set()
    
    # 先获取第一页，了解总页数
    logger.info(f"搜索关键词: {keyword}")
    first_page = fetch_search_page(keyword, page=1)
    
    if not first_page or not first_page.get("results"):
        logger.warning(f"关键词 '{keyword}' 无搜索结果")
        return entries
    
    total_pages = min(first_page.get("pageCount", 1), max_pages)
    total_count = first_page.get("resultCount", 0)
    logger.info(f"共 {total_count} 条结果，{first_page.get('pageCount', 1)} 页，将爬取 {total_pages} 页")
    
    # 处理所有页面
    for page_num in range(1, total_pages + 1):
        if page_num == 1:
            page_data = first_page
        else:
            sleep_long(1.0, 2.5)  # 页面间隔
            page_data = fetch_search_page(keyword, page=page_num)
        
        if not page_data or not page_data.get("results"):
            logger.warning(f"第 {page_num} 页无数据，跳过")
            continue
        
        results = page_data["results"]
        logger.info(f"第 {page_num}/{total_pages} 页，获取 {len(results)} 条")
        
        for item in results:
            content_id = item.get("contentId", "")
            
            # 跳过已存在的
            if content_id in seen_ids:
                continue
            
            url = item.get("url", "")
            title = clean_html_tags(item.get("title", ""))
            summary = clean_html_tags(item.get("des", "") or "")
            pubtime = item.get("pubtime", "")
            sitename = item.get("sitename", "")
            
            entry = {
                "id": content_id or hash_id(url or title),
                "keyword": keyword,
                "title": title,
                "url": url,
                "summary": summary,
                "pubtime": pubtime,
                "sitename": sitename,
                "source": "新华网",
                "fetched_at": datetime.utcnow().isoformat(),
            }
            
            # 抓取正文
            if fetch_content and url:
                sleep_long(1.5, 3.0)  # 正文抓取间隔（增加避免触发反爬）
                content = fetch_article_body(url)
                entry["content"] = content
                if content:
                    logger.info(f"  [OK] {title[:30]}... ({len(content)} 字)")
                else:
                    logger.debug(f"  [SKIP] {title[:30]}... (正文抓取失败)")
            
            # 实时写入文件
            if out_file:
                out_file.write(json.dumps(entry, ensure_ascii=False) + "\n")
                out_file.flush()  # 立即刷新到磁盘
            
            new_count += 1
            seen_ids.add(content_id)
    
    return new_count


def load_seen(out_path: Path) -> Dict[str, Dict[str, Any]]:
    """读取已有 jsonl，返回 {id: obj}，用于去重/续跑。"""
    seen: Dict[str, Dict[str, Any]] = {}
    if not out_path.exists():
        return seen
    try:
        with out_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    uid = obj.get("id")
                    if uid:
                        seen[uid] = obj
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.warning(f"加载已有记录失败: {e}")
    return seen


def save_jsonl_append(items: Iterable[Dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as f:
        for obj in items:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="新华网新闻爬取工具（长江水旱灾害相关，带断点续跑）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python tools/crawler.py --keywords "长江 防汛抗旱" "长江 洪水" --max-pages 5
  python tools/crawler.py --keywords "长江 干旱" --max-pages 10 --save-txt
        """
    )
    parser.add_argument(
        "--keywords", nargs="+", required=True,
        help="关键词列表，例如 '长江 防汛抗旱' '长江 洪水' '长江 干旱'"
    )
    parser.add_argument(
        "--max-pages", type=int, default=5,
        help="每个关键词最大爬取页数，默认 5（每页约10条）"
    )
    parser.add_argument(
        "--all", action="store_true",
        help="爬取该关键词下的所有页面（忽略 --max-pages）"
    )
    parser.add_argument(
        "--no-content", action="store_true",
        help="不抓取正文（仅获取标题和摘要）"
    )
    parser.add_argument(
        "--output", default="data/docs_for_kg/all_kg_corpus/科普 & 新闻/新闻/xinhua_news.jsonl",
        help="输出 JSONL 路径"
    )
    parser.add_argument(
        "--save-txt", action="store_true",
        help="额外保存正文为独立 txt 文件"
    )
    parser.add_argument(
        "--log-file", default=None,
        help="日志文件路径（默认不保存到文件）"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="详细输出（DEBUG 级别）"
    )
    args = parser.parse_args()
    
    # 配置日志
    global logger
    log_level = logging.DEBUG if args.verbose else logging.INFO
    log_file = Path(args.log_file) if args.log_file else None
    logger = setup_logger(level=log_level, log_file=log_file)

    out_path = Path(args.output)
    seen = load_seen(out_path)
    seen_ids = set(seen.keys())
    
    logger.info("=" * 60)
    logger.info("新华网新闻爬取工具")
    logger.info("=" * 60)
    logger.info(f"载入已有记录 {len(seen)} 条（用于去重/续跑）")
    logger.info(f"输出路径: {out_path}")
    if log_file:
        logger.info(f"日志文件: {log_file}")
    logger.info(f"关键词: {args.keywords}")
    max_pages = 99999 if args.all else args.max_pages
    logger.info(f"每关键词最大页数: {'全部' if args.all else max_pages}")
    logger.info(f"抓取正文: {not args.no_content}")
    logger.info("=" * 60)

    total_new = 0
    fetch_content = not args.no_content
    
    # 以追加模式打开文件，实时写入
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as out_file:
        for kw in args.keywords:
            logger.info("─" * 40)
            new_count = crawl_keyword(
                kw, 
                max_pages=max_pages,
                fetch_content=fetch_content,
                seen_ids=seen_ids,
                out_file=out_file,
            )
            logger.info(f"关键词 '{kw}' 新增 {new_count} 条（已实时保存）")
            total_new += new_count
            
            # 关键词间隔
            if kw != args.keywords[-1]:
                sleep_long(2.0, 4.0)
    
    if total_new == 0:
        logger.info("没有新增内容（可能全部已抓取）")
        return
    
    logger.info("=" * 60)
    logger.info("爬取完成！")
    logger.info(f"  - 新增: {total_new} 条（已实时写入）")
    logger.info(f"  - 总计: {len(seen) + total_new} 条")
    logger.info(f"  - 输出: {out_path}")
    logger.info("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("用户中断，已保存进度")
    except Exception as e:
        logger.error(f"发生异常: {e}")
        raise
