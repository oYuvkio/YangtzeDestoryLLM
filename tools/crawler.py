"""
新闻爬取工具（RSS+正文抓取，内置去重与断点续跑，尽量降低反爬风险）。

设计要点：
- 来源：Google News RSS 按关键词搜索，可选 site 限定（避免对单一站点高频抓取）。
- 反爬规避：随机 UA、抖动等待、超时/重试、遇到 403/429 指数退避。
- 正文抓取：默认开启（满足“需要正文”的需求），用轻量级 <p> 抽取。
- 去重/断点续跑：读取已有 jsonl，按 link+title 的 MD5 去重，新 run 不重复抓取。
- 保存：默认输出到 data/docs_for_kg/all_kg_corpus/科普 & 新闻/新闻/news.jsonl，并创建文本备份（可选）。

使用示例：
python tools/news_crawler.py \
  --keywords "长江洪水" "长江干旱" \
  --max-per-keyword 30 \
  --output-json "data/docs_for_kg/all_kg_corpus/科普 & 新闻/新闻/news.jsonl" \
  --save-txt
"""
from __future__ import annotations

import argparse
import hashlib
import math
import json
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Dict, Any

import feedparser  # type: ignore
import requests
from bs4 import BeautifulSoup  # type: ignore


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
]


def rand_ua() -> str:
    return random.choice(USER_AGENTS)


def sleep_brief(min_ms: int = 200, max_ms: int = 800) -> None:
    time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


def make_feed_url(keyword: str, site: str | None = None, lang: str = "zh-CN") -> str:
    """
    构造 Google News RSS 搜索地址。
    - keyword: 关键词（会做 URL 编码）
    - site: 可选站点限定，如 "site:people.com.cn"
    """
    from urllib.parse import quote_plus

    query = keyword
    if site:
        query = f"{keyword} {site}"
    return f"https://news.google.com/rss/search?q={quote_plus(query)}&hl={lang}"


def hash_id(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:16]


def fetch_feed(url: str, retries: int = 3, timeout: int = 10) -> feedparser.FeedParserDict:
    backoff = 1.0
    for _ in range(retries):
        try:
            headers = {"User-Agent": rand_ua()}
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                return feedparser.parse(resp.text)
            if resp.status_code in (403, 429):
                sleep_brief(800, 1800)
                backoff *= 2
                time.sleep(min(backoff, 8))
        except Exception:
            sleep_brief(300, 800)
    return feedparser.parse("")  # 失败返回空


def fetch_article_body(url: str, timeout: int = 10, retries: int = 2) -> str:
    """
    简单正文抓取（可选）：获取 HTML 后提取 <p> 文本。
    可能受反爬限制，请谨慎开启。
    """
    backoff = 1.0
    for _ in range(retries):
        try:
            headers = {"User-Agent": rand_ua()}
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code != 200:
                if resp.status_code in (403, 429):
                    sleep_brief(800, 1800)
                    backoff *= 2
                    time.sleep(min(backoff, 8))
                else:
                    sleep_brief()
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            paragraphs = [p.get_text(strip=True) for p in soup.find_all("p")]
            body = "\n".join([p for p in paragraphs if p])
            if body:
                return body
        except Exception:
            sleep_brief()
    return ""


def crawl_keyword(keyword: str, max_count: int, fetch_content: bool, sites: List[str] | None = None) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    sites = sites or [None]
    for site in sites:
        feed_url = make_feed_url(keyword, site=site)
        feed = fetch_feed(feed_url)
        for entry in feed.entries:
            if len(entries) >= max_count:
                break
            link = entry.get("link") or entry.get("id") or ""
            title = entry.get("title", "")
            summary = entry.get("summary", "")
            published = entry.get("published", "")
            # 去重 ID：优先 link，其次标题；不包含 keyword，避免跨关键词重复
            uid = hash_id(f"{link or title}")
            item = {
                "id": uid,
                "keyword": keyword,
                "title": title,
                "link": link,
                "summary": summary,
                "published": published,
                "source": entry.get("source", {}).get("title") if isinstance(entry.get("source"), dict) else None,
                "fetched_at": datetime.utcnow().isoformat(),
            }
            if fetch_content and link:
                item["content"] = fetch_article_body(link)
            entries.append(item)
        sleep_brief()
    return entries[:max_count]


def load_seen(out_path: Path) -> Dict[str, Dict[str, Any]]:
    """读取已有 jsonl，返回 {id: obj}，用于去重/续跑。"""
    seen: Dict[str, Dict[str, Any]] = {}
    if not out_path.exists():
        return seen
    try:
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            uid = obj.get("id")
            if uid:
                seen[uid] = obj
    except Exception:
        pass
    return seen


def save_jsonl_append(items: Iterable[Dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as f:
        for obj in items:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="长江水旱灾害相关新闻爬取（RSS+正文，带断点续跑）")
    parser.add_argument("--keywords", nargs="+",
                        required=True, help="关键词列表，例如 '长江洪水' '长江干旱'")
    parser.add_argument("--sites", nargs="*", default=[],
                        help="可选站点限定（site:xxx），如 people.com.cn")
    parser.add_argument("--max-per-keyword", type=int,
                        default=30, help="每个关键词最多抓取条数，默认 30")
    parser.add_argument("--fetch-content", action="store_true", default=True,
                        help="是否抓取正文（默认 True，注意频率以防反爬）")
    parser.add_argument("--output", default="data/docs_for_kg/all_kg_corpus/科普 & 新闻/新闻/news.jsonl",
                        help="输出 JSONL 路径（默认保存到 data/docs_for_kg/.../新闻/news.jsonl）")
    parser.add_argument("--save-txt", action="store_true",
                        help="是否额外保存正文 txt（与 jsonl 同目录），默认不保存")
    args = parser.parse_args()

    out_path = Path(args.output)
    seen = load_seen(out_path)
    print(f"[NEWS] 载入已有记录 {len(seen)} 条（用于去重/续跑）")

    all_items: List[Dict[str, Any]] = []
    for kw in args.keywords:
        print(f"[NEWS] 抓取关键词: {kw}")
        items = crawl_keyword(kw, args.max_per_keyword,
                              args.fetch_content, sites=args.sites or None)
        print(f"[NEWS] 关键词 {kw} 获取 {len(items)} 条")
        all_items.extend(items)

    # 断点续跑去重
    new_items = [it for it in all_items if it.get("id") not in seen]
    if not new_items:
        print("[NEWS] 没有新增内容（可能全部已抓取）")
        return

    save_jsonl_append(new_items, out_path)
    print(
        f"[NEWS] 完成：新增 {len(new_items)} 条，总计 {len(seen) + len(new_items)} 条，输出 {out_path}")

    if args.save_txt:
        txt_dir = out_path.parent
        for item in new_items:
            content = item.get("content")
            if not content:
                continue
            fname = f"{item['id']}.txt"
            (txt_dir / fname).write_text(content, encoding="utf-8")
        print(f"[NEWS] 已额外保存正文 txt 到目录：{txt_dir}")


if __name__ == "__main__":
    main()
