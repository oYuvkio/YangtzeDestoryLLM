#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PaddleOCRVL 批量 OCR（PDF -> Markdown）。

需求目标
- 读取 `data/corpus_for_kg/raw_all/灾害案例 & 论文/论文_ori` 下的 PDF（递归）
- 输出同名 `.md` 到 `data/corpus_for_kg/raw_all/灾害案例 & 论文/论文_handled`
- 不保存图片文件，并在 Markdown 中移除所有图片引用（imgs/...）
- 支持断点续跑：缓存记录每个文件的处理状态与文件指纹（mtime/size）
- 日志输出到 `logs/ocr/`

说明
PaddleOCR 的 markdown 默认会以 HTML `<img src="imgs/xxx.jpg" .../>` 引用图片，
这里会在写出前做后处理，去掉这些图片块与引用。
"""

from __future__ import annotations

import argparse
import hashlib
import base64
import json
import logging
import os
import re
import shutil
import sys
import threading
import time
import traceback
import socket
import urllib.error
import urllib.request
from urllib.parse import urlparse
from concurrent.futures import (
    Future,
    ThreadPoolExecutor,
    as_completed,
    wait,
    FIRST_COMPLETED,
)
from dataclasses import dataclass, asdict
from json import JSONDecodeError
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Set, Tuple


try:  # pragma: no cover - Windows/特殊环境可能不存在
    import fcntl  # type: ignore
except Exception:  # pragma: no cover
    fcntl = None  # type: ignore


def _sanitize_ld_library_path() -> None:
    """
    规避 ~/.bashrc 里把 /usr/local/cuda/lib* 放到 LD_LIBRARY_PATH 的情况。

    该设置可能会抢先加载旧版 NCCL，导致 `import torch`/`import paddleocr` 失败。
    """
    ld_library_path = os.environ.get("LD_LIBRARY_PATH", "")
    if not ld_library_path:
        return
    parts = [p for p in ld_library_path.split(":") if p]
    parts = [p for p in parts if p not in ("/usr/local/cuda/lib", "/usr/local/cuda/lib64")]
    os.environ["LD_LIBRARY_PATH"] = ":".join(parts)


_sanitize_ld_library_path()

try:
    from paddleocr import PaddleOCRVL
except Exception as e:  # pragma: no cover - 运行时依赖
    PaddleOCRVL = None  # type: ignore[assignment]
    _PADDLEOCR_IMPORT_ERROR = e

DEFAULT_API_URL = "http://127.0.0.1:8123/layout-parsing"


DEFAULT_INPUT_ROOT = Path("data/corpus_for_kg/raw_all/灾害案例 & 论文/论文_ori")
DEFAULT_OUTPUT_ROOT = Path("data/corpus_for_kg/raw_all/灾害案例 & 论文/论文_handled")
DEFAULT_LOG_DIR = Path("logs/ocr")
DEFAULT_CACHE_FILE = DEFAULT_LOG_DIR / "paddleocr_cache.jsonl"


def setup_logger(log_dir: Path, verbose: bool) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("paddle_ocr_batch")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(formatter)
    logger.addHandler(console)

    log_file = log_dir / f"paddle_ocr_{time.strftime('%Y%m%d_%H%M%S')}_pid{os.getpid()}.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logger.propagate = False
    logger.info(f"日志文件: {log_file}")
    return logger


@dataclass(frozen=True)
class FileFingerprint:
    size: int
    mtime_ns: int

    @classmethod
    def from_path(cls, path: Path) -> "FileFingerprint":
        stat = path.stat()
        return cls(size=int(stat.st_size), mtime_ns=int(stat.st_mtime_ns))


@dataclass
class CacheRecord:
    input_path: str
    output_md: str
    # 状态值（向后兼容旧值 failed）：
    # - success
    # - failed_timeout   （请求超时，不重试）
    # - failed_parse     （解析错误，最多重试 2 次后仍失败）
    # - failed_unavailable（服务不可用：Connection refused 等）
    # - failed_other     （其他错误）
    # - failed           （旧版本遗留）
    status: str
    fingerprint: Dict[str, Any]
    updated_at: str
    message: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


class JsonlCache:
    """
    简单 JSONL 缓存：每条记录 append 写入，启动时扫描并取最后一条为准。
    """

    def __init__(self, path: Path, logger: logging.Logger):
        self.path = path
        self.logger = logger
        self._records: Dict[str, CacheRecord] = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with self.path.open("r", encoding="utf-8") as file_handle:
                for line in file_handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        rec = CacheRecord(
                            input_path=str(data.get("input_path", "")),
                            output_md=str(data.get("output_md", "")),
                            status=str(data.get("status", "")),
                            fingerprint=dict(data.get("fingerprint") or {}),
                            updated_at=str(data.get("updated_at", "")),
                            message=str(data.get("message", "")),
                        )
                        if rec.input_path:
                            self._records[rec.input_path] = rec
                    except Exception:
                        continue
            self.logger.info(f"加载缓存: {self.path} (记录 {len(self._records)} 条)")
        except Exception as e:
            self.logger.warning(f"读取缓存失败，将忽略: {e}")

    def get(self, input_path: Path) -> Optional[CacheRecord]:
        with self._lock:
            return self._records.get(str(input_path))

    def _append_line_bytes(self, line: bytes) -> None:
        """
        追加写入一行 JSONL（跨进程安全）。

        说明：
        - 单进程下直接写入即可；
        - 多进程同时 append 时，如果不加锁，可能出现行内容交错导致缓存损坏；
        - Linux 下优先使用 `fcntl.flock` 做互斥（Windows 下自动降级）。
        """
        with self.path.open("ab") as file_handle:
            if fcntl is not None:
                fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX)
            try:
                file_handle.write(line)
                file_handle.flush()
            finally:
                if fcntl is not None:
                    try:
                        fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)
                    except Exception:
                        pass

    def upsert(self, record: CacheRecord) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            line = (record.to_json() + "\n").encode("utf-8")
            try:
                self._append_line_bytes(line)
            except Exception as e:
                # 不中断主流程：写缓存失败只会影响断点续跑
                self.logger.warning(f"写入缓存失败（将继续运行）: {e}")
            self._records[record.input_path] = record


def _is_pid_alive(pid: int) -> bool:
    """
    判断进程是否仍在运行。

    说明：
    - Linux/macOS：使用 `os.kill(pid, 0)` 判断；
    - Windows：无法稳定判断时保守返回 True（避免误删运行标记）。
    """
    if pid <= 0:
        return False
    if os.name == "nt":  # pragma: no cover
        return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return True


class RunMarker:
    """
    多进程运行标记：用于判断是否存在其他仍在运行的 OCR 进程。

    目的：
    - 多 tmux 并行跑时，避免某个进程提前执行全局清理（删除 imgs/）导致另一个进程正在写图时报错。
    - 通过 pid 存活检查，尽量清理“僵尸标记”。
    """

    def __init__(self, run_dir: Path, *, logger: logging.Logger):
        self.run_dir = run_dir
        self.logger = logger
        self.pid = int(os.getpid())
        self.path = self.run_dir / f"run_{self.pid}.json"
        self._started = False

    def start(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "pid": self.pid,
            "host": socket.gethostname(),
            "started_at": time.time(),
            "cmdline": sys.argv,
        }
        try:
            tmp_path = self.path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            tmp_path.replace(self.path)
            self._started = True
        except Exception as e:
            self.logger.warning(f"写入运行标记失败（不影响 OCR）：{e}")

    def stop(self) -> None:
        if not self._started:
            return
        try:
            if self.path.exists():
                self.path.unlink()
        except Exception:
            pass
        self._started = False

    @staticmethod
    def list_other_active_pids(run_dir: Path, *, current_pid: int, logger: logging.Logger) -> Set[int]:
        active: Set[int] = set()
        if not run_dir.exists():
            return active

        for marker in run_dir.glob("run_*.json"):
            pid_str = marker.stem.replace("run_", "", 1)
            try:
                pid = int(pid_str)
            except Exception:
                continue
            if pid == current_pid:
                continue
            if _is_pid_alive(pid):
                active.add(pid)
                continue
            # 清理僵尸标记
            try:
                marker.unlink()
            except Exception:
                pass
        return active


class HeldLock:
    """
    代表一个已持有的锁（用于跨进程互斥）。
    """

    def release(self) -> None:
        raise NotImplementedError

    def __enter__(self) -> "HeldLock":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


class FlockHeldLock(HeldLock):
    """
    基于 `fcntl.flock` 的文件锁（Linux/macOS）。
    """

    def __init__(self, file_handle, lock_path: Path):
        self._file_handle = file_handle
        self.lock_path = lock_path

    @classmethod
    def try_acquire(cls, lock_path: Path) -> Optional["FlockHeldLock"]:
        if fcntl is None:  # pragma: no cover
            return None
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        file_handle = lock_path.open("a", encoding="utf-8")
        try:
            fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return cls(file_handle=file_handle, lock_path=lock_path)
        except BlockingIOError:
            file_handle.close()
            return None
        except OSError as e:
            # 常见“抢不到锁”错误：EAGAIN(11)/EACCES(13)/EWOULDBLOCK(35)
            file_handle.close()
            if getattr(e, "errno", None) in (11, 13, 35):
                return None
            raise

    def release(self) -> None:
        try:
            if fcntl is not None:
                try:
                    fcntl.flock(self._file_handle.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
        finally:
            try:
                self._file_handle.close()
            except Exception:
                pass


class MkdirHeldLock(HeldLock):
    """
    基于“原子创建目录”的锁（可作为 flock 不可用时的后备方案）。
    """

    def __init__(self, lock_dir: Path):
        self.lock_dir = lock_dir
        self._released = False

    @classmethod
    def try_acquire(cls, lock_dir: Path) -> Optional["MkdirHeldLock"]:
        lock_dir.parent.mkdir(parents=True, exist_ok=True)
        try:
            lock_dir.mkdir(parents=False, exist_ok=False)
        except FileExistsError:
            meta = lock_dir / "meta.json"
            pid = 0
            try:
                if meta.exists():
                    data = json.loads(meta.read_text(encoding="utf-8"))
                    pid = int(data.get("pid", 0) or 0)
            except Exception:
                pid = 0

            # 尝试回收僵尸锁
            if pid and not _is_pid_alive(pid):
                try:
                    shutil.rmtree(lock_dir)
                except Exception:
                    return None
                try:
                    lock_dir.mkdir(parents=False, exist_ok=False)
                except FileExistsError:
                    # 竞态：删除后被其他进程抢先创建，视为获取失败
                    return None
                except Exception:
                    return None
            else:
                return None
        except Exception:
            return None

        try:
            (lock_dir / "meta.json").write_text(
                json.dumps({"pid": os.getpid(), "created_at": time.time()}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass
        return cls(lock_dir=lock_dir)

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        try:
            shutil.rmtree(self.lock_dir)
        except Exception:
            pass


def resolve_lock_mode(lock_mode: str) -> str:
    """
    解析锁模式：
    - auto: 优先 flock，其次 mkdir
    - none: 不使用锁（不推荐多进程并行）
    - flock: fcntl.flock
    - mkdir: mkdir 原子锁
    """
    mode = (lock_mode or "auto").strip().lower()
    if mode == "auto":
        return "flock" if fcntl is not None else "mkdir"
    if mode in ("none", "flock", "mkdir"):
        return mode
    raise ValueError(f"未知 lock_mode: {lock_mode}")


class MultiProcessLockManager:
    """
    多进程锁管理器：
    - 每个输入文件一个锁（避免两个进程同时 OCR 同一个 PDF）
    - 提供一个全局 cleanup 锁（避免多个进程重复执行全局清理）
    """

    def __init__(self, lock_dir: Path, *, lock_mode: str, logger: logging.Logger):
        self.lock_dir = lock_dir
        self.logger = logger
        self.lock_mode = resolve_lock_mode(lock_mode)
        self.files_dir = self.lock_dir / "files"
        self.runs_dir = self.lock_dir / "runs"
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _key_for_path(path: Path) -> str:
        return hashlib.sha1(str(path).encode("utf-8")).hexdigest()

    def try_acquire_file_lock(self, input_path: Path) -> Optional[HeldLock]:
        key = self._key_for_path(input_path)
        if self.lock_mode == "flock":
            return FlockHeldLock.try_acquire(self.files_dir / f"{key}.lock")
        if self.lock_mode == "mkdir":
            return MkdirHeldLock.try_acquire(self.files_dir / f"{key}.lockdir")
        return None

    def try_acquire_cleanup_lock(self) -> Optional[HeldLock]:
        if self.lock_mode == "flock":
            return FlockHeldLock.try_acquire(self.lock_dir / "cleanup.lock")
        if self.lock_mode == "mkdir":
            return MkdirHeldLock.try_acquire(self.lock_dir / "cleanup.lockdir")
        return None


def filter_files_by_shard(files: List[Path], shard_count: int, shard_index: int) -> List[Path]:
    """
    通过哈希分片，将同一份文件列表分配给不同进程处理。

    典型用法（两个 tmux 窗口）：
    - 窗口 A：--shard-count 2 --shard-index 0
    - 窗口 B：--shard-count 2 --shard-index 1
    """
    if shard_count <= 1:
        return files
    if shard_index < 0 or shard_index >= shard_count:
        raise ValueError(f"shard_index 必须在 [0, {shard_count - 1}]，当前: {shard_index}")

    kept: List[Path] = []
    for path in files:
        digest = hashlib.sha1(str(path).encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % shard_count
        if bucket == shard_index:
            kept.append(path)
    return kept


class RequestTimeoutError(RuntimeError):
    """请求超时错误（不应重试）。"""


class ParseError(RuntimeError):
    """解析错误（允许有限次数重试）。"""


class ServiceUnavailableError(RuntimeError):
    """服务不可用（连接拒绝/服务未启动等）。"""


def _iter_exception_causes(err: BaseException) -> Iterator[BaseException]:
    """
    遍历异常链（__cause__/__context__），用于分类失败原因。
    """
    seen: Set[int] = set()
    cur: Optional[BaseException] = err
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        yield cur
        cur = cur.__cause__ or cur.__context__


def classify_failure_status(err: BaseException) -> str:
    """
    将异常归类为缓存中的失败状态。
    """
    for e in _iter_exception_causes(err):
        if isinstance(e, RequestTimeoutError):
            return "failed_timeout"
        if isinstance(e, ParseError):
            return "failed_parse"
        if isinstance(e, ServiceUnavailableError):
            return "failed_unavailable"
    return "failed_other"


def is_failed_status(status: str) -> bool:
    s = (status or "").strip().lower()
    return s == "failed" or s.startswith("failed_")


_IMG_HTML_LINE = re.compile(r"<img\s+[^>]*>", re.IGNORECASE)
_IMG_HTML_BLOCK = re.compile(
    r'<div[^>]*>\s*<img\s+[^>]*>\s*</div>\s*',
    re.IGNORECASE,
)
_IMG_SRC_IMGS = re.compile(r'src\s*=\s*["\']imgs/[^"\']+["\']', re.IGNORECASE)
_IMG_MD_IMGS = re.compile(r"!\[[^\]]*\]\(\s*imgs/[^)]+\)", re.IGNORECASE)


def strip_images_from_markdown(markdown_text: str) -> str:
    """
    删除 OCR 输出 Markdown 中的图片引用与图片块。

    目标：不保存图片文件时，Markdown 也不应出现 imgs/... 引用。
    """
    if not markdown_text:
        return markdown_text

    text = markdown_text
    text = _IMG_HTML_BLOCK.sub("", text)
    text = _IMG_MD_IMGS.sub("", text)

    kept_lines: List[str] = []
    for line in text.splitlines():
        if _IMG_SRC_IMGS.search(line):
            continue
        if _IMG_HTML_LINE.search(line) and "imgs/" in line:
            continue
        kept_lines.append(line)

    # 清理连续空行（最多保留 2 行）
    cleaned: List[str] = []
    blank_count = 0
    for line in kept_lines:
        if not line.strip():
            blank_count += 1
            if blank_count <= 2:
                cleaned.append("")
            continue
        blank_count = 0
        cleaned.append(line.rstrip())
    return "\n".join(cleaned).strip() + "\n"


def extract_referenced_image_relpaths(markdown_text: str) -> Set[str]:
    """
    从 OCR 输出 Markdown 中抽取引用过的 `imgs/...` 相对路径。

    用于后续“按引用精确清理图片文件”，避免处理过程中扫描/删除整个 imgs 目录引发误删或竞态问题。
    """
    relpaths: Set[str] = set()
    if not markdown_text:
        return relpaths

    # HTML: <img src="imgs/xxx.jpg" .../>
    for match in re.finditer(
        r'src\s*=\s*["\'](imgs/[^"\']+)["\']',
        markdown_text,
        flags=re.IGNORECASE,
    ):
        relpaths.add(match.group(1))

    # Markdown: ![](imgs/xxx.jpg)
    for match in re.finditer(
        r"!\[[^\]]*\]\(\s*(imgs/[^)\s]+)\s*\)",
        markdown_text,
        flags=re.IGNORECASE,
    ):
        relpaths.add(match.group(1))

    return relpaths


def iter_input_files(input_root: Path, extensions: Iterable[str]) -> Iterator[Path]:
    suffixes = {f".{ext.lower().lstrip('.')}" for ext in extensions}
    if input_root.is_file():
        if input_root.suffix.lower() in suffixes:
            yield input_root
        return
    for path in sorted(input_root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() in suffixes:
            yield path


def build_output_md_path(input_path: Path, input_root: Path, output_root: Path) -> Path:
    try:
        relative = input_path.relative_to(input_root)
    except ValueError:
        relative = Path(input_path.name)
    return (output_root / relative).with_suffix(".md")


class PaddleOcrVlRunner:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self._pipeline = None

    def _get_pipeline(self):
        if self._pipeline is not None:
            return self._pipeline
        if PaddleOCRVL is None:
            raise ImportError(
                f"无法导入 paddleocr: {_PADDLEOCR_IMPORT_ERROR}"
            )
        self._pipeline = PaddleOCRVL(
            use_doc_orientation_classify=True,
            use_doc_unwarping=True,
        )
        return self._pipeline

    def ocr_pdf_to_markdown(self, input_file: Path) -> str:
        pipeline = self._get_pipeline()
        output = pipeline.predict(input=str(input_file))

        markdown_list: List[Dict[str, Any]] = []
        for page in output:
            md_info = getattr(page, "markdown", None)
            if md_info:
                markdown_list.append(md_info)

        return pipeline.concatenate_markdown_pages(markdown_list)


def _http_post_json(
    api_url: str,
    payload: Dict[str, Any],
    *,
    timeout_secs: float,
    proxy_mode: str,
) -> Dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        api_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        if proxy_mode == "disable":
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        else:
            # env: 使用环境变量中的 http_proxy/https_proxy/no_proxy
            opener = urllib.request.build_opener()

        with opener.open(request, timeout=timeout_secs) as resp:
            body = resp.read()
            encoding = resp.headers.get_content_charset() or "utf-8"
            try:
                return json.loads(body.decode(encoding))
            except JSONDecodeError as e:
                preview = body[:300].decode("utf-8", errors="replace")
                raise ParseError(f"响应 JSON 解析失败: {e}; preview={preview!r}") from e
    except socket.timeout as e:
        raise RequestTimeoutError(f"请求超时（timeout={timeout_secs}s）") from e
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", errors="replace")
        except Exception:
            detail = ""
        # 500 常见原因：服务端尝试 base64 解码失败/内部解析错误，此类更适合归入 ParseError
        if int(getattr(e, "code", 0) or 0) >= 500 and detail:
            lower = detail.lower()
            if "string argument should contain only ascii characters" in lower or "b64decode" in lower:
                raise ParseError(f"HTTP {e.code}: {detail}".strip()) from e
        raise RuntimeError(f"HTTP {e.code}: {detail}".strip()) from e
    except urllib.error.URLError as e:
        # 常见：<urlopen error timed out>
        reason = getattr(e, "reason", None)
        if isinstance(reason, socket.timeout):
            raise RequestTimeoutError(f"请求超时（timeout={timeout_secs}s）") from e
        # 常见：<urlopen error [Errno 111] Connection refused>
        if isinstance(reason, ConnectionRefusedError):
            raise ServiceUnavailableError(f"连接被拒绝（Connection refused）: {api_url}") from e
        if isinstance(reason, OSError) and getattr(reason, "errno", None) == 111:
            raise ServiceUnavailableError(f"连接被拒绝（Errno 111）: {api_url}") from e
        raise RuntimeError(f"URL 错误: {e}") from e


def resolve_proxy_mode(api_url: str, proxy_mode: str) -> str:
    """
    proxy_mode:
    - auto: 对 localhost/127.0.0.1 默认禁用代理，避免被 http_proxy 干扰
    - disable: 强制禁用代理
    - env: 使用环境代理
    """
    mode = (proxy_mode or "auto").strip().lower()
    if mode in ("disable", "env"):
        return mode

    parsed = urlparse(api_url)
    host = (parsed.hostname or "").lower()
    if host in ("localhost", "127.0.0.1", "::1"):
        return "disable"
    if host.startswith("127."):
        return "disable"
    return "env"


def concatenate_markdown_pages(page_texts: List[str]) -> str:
    parts: List[str] = []
    for page_text in page_texts:
        text = (page_text or "").strip()
        if not text:
            continue
        parts.append(text)
    return ("\n\n".join(parts).strip() + "\n") if parts else ""


class PaddleServerRunner:
    """
    PaddleOCR Serving 客户端（HTTP）。

    线程安全说明：
    - 不复用全局连接/会话；每次请求使用独立 urllib 调用，天然线程安全。
    - 仅共享只读配置。
    """

    def __init__(
        self,
        *,
        api_url: str,
        timeout_secs: float,
        max_retries: int,
        backoff_secs: float,
        file_mode: str,
        proxy_mode: str,
        logger: logging.Logger,
    ):
        self.api_url = api_url
        self.timeout_secs = timeout_secs
        self.max_retries = max_retries
        self.backoff_secs = backoff_secs
        self.file_mode = file_mode
        self.proxy_mode = resolve_proxy_mode(api_url, proxy_mode)
        self.logger = logger

    @staticmethod
    def _looks_like_base64_decode_error(message: str) -> bool:
        msg = (message or "").lower()
        return (
            "string argument should contain only ascii characters" in msg
            or "b64decode" in msg
            or "base64" in msg and "decode" in msg
        )

    def _build_file_field(self, input_file: Path) -> str:
        return self._build_file_field_with_mode(input_file, self.file_mode)

    def _build_file_field_with_mode(self, input_file: Path, mode: str) -> str:
        if mode == "auto":
            # paddlex serving 的实现对 file 字段更偏向 base64/url。
            # auto 模式：默认优先 base64，避免把本地路径误当 base64 导致 500。
            mode = "base64"

        if mode == "path":
            return str(input_file)
        if mode == "base64":
            file_size_mb = input_file.stat().st_size / (1024 * 1024)
            if file_size_mb > 50:
                self.logger.warning(
                    f"base64 模式将上传大文件（{file_size_mb:.1f}MB）：{input_file.name}，"
                    "建议优先使用 --file-mode path（需服务端可访问该路径）"
                )
            data = input_file.read_bytes()
            return base64.b64encode(data).decode("ascii")
        raise ValueError(f"未知 file_mode: {mode}")

    def ocr_pdf_to_markdown(self, input_file: Path) -> str:
        payload: Dict[str, Any] = {
            "file": "",
            "fileType": 0,  # PDF
            "useDocOrientationClassify": True,
            "useDocUnwarping": True,
            "useLayoutDetection": True,
            "useChartRecognition": False,
            "prettifyMarkdown": True,
            "showFormulaNumber": False,
            "visualize": False,  # 不返回 outputImages/inputImage，减少返回体积
        }

        parse_retry_count = 0
        other_retry_count = 0
        max_parse_retries = 2  # 解析错误最多重试 2 次（不含首次）

        last_error: Optional[Exception] = None
        # 如果用户显式使用 path 且服务端报“base64 解码类错误”，则自动切到 base64 再试一次
        auto_switched_to_base64 = False
        while True:
            try:
                if not payload["file"]:
                    payload["file"] = self._build_file_field(input_file)
                data = _http_post_json(
                    self.api_url,
                    payload,
                    timeout_secs=self.timeout_secs,
                    proxy_mode=self.proxy_mode,
                )
                error_code = int(data.get("errorCode", 0) or 0)
                if error_code != 0:
                    error_msg = str(data.get("errorMsg", ""))
                    raise ParseError(f"服务端解析错误: errorCode={error_code}, errorMsg={error_msg}")

                result = data.get("result")
                if not isinstance(result, dict):
                    raise ParseError("响应缺少 result 或类型错误")
                parsing_results = result.get("layoutParsingResults")
                if not isinstance(parsing_results, list):
                    raise ParseError("响应缺少 layoutParsingResults 或类型错误")

                page_texts: List[str] = []
                for item in parsing_results:
                    if not isinstance(item, dict):
                        continue
                    markdown_obj = item.get("markdown")
                    if not isinstance(markdown_obj, dict):
                        continue
                    page_texts.append(str(markdown_obj.get("text", "") or ""))
                return concatenate_markdown_pages(page_texts)

            except RequestTimeoutError as e:
                # 超时不重试：直接失败，由上层写入 failed 缓存
                raise e
            except ServiceUnavailableError as e:
                # 服务不可用：通常表示服务挂了/端口没起来，交给上层做熔断处理
                # 常见误判原因：环境变量 http_proxy 将本地请求走代理，代理端口拒绝连接。
                if self.proxy_mode != "env":
                    self.logger.warning(
                        f"检测到连接被拒绝；当前 proxy_mode={self.proxy_mode}，"
                        "若你依赖代理访问远端服务，请显式加 --proxy-mode env"
                    )
                raise e
            except ParseError as e:
                last_error = e
                # 针对服务端把“本地路径”当 base64 的情况做自愈
                if (
                    not auto_switched_to_base64
                    and self.file_mode in ("path", "auto")
                    and self._looks_like_base64_decode_error(str(e))
                ):
                    auto_switched_to_base64 = True
                    payload["file"] = self._build_file_field_with_mode(input_file, "base64")
                    self.logger.warning(
                        f"检测到服务端疑似按 base64 解码失败，自动切换为 base64 重试: {input_file.name}"
                    )
                    continue

                if parse_retry_count >= max_parse_retries:
                    break
                parse_retry_count += 1
                sleep_secs = min(self.backoff_secs * (2 ** (parse_retry_count - 1)), 60.0)
                self.logger.warning(
                    f"解析错误重试（{parse_retry_count}/{max_parse_retries}）: {input_file.name} -> {e}"
                )
                time.sleep(sleep_secs)
            except Exception as e:
                last_error = e
                if other_retry_count >= self.max_retries:
                    break
                other_retry_count += 1
                sleep_secs = min(self.backoff_secs * (2 ** (other_retry_count - 1)), 60.0)
                self.logger.warning(
                    f"请求失败重试（{other_retry_count}/{self.max_retries}）: {input_file.name} -> {type(e).__name__}: {e}"
                )
                time.sleep(sleep_secs)

        if isinstance(last_error, ParseError):
            raise ParseError(f"解析错误重试耗尽: {last_error}") from last_error
        raise RuntimeError(f"请求失败（已停止重试）: {last_error}") from last_error


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)


def cleanup_referenced_images(referenced: Set[Path], *, logger: logging.Logger) -> None:
    """
    清理 OCR 产出的图片文件（按引用精确删除）。

    说明：
    - 只删除“确实在 OCR 输出 markdown 中引用过”的 `imgs/...` 文件；
    - 在全部任务完成后统一清理，避免未来并行化时出现竞态风险。
    """
    if not referenced:
        return

    removed_files = 0
    touched_dirs: Set[Path] = set()

    for file_path in sorted(referenced):
        touched_dirs.add(file_path.parent)
        if not file_path.exists() or not file_path.is_file():
            continue
        try:
            file_path.unlink()
            removed_files += 1
        except Exception:
            continue

    # 尝试删除空目录（从深到浅）
    try:
        all_dirs: Set[Path] = set(touched_dirs)
        for dir_path in list(touched_dirs):
            parent = dir_path.parent
            while parent != parent.parent:
                all_dirs.add(parent)
                parent = parent.parent

        for dir_path in sorted(all_dirs, reverse=True):
            try:
                dir_path.rmdir()
            except OSError:
                pass
    except OSError:
        pass

    if removed_files:
        logger.info(f"[CLEAN] 已清理 OCR 图片文件: {removed_files} 张")


def cleanup_output_imgs_dirs(output_root: Path, *, logger: logging.Logger) -> None:
    """
    在输出根目录下清理所有 `imgs/` 目录。

    背景：PaddleOCR 的 markdown 默认引用 `imgs/...`，一些实现会把图片输出到同级 `imgs/`。
    本项目不需要保留这些图片，因此在全部处理完成后统一清理，避免竞态风险。
    """
    if not output_root.exists() or not output_root.is_dir():
        return

    removed_files = 0
    removed_dirs = 0
    imgs_dirs = [p for p in output_root.rglob("imgs") if p.is_dir()]
    for imgs_dir in sorted(imgs_dirs):
        for file_path in sorted(imgs_dir.rglob("*")):
            if not file_path.is_file():
                continue
            try:
                file_path.unlink()
                removed_files += 1
            except Exception:
                continue

        # 删除空目录（从深到浅）
        try:
            for dir_path in sorted([p for p in imgs_dir.rglob("*") if p.is_dir()], reverse=True):
                try:
                    dir_path.rmdir()
                except OSError:
                    pass
            imgs_dir.rmdir()
            removed_dirs += 1
        except OSError:
            pass

    if removed_files or removed_dirs:
        logger.info(f"[CLEAN] 已清理输出 imgs 目录: {removed_dirs} 个, 文件: {removed_files} 个")


def process_one(
    runner: Any,
    input_path: Path,
    input_root: Path,
    output_root: Path,
    cache: JsonlCache,
    logger: logging.Logger,
    *,
    skip_existing: bool,
    retry_failed: bool,
    cleanup_targets: Set[Path],
    cache_unavailable: bool,
    service_down_event: Optional[threading.Event],
) -> Tuple[bool, str]:
    output_md = build_output_md_path(input_path, input_root, output_root)
    fingerprint = FileFingerprint.from_path(input_path)
    cached = cache.get(input_path)

    if cached and cached.status == "success" and cached.fingerprint == asdict(fingerprint):
        logger.info(f"[SKIP] 已处理（缓存命中）: {input_path}")
        return True, "cached"

    if cached and is_failed_status(cached.status) and not retry_failed:
        logger.info(f"[SKIP] 上次失败（未开启重试）: {input_path}")
        return True, "failed_cached_skip"

    if skip_existing and output_md.exists() and output_md.stat().st_size > 0:
        logger.info(f"[SKIP] 输出已存在: {output_md}")
        cache.upsert(CacheRecord(
            input_path=str(input_path),
            output_md=str(output_md),
            status="success",
            fingerprint=asdict(fingerprint),
            updated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            message="skip_existing_output_present",
        ))
        return True, "output_exists"

    logger.info(f"[RUN ] OCR: {input_path}")
    started_at = time.time()
    try:
        raw_markdown = runner.ocr_pdf_to_markdown(input_path)
        referenced = extract_referenced_image_relpaths(raw_markdown)
        cleaned_markdown = strip_images_from_markdown(raw_markdown)
        atomic_write_text(output_md, cleaned_markdown)

        # 记录需要清理的图片文件（仅限同目录 imgs/ 下）
        for relpath in referenced:
            if not relpath.startswith("imgs/"):
                continue
            rel = Path(relpath)
            if rel.is_absolute() or ".." in rel.parts:
                continue
            cleanup_targets.add(output_md.parent / rel)

        duration = time.time() - started_at
        logger.info(f"[OK  ] 输出: {output_md} ({duration:.1f}s)")
        cache.upsert(CacheRecord(
            input_path=str(input_path),
            output_md=str(output_md),
            status="success",
            fingerprint=asdict(fingerprint),
            updated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            message=f"ok:{duration:.1f}s",
        ))
        return True, "success"
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        failed_status = classify_failure_status(e)
        logger.error(f"[FAIL] {input_path} -> {err}")
        logger.debug(traceback.format_exc())

        # 服务不可用：默认不写缓存，避免把大量文档“误标失败”污染缓存
        if failed_status == "failed_unavailable":
            if service_down_event is not None:
                service_down_event.set()
            if not cache_unavailable:
                logger.warning(
                    "[SKIP-CACHE] 服务不可用导致失败，默认不写入缓存；"
                    "如需记录请加 --cache-unavailable"
                )
                return False, "failed_unavailable"

        cache.upsert(CacheRecord(
            input_path=str(input_path),
            output_md=str(output_md),
            status=failed_status,
            fingerprint=asdict(fingerprint),
            updated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            message=err,
        ))
        return False, "failed"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="paddle_ocr_batch",
        description="批量处理 PDF OCR（PaddleOCRVL），输出 Markdown（去除图片引用）",
    )
    parser.add_argument(
        "--input-root",
        default=str(DEFAULT_INPUT_ROOT),
        help="输入目录（递归扫描 PDF）或单个 PDF 文件路径",
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
        help="输出目录（保持相对目录结构，输出同名 .md）",
    )
    parser.add_argument(
        "--ext",
        nargs="+",
        default=["pdf"],
        help="要处理的扩展名列表（默认: pdf）",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="最多处理文件数（用于测试）",
    )
    parser.add_argument(
        "--sort-by-size",
        choices=["none", "asc", "desc"],
        default="none",
        help="按文件大小排序处理顺序：none=不排序；asc=小文件优先；desc=大文件优先（默认 none）",
    )
    parser.add_argument(
        "--max-size-mb",
        type=float,
        default=None,
        help="仅处理不超过该大小的文件（单位 MB，默认不限）",
    )
    parser.add_argument(
        "--min-size-mb",
        type=float,
        default=None,
        help="仅处理不小于该大小的文件（单位 MB，默认不限）",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="若输出 md 已存在则跳过（并写入缓存），默认不跳过",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="重试缓存中标记为 failed 的文件",
    )
    parser.add_argument(
        "--cache-file",
        default=str(DEFAULT_CACHE_FILE),
        help="缓存文件路径（JSONL），用于断点续跑",
    )
    parser.add_argument(
        "--log-dir",
        default=str(DEFAULT_LOG_DIR),
        help="日志目录（默认: logs/ocr）",
    )
    parser.add_argument(
        "--lock-dir",
        default="",
        help="多进程锁目录（默认: <log-dir>/locks；两个 tmux 进程需保持一致）",
    )
    parser.add_argument(
        "--lock-mode",
        choices=["auto", "none", "flock", "mkdir"],
        default="auto",
        help="多进程锁模式：auto=优先 flock；none=不加锁；flock=文件锁；mkdir=目录锁（默认 auto）",
    )
    parser.add_argument(
        "--shard-count",
        type=int,
        default=1,
        help="分片总数（用于多进程协作；默认 1=不分片）",
    )
    parser.add_argument(
        "--shard-index",
        type=int,
        default=0,
        help="当前分片编号（0-based；需满足 0 <= shard_index < shard_count）",
    )
    parser.add_argument(
        "--cleanup-images",
        choices=["auto", "always", "never"],
        default="auto",
        help="清理输出中的 imgs 目录：auto=仅最后一个进程清理；always=总是清理；never=不清理（默认 auto）",
    )
    parser.add_argument(
        "--cleanup-only",
        action="store_true",
        help="只执行清理（删除 output_root 下所有 imgs/），不进行 OCR",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只列出将处理的文件，不实际 OCR",
    )
    parser.add_argument(
        "--runner",
        choices=["server", "local"],
        default="server",
        help="OCR 执行方式：server=调用 Paddle 服务端；local=本地 PaddleOCRVL（默认: server）",
    )
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help=f"Paddle 服务端 URL（默认: {DEFAULT_API_URL}）",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=2,
        help="并发线程数（请求服务端时建议 1~4，默认 2）",
    )
    parser.add_argument(
        "--timeout-secs",
        type=float,
        default=3600.0,
        help="单次请求超时秒数（默认 3600）",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="失败重试次数（默认 2）",
    )
    parser.add_argument(
        "--retry-backoff-secs",
        type=float,
        default=2.0,
        help="重试退避初始秒数（默认 2.0）",
    )
    parser.add_argument(
        "--file-mode",
        choices=["auto", "path", "base64"],
        default="auto",
        help="传给服务端的 file 字段：auto=优先 base64；path=本机可访问路径；base64=上传内容（默认 auto）",
    )
    parser.add_argument(
        "--proxy-mode",
        choices=["auto", "disable", "env"],
        default="auto",
        help="HTTP 代理处理：auto=localhost 禁用代理；disable=总是禁用；env=使用环境变量代理（默认 auto）",
    )
    parser.add_argument(
        "--cache-unavailable",
        action="store_true",
        help="服务不可用（Connection refused 等）时也写入缓存为 failed_unavailable（默认不写入）",
    )
    parser.add_argument(
        "--no-stop-on-unavailable",
        action="store_true",
        help="检测到服务不可用时不熔断，继续处理其他文件（不推荐）",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="输出 debug 日志",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    log_dir = Path(args.log_dir).expanduser().resolve()
    logger = setup_logger(log_dir, verbose=bool(args.verbose))
    user_provided_workers = "--workers" in sys.argv

    lock_dir = Path(args.lock_dir).expanduser()
    if not str(args.lock_dir).strip():
        lock_dir = log_dir / "locks"
    lock_dir = lock_dir.resolve()

    lock_manager = MultiProcessLockManager(
        lock_dir,
        lock_mode=str(args.lock_mode),
        logger=logger,
    )
    run_marker = RunMarker(lock_manager.runs_dir, logger=logger)
    run_marker.start()

    input_root = Path(args.input_root).expanduser().resolve()
    output_root = Path(args.output_root).expanduser().resolve()
    cache = JsonlCache(Path(args.cache_file).expanduser().resolve(), logger=logger)

    try:
        logger.info(f"锁目录: {lock_dir}")
        logger.info(f"锁模式: {lock_manager.lock_mode}")

        if bool(args.cleanup_only):
            other_pids = RunMarker.list_other_active_pids(
                lock_manager.runs_dir,
                current_pid=os.getpid(),
                logger=logger,
            )
            if other_pids:
                logger.error(
                    f"检测到其他 OCR 进程仍在运行（pid={sorted(other_pids)}），为避免竞态，本次清理已取消。"
                )
                return 2

            cleanup_lock_obj: Optional[HeldLock] = None
            try:
                cleanup_lock_obj = lock_manager.try_acquire_cleanup_lock()
            except Exception as e:
                logger.warning(f"获取清理锁失败，将直接清理: {type(e).__name__}: {e}")
            if cleanup_lock_obj is not None:
                with cleanup_lock_obj:
                    cleanup_output_imgs_dirs(output_root, logger=logger)
            else:
                cleanup_output_imgs_dirs(output_root, logger=logger)
            logger.info("[CLEAN] cleanup-only 完成")
            return 0

        if not input_root.exists():
            logger.error(f"输入路径不存在: {input_root}")
            return 1

        output_root.mkdir(parents=True, exist_ok=True)

        files = list(iter_input_files(input_root, args.ext))
        filtered_by_size = 0
        if args.max_size_mb is not None or args.min_size_mb is not None:
            max_bytes = int(args.max_size_mb * 1024 * 1024) if args.max_size_mb is not None else None
            min_bytes = int(args.min_size_mb * 1024 * 1024) if args.min_size_mb is not None else None
            kept: List[Path] = []
            for path in files:
                try:
                    size = int(path.stat().st_size)
                except Exception:
                    kept.append(path)
                    continue
                if max_bytes is not None and size > max_bytes:
                    filtered_by_size += 1
                    continue
                if min_bytes is not None and size < min_bytes:
                    filtered_by_size += 1
                    continue
                kept.append(path)
            files = kept

        if args.sort_by_size != "none":
            decorated: List[Tuple[int, Path]] = []
            for path in files:
                try:
                    size = int(path.stat().st_size)
                except Exception:
                    size = 0
                decorated.append((size, path))
            reverse = args.sort_by_size == "desc"
            decorated.sort(key=lambda x: x[0], reverse=reverse)
            files = [p for _, p in decorated]

        try:
            files = filter_files_by_shard(files, int(args.shard_count), int(args.shard_index))
        except ValueError as e:
            logger.error(str(e))
            return 1

        if args.max_files:
            files = files[: args.max_files]

        logger.info(f"输入: {input_root}")
        logger.info(f"输出: {output_root}")
        if filtered_by_size:
            logger.info(f"按大小过滤跳过文件数: {filtered_by_size}")
        if args.sort_by_size != "none":
            logger.info(f"按文件大小排序: {args.sort_by_size}")
        if int(args.shard_count) > 1:
            logger.info(f"分片: shard_index={int(args.shard_index)}, shard_count={int(args.shard_count)}")
        if int(args.shard_count) > 1 and lock_manager.lock_mode == "none":
            logger.warning("已启用分片但未启用锁（--lock-mode none）；请确保 shard 参数正确以避免重复处理。")
        logger.info(f"待处理文件数: {len(files)}")

        if args.dry_run:
            for idx, path in enumerate(files, start=1):
                logger.info(f"[DRY] {idx:4d}. {path}")
            return 0

        if args.runner == "local":
            runner: Any = PaddleOcrVlRunner(logger=logger)
            if int(args.workers) != 1 and user_provided_workers:
                logger.warning("local 模式下 PaddleOCRVL 非线程安全，已强制 --workers=1")
        else:
            runner = PaddleServerRunner(
                api_url=str(args.api_url),
                timeout_secs=float(args.timeout_secs),
                max_retries=int(args.retries),
                backoff_secs=float(args.retry_backoff_secs),
                file_mode=str(args.file_mode),
                proxy_mode=str(args.proxy_mode),
                logger=logger,
            )

        cleanup_targets: Set[Path] = set()
        cleanup_lock = threading.Lock()
        service_down_event = threading.Event()
        stop_event = threading.Event()

        ok_count = 0
        fail_count = 0

        def _task(input_path: Path) -> Tuple[bool, str]:
            if stop_event.is_set():
                return False, "stopped"
            if args.runner == "server" and service_down_event.is_set() and not bool(args.no_stop_on_unavailable):
                return False, "service_unavailable_skip"

            held_lock: Optional[HeldLock] = None
            if lock_manager.lock_mode != "none":
                try:
                    held_lock = lock_manager.try_acquire_file_lock(input_path)
                except Exception as e:
                    logger.error(f"[FAIL] 获取文件锁失败: {input_path} -> {type(e).__name__}: {e}")
                    logger.debug(traceback.format_exc())
                    return False, "lock_error"
                if held_lock is None:
                    logger.info(f"[SKIP] 文件正在被其他进程处理: {input_path}")
                    return True, "locked"

            try:
                local_cleanup: Set[Path] = set()
                ok, status = process_one(
                    runner=runner,
                    input_path=input_path,
                    input_root=input_root if input_root.is_dir() else input_root.parent,
                    output_root=output_root,
                    cache=cache,
                    logger=logger,
                    skip_existing=bool(args.skip_existing),
                    retry_failed=bool(args.retry_failed),
                    cleanup_targets=local_cleanup,
                    cache_unavailable=bool(args.cache_unavailable),
                    service_down_event=service_down_event if args.runner == "server" else None,
                )
            finally:
                if held_lock is not None:
                    held_lock.release()

            if local_cleanup:
                with cleanup_lock:
                    cleanup_targets.update(local_cleanup)
            return ok, status

        max_workers = 1 if args.runner == "local" else max(1, int(args.workers))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            pending: Set[Future] = set()
            file_iter = iter(files)

            def submit_one() -> bool:
                if args.runner == "server" and service_down_event.is_set() and not bool(args.no_stop_on_unavailable):
                    return False
                try:
                    next_path = next(file_iter)
                except StopIteration:
                    return False
                pending.add(executor.submit(_task, next_path))
                return True

            for _ in range(min(max_workers, len(files))):
                submit_one()

            done_count = 0
            try:
                while pending:
                    if args.runner == "server" and service_down_event.is_set() and not bool(args.no_stop_on_unavailable):
                        logger.error(
                            "检测到服务不可用（Connection refused 等），已触发熔断：停止提交并取消剩余任务。"
                        )
                        for fut in pending:
                            fut.cancel()
                        break

                    done, pending = wait(pending, timeout=1.0, return_when=FIRST_COMPLETED)
                    for fut in done:
                        done_count += 1
                        try:
                            ok, _ = fut.result()
                        except Exception as e:
                            logger.error(f"[FAIL] 任务异常: {type(e).__name__}: {e}")
                            ok = False
                        logger.info(f"完成进度: [{done_count}/{len(files)}]")
                        if ok:
                            ok_count += 1
                        else:
                            fail_count += 1

                        while len(pending) < max_workers and submit_one():
                            pass
            except KeyboardInterrupt:
                stop_event.set()
                logger.warning("收到 Ctrl+C，正在取消未完成任务并退出（服务端可能仍会继续处理已提交请求）。")
                for fut in pending:
                    fut.cancel()

        # 先移除运行标记，再决定是否清理（避免并发时两个进程都“看见对方”从而都跳过清理）
        run_marker.stop()

        cleanup_mode = str(args.cleanup_images or "auto").strip().lower()
        if cleanup_mode == "never":
            logger.info("[CLEAN] 已禁用自动清理（--cleanup-images never）")
        else:
            other_pids = RunMarker.list_other_active_pids(
                lock_manager.runs_dir,
                current_pid=os.getpid(),
                logger=logger,
            )
            if cleanup_mode == "auto" and other_pids:
                logger.info(
                    f"[CLEAN] 检测到其他 OCR 进程仍在运行（pid={sorted(other_pids)}），跳过清理；"
                    "可在全部结束后运行: python tools/paddle_ocr.py --cleanup-only"
                )
            else:
                cleanup_lock_obj = None
                try:
                    cleanup_lock_obj = lock_manager.try_acquire_cleanup_lock()
                except Exception as e:
                    logger.warning(f"获取清理锁失败，将直接清理: {type(e).__name__}: {e}")
                if cleanup_lock_obj is None and lock_manager.lock_mode != "none":
                    logger.info("[CLEAN] 另一个进程正在执行清理，本进程跳过")
                else:
                    if cleanup_lock_obj is not None:
                        with cleanup_lock_obj:
                            cleanup_referenced_images(cleanup_targets, logger=logger)
                            cleanup_output_imgs_dirs(output_root, logger=logger)
                    else:
                        cleanup_referenced_images(cleanup_targets, logger=logger)
                        cleanup_output_imgs_dirs(output_root, logger=logger)

        logger.info(f"完成: success_or_skipped={ok_count}, failed={fail_count}")
        return 0 if fail_count == 0 else 2
    finally:
        run_marker.stop()


if __name__ == "__main__":
    raise SystemExit(main())
