"""
P4语料批量清洗工具 v2.0
优化：智能去噪、语义切分、多引擎支持、并行处理
新增：可选元数据提取（source_type/year/title/url/province/river），可拼接到文件名，便于溯源。
"""
from __future__ import annotations

import argparse
import re
import json
from pathlib import Path
from typing import Iterable, List, Tuple, Optional, Dict
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib


@dataclass
class DocumentMeta:
    """文档元数据，便于溯源"""
    source_file: str
    part_index: int
    total_parts: int
    char_count: int
    md5_hash: str  # 用于去重
    source_type: str = ""
    year: str = ""
    title: str = ""
    url: str = ""
    province: str = ""
    river: str = ""


# ==================== PDF解析引擎 ====================

def extract_with_pypdf2(path: Path) -> str:
    """PyPDF2 引擎（速度快，但表格效果一般）"""
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        raise ImportError("请安装 PyPDF2: pip install PyPDF2")

    reader = PdfReader(str(path))
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        # 标记页码便于后续去页眉页脚
        pages.append(f"[PAGE_{i+1}_START]\n{text}\n[PAGE_{i+1}_END]")
    return "\n".join(pages)


def extract_with_pdfplumber(path: Path) -> str:
    """pdfplumber 引擎（表格识别更好）"""
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("请安装 pdfplumber: pip install pdfplumber")

    pages = []
    with pdfplumber.open(str(path)) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            # 尝试提取表格
            tables = page.extract_tables()
            table_text = ""
            for table in tables:
                if table:
                    rows = [" | ".join(
                        str(cell) if cell else "" for cell in row) for row in table]
                    table_text += "\n[TABLE]\n" + \
                        "\n".join(rows) + "\n[/TABLE]\n"
            pages.append(
                f"[PAGE_{i+1}_START]\n{text}\n{table_text}[PAGE_{i+1}_END]")
    return "\n".join(pages)


def extract_text_from_pdf(path: Path, engine: str = "auto") -> str:
    """
    PDF文本提取，支持多引擎
    engine: "pypdf2", "pdfplumber", "auto"(自动选择)
    """
    if engine == "auto":
        # 优先尝试 pdfplumber（效果更好），失败则回退到 pypdf2
        try:
            return extract_with_pdfplumber(path)
        except ImportError:
            return extract_with_pypdf2(path)
    elif engine == "pdfplumber":
        return extract_with_pdfplumber(path)
    else:
        return extract_with_pypdf2(path)


def extract_text_from_txt(path: Path) -> str:
    """读取txt文件，自动检测编码"""
    encodings = ["utf-8", "gbk", "gb2312", "utf-16"]
    for enc in encodings:
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    # 最后尝试忽略错误
    return path.read_text(encoding="utf-8", errors="ignore")


def extract_text(path: Path, pdf_engine: str = "auto") -> str:
    """统一入口"""
    ext = path.suffix.lower()
    if ext == ".pdf":
        return extract_text_from_pdf(path, engine=pdf_engine)
    if ext == ".txt":
        return extract_text_from_txt(path)
    if ext == ".caj":
        raise NotImplementedError(f"CAJ不支持直接解析: {path}，请用CAJViewer转PDF")
    if ext in (".doc", ".docx"):
        raise NotImplementedError(f"Word文档请先转PDF: {path}")
    raise ValueError(f"不支持的文件类型: {ext}")


# ==================== 智能清洗 ====================

class TextCleaner:
    """文本清洗器：去噪、规范化"""

    # 页眉页脚的典型模式
    HEADER_FOOTER_PATTERNS = [
        r"第\s*\d+\s*页\s*[/／共]\s*\d+\s*页",  # 第1页/共10页
        r"[-—]\s*\d+\s*[-—]",  # - 1 - 或 — 1 —
        r"^\d+$",  # 单独的页码
        r"^[①②③④⑤⑥⑦⑧⑨⑩]+$",  # 圆圈数字
        r"^\s*·\s*\d+\s*·\s*$",  # ·1·
    ]

    # 目录行模式
    TOC_PATTERNS = [
        r"^[\d一二三四五六七八九十]+[、.．]\s*.{2,30}\s*[\.…·]+\s*\d+\s*$",  # 目录条目
        r"^目\s*录\s*$",
        r"^CONTENTS?\s*$",
    ]

    # 参考文献模式
    REFERENCE_START = [
        r"^参\s*考\s*文\s*献\s*$",
        r"^References?\s*$",
        r"^REFERENCES?\s*$",
        r"^引用文献\s*$",
    ]

    # 需要删除的噪声模式
    NOISE_PATTERNS = [
        r"\[PAGE_\d+_(START|END)\]",  # 页面标记
        r"^\s*www\.[^\s]+\s*$",  # 网址行
        r"^\s*http[s]?://[^\s]+\s*$",
        r"版权所有.*?翻印必究",
        r"本刊编辑部",
        r"收稿日期[:：]\s*\d{4}[-/]\d{1,2}[-/]\d{1,2}",
        r"基金项目[:：].{10,100}",  # 基金信息（可选保留）
        r"作者简介[:：].{10,200}",
    ]

    def __init__(self,
                 remove_headers: bool = True,
                 remove_toc: bool = True,
                 remove_references: bool = False,  # 参考文献默认保留
                 remove_noise: bool = True):
        self.remove_headers = remove_headers
        self.remove_toc = remove_toc
        self.remove_references = remove_references
        self.remove_noise = remove_noise

    def clean(self, text: str) -> str:
        """执行清洗流程"""
        # 1. 基础规范化
        text = self._normalize(text)

        # 2. 去除页眉页脚
        if self.remove_headers:
            text = self._remove_headers_footers(text)

        # 3. 去除目录
        if self.remove_toc:
            text = self._remove_toc(text)

        # 4. 去除参考文献（可选）
        if self.remove_references:
            text = self._remove_references(text)

        # 5. 去除其他噪声
        if self.remove_noise:
            text = self._remove_noise(text)

        # 6. 最终规范化
        text = self._final_normalize(text)

        return text

    def _normalize(self, text: str) -> str:
        """基础规范化"""
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # 全角转半角（数字和部分标点）
        text = self._fullwidth_to_halfwidth(text)
        return text

    def _fullwidth_to_halfwidth(self, text: str) -> str:
        """全角字符转半角"""
        result = []
        for char in text:
            code = ord(char)
            # 全角数字和字母转半角
            if 0xFF01 <= code <= 0xFF5E:
                result.append(chr(code - 0xFEE0))
            # 全角空格
            elif code == 0x3000:
                result.append(' ')
            else:
                result.append(char)
        return ''.join(result)

    def _remove_headers_footers(self, text: str) -> str:
        """去除页眉页脚"""
        lines = text.split("\n")
        cleaned = []
        for line in lines:
            is_header_footer = False
            for pattern in self.HEADER_FOOTER_PATTERNS:
                if re.match(pattern, line.strip()):
                    is_header_footer = True
                    break
            if not is_header_footer:
                cleaned.append(line)
        return "\n".join(cleaned)

    def _remove_toc(self, text: str) -> str:
        """去除目录部分"""
        lines = text.split("\n")
        cleaned = []
        in_toc = False
        toc_line_count = 0

        for line in lines:
            # 检测目录开始
            for pattern in self.TOC_PATTERNS[:2]:  # "目录" 标题
                if re.match(pattern, line.strip(), re.IGNORECASE):
                    in_toc = True
                    toc_line_count = 0
                    break

            if in_toc:
                toc_line_count += 1
                # 目录行检测
                is_toc_entry = False
                for pattern in self.TOC_PATTERNS:
                    if re.match(pattern, line.strip()):
                        is_toc_entry = True
                        break

                # 超过30行非目录内容，认为目录结束
                if not is_toc_entry and line.strip() and len(line.strip()) > 50:
                    in_toc = False
                    cleaned.append(line)
                # 最多跳过100行目录
                elif toc_line_count > 100:
                    in_toc = False
            else:
                cleaned.append(line)

        return "\n".join(cleaned)

    def _remove_references(self, text: str) -> str:
        """去除参考文献部分"""
        for pattern in self.REFERENCE_START:
            match = re.search(pattern, text, re.MULTILINE)
            if match:
                # 找到参考文献开始位置，截断
                text = text[:match.start()]
                break
        return text

    def _remove_noise(self, text: str) -> str:
        """去除各种噪声"""
        for pattern in self.NOISE_PATTERNS:
            text = re.sub(pattern, "", text, flags=re.MULTILINE)
        return text

    def _final_normalize(self, text: str) -> str:
        """最终规范化"""
        # 压缩连续空白
        text = re.sub(r"[ \t]+", " ", text)
        # 压缩连续空行（保留最多2个换行）
        text = re.sub(r"\n{3,}", "\n\n", text)
        # 去除行首行尾空白
        lines = [line.strip() for line in text.split("\n")]
        text = "\n".join(lines)
        return text.strip()


# ==================== 智能切分 ====================

class SmartSplitter:
    """
    智能切分器：
    1. 优先按章节标题切分
    2. 其次按段落切分
    3. 最后按字符数硬切
    """

    # 章节标题模式（中文学术文献常见格式）
    SECTION_PATTERNS = [
        r"^第[一二三四五六七八九十\d]+[章节部分]\s*.+",  # 第一章 xxx
        r"^[一二三四五六七八九十]+[、.．]\s*.{2,30}$",  # 一、xxx
        r"^\d+[、.．]\s*.{2,30}$",  # 1、xxx 或 1. xxx
        r"^\d+\.\d+\s+.{2,30}$",  # 1.1 xxx
        r"^[（(][一二三四五六七八九十\d]+[)）]\s*.+",  # （一）xxx
        r"^摘\s*要\s*$",
        r"^Abstract\s*$",
        r"^引\s*言\s*$",
        r"^前\s*言\s*$",
        r"^结\s*论\s*$",
        r"^结语\s*$",
        r"^致\s*谢\s*$",
    ]

    def __init__(self, min_chars: int = 800, max_chars: int = 2500,
                 prefer_section: bool = True):
        self.min_chars = min_chars
        self.max_chars = max_chars
        self.prefer_section = prefer_section

    def split(self, text: str) -> List[str]:
        """执行切分"""
        if self.prefer_section:
            # 先尝试按章节切分
            sections = self._split_by_sections(text)
            if len(sections) > 1:
                # 对每个章节再按长度控制
                parts = []
                for section in sections:
                    parts.extend(self._split_by_length(section))
                return self._merge_short_parts(parts)

        # 按段落和长度切分
        parts = self._split_by_paragraphs(text)
        return self._merge_short_parts(parts)

    def _split_by_sections(self, text: str) -> List[str]:
        """按章节标题切分"""
        lines = text.split("\n")
        sections = []
        current_section = []

        for line in lines:
            is_section_header = False
            for pattern in self.SECTION_PATTERNS:
                if re.match(pattern, line.strip()):
                    is_section_header = True
                    break

            if is_section_header and current_section:
                sections.append("\n".join(current_section))
                current_section = [line]
            else:
                current_section.append(line)

        if current_section:
            sections.append("\n".join(current_section))

        return sections

    def _split_by_paragraphs(self, text: str) -> List[str]:
        """按段落切分"""
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        return self._merge_paragraphs(paragraphs)

    def _merge_paragraphs(self, paragraphs: List[str]) -> List[str]:
        """合并段落，控制长度"""
        parts = []
        buffer = []
        buffer_len = 0

        for para in paragraphs:
            para_len = len(para)

            # 单个段落超长，硬切
            if para_len > self.max_chars:
                if buffer:
                    parts.append("\n\n".join(buffer))
                    buffer = []
                    buffer_len = 0
                # 硬切超长段落
                for i in range(0, para_len, self.max_chars):
                    parts.append(para[i:i + self.max_chars])
                continue

            # 加入当前段落后是否超长
            if buffer_len + para_len + 2 > self.max_chars:
                if buffer_len >= self.min_chars:
                    parts.append("\n\n".join(buffer))
                    buffer = [para]
                    buffer_len = para_len
                else:
                    # 缓冲太短，继续累加
                    buffer.append(para)
                    buffer_len += para_len + 2
            else:
                buffer.append(para)
                buffer_len += para_len + 2

        if buffer:
            parts.append("\n\n".join(buffer))

        return parts

    def _split_by_length(self, text: str) -> List[str]:
        """按长度切分（用于章节内部）"""
        if len(text) <= self.max_chars:
            return [text]
        return self._split_by_paragraphs(text)

    def _merge_short_parts(self, parts: List[str]) -> List[str]:
        """合并过短的片段"""
        if len(parts) <= 1:
            return parts

        merged = []
        i = 0
        while i < len(parts):
            current = parts[i]
            # 如果当前部分过短，尝试与下一部分合并
            while len(current) < self.min_chars and i + 1 < len(parts):
                i += 1
                current = current + "\n\n" + parts[i]
            merged.append(current.strip())
            i += 1

        # 最后一个如果太短，与前一个合并
        if len(merged) >= 2 and len(merged[-1]) < self.min_chars // 2:
            merged[-2] = merged[-2] + "\n\n" + merged[-1]
            merged.pop()

        return merged


# ==================== 输出管理 ====================

def compute_md5(text: str) -> str:
    """计算文本MD5，用于去重"""
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]


PROVINCES = [
    "北京", "天津", "上海", "重庆", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江",
    "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南", "广东",
    "广西", "海南", "四川", "贵州", "云南", "西藏", "陕西", "甘肃", "青海", "宁夏", "新疆",
    "香港", "澳门", "台湾"
]

RIVERS = [
    "长江", "汉江", "嘉陵江", "乌江", "洞庭湖", "鄱阳湖", "太湖", "三峡", "金沙江", "岷江",
    "湘江", "赣江", "黄河"
]


def extract_meta_from_name(stem: str, default_source: str = "", default_url: str = "") -> Dict[str, str]:
    """
    依据文件名粗略提取元数据：year/province/river/title。
    - year：优先匹配 19xx/20xx
    - province/river：简单包含匹配
    """
    year_match = re.search(r"(19|20)\d{2}", stem)
    year = year_match.group(0) if year_match else ""
    province = next((p for p in PROVINCES if p in stem), "")
    river = next((r for r in RIVERS if r in stem), "")
    title = stem
    return {
        "source_type": default_source,
        "year": year,
        "title": title,
        "url": default_url,
        "province": province,
        "river": river,
    }


def build_name_with_meta(stem: str, meta: Dict[str, str]) -> str:
    """
    将元数据拼到文件名中，格式：stem__src-...__year-...__prov-...__river-...
    只拼接非空字段，避免过长。
    """
    parts = [stem]
    for key in ["source_type", "year", "province", "river"]:
        val = meta.get(key, "")
        if val:
            safe_val = re.sub(r"[\\/:*?\"<>|\\s]+", "_", val)
            parts.append(f"{key}-{safe_val}")
    return "__".join(parts)


def write_parts(parts: List[str], out_dir: Path, stem: str,
                source_file: str, rel_dir: Optional[Path] = None,
                meta_extra: Optional[Dict[str, str]] = None) -> List[Tuple[Path, DocumentMeta]]:
    """
    写入切分后的文件，附带元数据。
    rel_dir 用于保留相对目录结构，例如年鉴/2019/xxx.txt -> output/年鉴/2019/xxx_part01.txt
    meta_extra：附加的源/年份/省份等元数据。
    """
    target_dir = out_dir / rel_dir if rel_dir else out_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    written = []
    total = len(parts)
    meta_extra = meta_extra or {}

    for idx, chunk in enumerate(parts, start=1):
        # 生成元数据
        meta = DocumentMeta(
            source_file=source_file,
            part_index=idx,
            total_parts=total,
            char_count=len(chunk),
            md5_hash=compute_md5(chunk),
            source_type=meta_extra.get("source_type", ""),
            year=meta_extra.get("year", ""),
            title=meta_extra.get("title", ""),
            url=meta_extra.get("url", ""),
            province=meta_extra.get("province", ""),
            river=meta_extra.get("river", ""),
        )

        name_base = build_name_with_meta(f"{stem}_part{idx:02d}", meta_extra)

        # 写入文本
        out_path = target_dir / f"{name_base}.txt"
        out_path.write_text(chunk, encoding="utf-8")

        # 写入元数据（JSON sidecar）
        meta_path = target_dir / f"{name_base}.meta.json"
        meta_path.write_text(json.dumps(asdict(meta), ensure_ascii=False, indent=2),
                             encoding="utf-8")

        written.append((out_path, meta))

    return written


# ==================== 主处理流程 ====================

def process_file(path: Path, out_dir: Path,
                 cleaner: TextCleaner, splitter: SmartSplitter,
                 pdf_engine: str = "auto", rel_dir: Optional[Path] = None,
                 meta_extra: Optional[Dict[str, str]] = None) -> List[Tuple[Path, DocumentMeta]]:
    """处理单个文件"""
    # 1. 提取文本
    raw_text = extract_text(path, pdf_engine=pdf_engine)

    # 2. 清洗
    clean_text = cleaner.clean(raw_text)

    # 3. 检查有效内容
    if len(clean_text) < 100:
        raise ValueError(f"清洗后文本过短（{len(clean_text)}字符），可能是扫描版PDF")

    # 4. 切分
    parts = splitter.split(clean_text)

    # 5. 写入
    return write_parts(parts, out_dir, path.stem, str(path.name), rel_dir=rel_dir, meta_extra=meta_extra)


def iter_input_files(src: Path) -> Iterable[Path]:
    """
    遍历输入文件（递归子目录），避免重复。
    支持 pdf/txt/caj（caj 需手工转换提示）。
    """
    if src.is_file():
        yield src
        return

    seen = set()
    patterns = ("*.pdf", "*.PDF", "*.txt", "*.TXT", "*.caj", "*.CAJ",
                "**/*.pdf", "**/*.PDF", "**/*.txt", "**/*.TXT", "**/*.caj", "**/*.CAJ")
    for ext in patterns:
        for p in src.glob(ext):
            if p.is_file() and p not in seen:
                seen.add(p)
                yield p


def process_batch(files: List[Path], out_dir: Path,
                  cleaner: TextCleaner, splitter: SmartSplitter,
                  pdf_engine: str = "auto", max_workers: int = 4,
                  src_root: Optional[Path] = None,
                  meta_defaults: Optional[Dict[str, str]] = None) -> Dict:
    """批量处理（支持并行）"""
    results = {
        "success": [],
        "skipped": [],
        "failed": [],
        "total_parts": 0
    }

    def process_one(f: Path, root: Path, meta_defaults: Dict[str, str]):
        try:
            try:
                rel_dir = f.parent.relative_to(root)
            except ValueError:
                rel_dir = None
            meta_extra = extract_meta_from_name(f.stem, default_source=meta_defaults.get("source_type", ""),
                                                default_url=meta_defaults.get("url", ""))
            written = process_file(f, out_dir, cleaner, splitter,
                                   pdf_engine, rel_dir=rel_dir, meta_extra=meta_extra)
            return ("success", f, written)
        except NotImplementedError as e:
            return ("skipped", f, str(e))
        except Exception as e:
            return ("failed", f, str(e))

    # 使用线程池并行处理
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        root = src_root or src
        futures = {executor.submit(
            process_one, f, root, meta_defaults or {}): f for f in files}
        for future in as_completed(futures):
            status, path, data = future.result()
            if status == "success":
                results["success"].append((path, len(data)))
                results["total_parts"] += len(data)
                print(f"[OK] {path.name}: {len(data)} 份")
            elif status == "skipped":
                results["skipped"].append((path, data))
                print(f"[SKIP] {path.name}: {data}")
            else:
                results["failed"].append((path, data))
                print(f"[ERROR] {path.name}: {data}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="P4语料批量清洗工具 v2.0 - 智能去噪、语义切分",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python corpus_cleaner.py --input ./pdfs/ --output-dir ./corpus/
  python corpus_cleaner.py --input paper.pdf --min-chars 1000 --max-chars 3000
  python corpus_cleaner.py --input ./docs/ --remove-references --pdf-engine pdfplumber
        """)

    parser.add_argument("--input", required=True,
                        help="输入文件或目录（支持pdf/txt）")
    parser.add_argument("--output-dir", default="data/enhancing_onto_corpus_docs",
                        help="输出目录，默认 data/enhancing_onto_corpus_docs")
    parser.add_argument("--min-chars", type=int, default=800,
                        help="切分后单份最小字符数，默认 800")
    parser.add_argument("--max-chars", type=int, default=2500,
                        help="切分后单份最大字符数，默认 2500")
    parser.add_argument("--pdf-engine", choices=["auto", "pypdf2", "pdfplumber"],
                        default="auto", help="PDF解析引擎，默认 auto")
    parser.add_argument("--remove-references", action="store_true",
                        help="是否去除参考文献部分")
    parser.add_argument("--no-section-split", action="store_true",
                        help="禁用章节智能切分，仅按长度切分")
    parser.add_argument("--workers", type=int, default=4,
                        help="并行处理线程数，默认 4")
    parser.add_argument("--source-type", default="",
                        help="源类型（如 年鉴/公报/预案/新闻），用于文件名与元数据")
    parser.add_argument("--default-url", default="", help="默认 URL（可空），用于元数据")

    args = parser.parse_args()

    # 初始化清洗器和切分器
    cleaner = TextCleaner(
        remove_headers=True,
        remove_toc=True,
        remove_references=args.remove_references,
        remove_noise=True
    )

    splitter = SmartSplitter(
        min_chars=args.min_chars,
        max_chars=args.max_chars,
        prefer_section=not args.no_section_split
    )

    # 收集文件（去重）
    src = Path(args.input)
    out_dir = Path(args.output_dir)
    files_seen = set()
    files: List[Path] = []
    for f in iter_input_files(src):
        if f not in files_seen:
            files_seen.add(f)
            files.append(f)

    if not files:
        print(f"未找到可处理的文件: {src}")
        return

    print(f"=" * 60)
    print(f"P4语料批量清洗工具 v2.0")
    print(f"=" * 60)
    print(f"待处理: {len(files)} 个文件")
    print(f"输出目录: {out_dir}")
    print(f"字符范围: {args.min_chars} - {args.max_chars}")
    print(f"PDF引擎: {args.pdf_engine}")
    print(f"=" * 60)

    # 批量处理
    meta_defaults = {"source_type": args.source_type, "url": args.default_url}
    results = process_batch(files, out_dir, cleaner, splitter,
                            args.pdf_engine, args.workers, src_root=src, meta_defaults=meta_defaults)

    # 输出统计
    print(f"\n{'=' * 60}")
    print(f"处理完成!")
    print(f"  成功: {len(results['success'])} 个文件 → {results['total_parts']} 份")
    print(f"  跳过: {len(results['skipped'])} 个")
    print(f"  失败: {len(results['failed'])} 个")
    print(f"{'=' * 60}")

    # 生成汇总索引
    index_path = out_dir / "_corpus_index.json"
    index_data = {
        "total_files": len(files),
        "total_parts": results["total_parts"],
        "success": [(str(p), n) for p, n in results["success"]],
        "skipped": [(str(p), e) for p, e in results["skipped"]],
        "failed": [(str(p), e) for p, e in results["failed"]]
    }
    index_path.write_text(json.dumps(index_data, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    print(f"索引已保存: {index_path}")


if __name__ == "__main__":
    main()
