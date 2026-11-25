"""pdffix：清除 PDF 中的红色水印（内容流手术法）。

核心思路
--------
PDF 内容流里，文字由 show-text 指令（Tj / TJ / ' / "）绘制，绘制前用
rg / g / k 设置填色颜色。本模块完整解析内容流的操作符序列，维护图形
状态栈（q / Q）与当前填色颜色，**精确找出填色为红色的 show-text 指令并
逐字节删除**。

相比「矩形遮盖」的优势：水印的轴对齐外接框往往很大，遮盖会连带删掉
正文黑色文字；相比「重新栅格化」：不损失图片质量，图像字节保持不变。
"""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import fitz  # PyMuPDF
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "缺少依赖 PyMuPDF，请执行：pip3 install pymupdf"
    ) from exc


__version__ = "1.0.0"


# --------------------------------------------------------------------------- #
# 颜色判定
# --------------------------------------------------------------------------- #
def is_red_rgb(r: float, g: float, b: float) -> bool:
    """判定 RGB 是否为红色：红通道显著占优。"""
    return r > 0.30 and r - g > 0.18 and r - b > 0.18


def cmyk_to_rgb(c: float, m: float, y: float, k: float) -> Tuple[float, float, float]:
    return ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))


def span_color_red(span: dict) -> bool:
    """兼容 get_texttrace 的 float RGB 与 get_text 的 int RGB。"""
    color = span.get("color")
    if color is None:
        return False
    if isinstance(color, (tuple, list)) and len(color) >= 3:
        return is_red_rgb(color[0], color[1], color[2])
    if isinstance(color, int):
        r, g, b = (color >> 16) & 255, (color >> 8) & 255, color & 255
        return r > 90 and r - g > 50 and r - b > 50
    return False


# --------------------------------------------------------------------------- #
# 内容流解析
# --------------------------------------------------------------------------- #
SHOW_OPS = {b"Tj", b"TJ", b"'", b'"'}
_WS = b"\x00\t\n\x0c\r "
_DELIM = b"()<>[]{}/%"
_OPCHARS = b"0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ*'\""
_NAME_OK = b"0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ._+-"


def _skip_ws(data: bytes, i: int) -> int:
    """跳过空白与 % 注释。"""
    n = len(data)
    while i < n:
        c = data[i : i + 1]
        if c in _WS:
            i += 1
        elif c == b"%":
            j = data.find(b"\n", i)
            i = n if j < 0 else j + 1
        else:
            break
    return i


def _scan_literal_string(data: bytes, i: int) -> Tuple[int, int]:
    """i 指向 '('，返回 (start, end)，处理嵌套括号与转义。"""
    start = i
    depth = 0
    n = len(data)
    while i < n:
        c = data[i : i + 1]
        if c == b"\\":
            i += 2
            continue
        if c == b"(":
            depth += 1
        elif c == b")":
            depth -= 1
            if depth == 0:
                return start, i + 1
        i += 1
    return start, n


def _scan_hex_string(data: bytes, i: int) -> Tuple[int, int]:
    start = i
    n = len(data)
    i += 1
    while i < n and data[i : i + 1] != b">":
        i += 1
    return start, min(i + 1, n)


def _scan_array(data: bytes, i: int) -> Tuple[int, int]:
    start = i
    n = len(data)
    depth = 0
    while i < n:
        c = data[i : i + 1]
        if c == b"(":
            _, i = _scan_literal_string(data, i)
            continue
        if c == b"<" and data[i + 1 : i + 2] != b"<":
            _, i = _scan_hex_string(data, i)
            continue
        if c == b"[":
            depth += 1
        elif c == b"]":
            depth -= 1
            if depth == 0:
                return start, i + 1
        i += 1
    return start, n


def parse_ops(data: bytes) -> List[dict]:
    """
    把内容流解析成操作符序列。每项：
        {"op": bytes, "op_start": int, "op_end": int,
         "operands": [(start, end, value), ...]}
    操作数按 PDF 规则累积，遇到操作符时归零。
    """
    ops: List[dict] = []
    pending: List[Tuple[int, int, object]] = []
    i = 0
    n = len(data)
    while i < n:
        i = _skip_ws(data, i)
        if i >= n:
            break
        c = data[i : i + 1]
        if c == b"(":
            s, e = _scan_literal_string(data, i)
            pending.append((s, e, None))
            i = e
        elif c == b"<":
            if data[i + 1 : i + 2] == b"<":
                depth = 0
                j = i
                while j < n:
                    if data[j : j + 2] == b"<<":
                        depth += 1
                        j += 2
                    elif data[j : j + 2] == b">>":
                        depth -= 1
                        j += 2
                        if depth == 0:
                            break
                    else:
                        j += 1
                pending.append((i, j, None))
                i = j
            else:
                s, e = _scan_hex_string(data, i)
                pending.append((s, e, None))
                i = e
        elif c == b"[":
            s, e = _scan_array(data, i)
            pending.append((s, e, None))
            i = e
        elif c == b"/":
            j = i + 1
            while j < n and data[j : j + 1] in _NAME_OK:
                j += 1
            pending.append((i, j, data[i + 1 : j]))
            i = j
        elif c in b"+-.0123456789":
            j = i
            while j < n and data[j : j + 1] in b"+-.0123456789":
                j += 1
            try:
                val = float(data[i:j])
            except ValueError:
                val = None
            pending.append((i, j, val))
            i = j
        elif c in b"])>":
            i += 1
        else:
            j = i
            while j < n and data[j : j + 1] in _OPCHARS:
                j += 1
            if j == i:
                i += 1
                continue
            ops.append({"op": data[i:j], "op_start": i, "op_end": j, "operands": pending})
            pending = []
            i = j
    return ops


def _nums(op: dict) -> List[float]:
    return [o[2] for o in op["operands"] if isinstance(o[2], (int, float))]


def find_red_text_ops(data: bytes) -> List[Tuple[int, int]]:
    """
    返回需要删除的字节区间 [(start, end), ...]：
    填色为红色的 show-text 指令及其操作数。
    """
    ops = parse_ops(data)
    stack: List[Tuple[float, float, float]] = []
    fill = (0.0, 0.0, 0.0)
    hits: List[Tuple[int, int]] = []
    for op in ops:
        name = op["op"]
        vals = _nums(op)
        if name == b"q":
            stack.append(fill)
        elif name == b"Q":
            if stack:
                fill = stack.pop()
        elif name == b"rg" and len(vals) >= 3:
            fill = (vals[-3], vals[-2], vals[-1])
        elif name == b"g" and vals:
            fill = (vals[-1], vals[-1], vals[-1])
        elif name == b"k" and len(vals) >= 4:
            fill = cmyk_to_rgb(vals[-4], vals[-3], vals[-2], vals[-1])
        elif name in (b"sc", b"scn") and len(vals) >= 3:
            fill = (vals[-3], vals[-2], vals[-1])
        elif name in SHOW_OPS:
            if is_red_rgb(*fill):
                if op["operands"]:
                    o_s, o_e, _ = op["operands"][-1]
                else:
                    o_s = o_e = op["op_start"]
                hits.append((o_s, o_e))
                hits.append((op["op_start"], op["op_end"]))
    return hits


def cut_ranges(data: bytes, ranges: Sequence[Tuple[int, int]]) -> bytes:
    """按字节区间从 data 中删除片段。"""
    if not ranges:
        return data
    merged: List[List[int]] = []
    for s, e in sorted(ranges):
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    out = bytearray()
    pos = 0
    for s, e in merged:
        out += data[pos:s]
        pos = e
    out += data[pos:]
    return bytes(out)


# --------------------------------------------------------------------------- #
# 页面与文档处理
# --------------------------------------------------------------------------- #
def page_stats(page) -> Tuple[int, int, List[str]]:
    """(红色字符数, 非红色字符数, 红色文本样本)"""
    red = other = 0
    samples: List[str] = []
    for blk in page.get_text("dict")["blocks"]:
        if blk.get("type") != 0:
            continue
        for ln in blk["lines"]:
            for sp in ln["spans"]:
                if span_color_red(sp):
                    red += len(sp["text"])
                    samples.append(sp["text"])
                else:
                    other += len(sp["text"])
    return red, other, samples


def _collect_xobject_edits(doc, pages: Iterable) -> Dict[int, Tuple[bytes, bytes]]:
    """找出含红色文字指令的 Form XObject（页眉水印通常在此）。"""
    edits: Dict[int, Tuple[bytes, bytes]] = {}
    for page in pages:
        try:
            xobjs = page.get_xobjects()
        except Exception:
            continue
        for item in xobjs:
            xref = item[0]
            if xref in edits:
                continue
            try:
                obj = doc.xref_object(xref, compressed=False)
            except Exception:
                continue
            if isinstance(obj, bytes):
                obj = obj.decode("latin-1")
            # 只处理 Form 型 XObject，图片型绝不碰
            if "/Form" not in obj:
                continue
            try:
                raw = doc.xref_stream(xref)
            except Exception:
                continue
            if not raw:
                continue
            hits = find_red_text_ops(raw)
            if hits:
                edits[xref] = (raw, cut_ranges(raw, hits))
    return edits


@dataclass
class FileReport:
    """单个文件的处理结果。"""

    source: str
    target: str
    pages: int = 0
    cleaned_pages: int = 0
    watermark_objects: int = 0
    red_chars_left: int = 0
    ok: bool = False
    failures: List[str] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def name(self) -> str:
        return os.path.basename(self.source)


def remove_red_watermark(
    src: str,
    dst: str,
    *,
    verify: bool = True,
    garbage_collect: bool = True,
) -> FileReport:
    """
    清除单个 PDF 的红色水印并另存为 dst。

    verify=True 时逐页校验：红色字符数须归零、非红色字符数须与处理前完全
    一致；任一不符即丢弃结果并返回 ok=False。
    """
    import time

    t0 = time.time()
    doc = fitz.open(src)
    report = FileReport(source=src, target=dst, pages=doc.page_count)

    before = [page_stats(page) for page in doc]

    # 1) 共享的 Form XObject（页眉水印）
    for xref, (raw, new) in _collect_xobject_edits(doc, doc).items():
        if new == raw:
            continue
        doc.update_stream(xref, new, new=False, compress=True)
        report.watermark_objects += 1

    # 2) 各页内联内容流（斜向防复制文字等）
    for i, page in enumerate(doc):
        try:
            xrefs = page.get_contents()
        except Exception as exc:
            report.failures.append(f"p{i}: 读取内容流失败 {exc}")
            continue
        for xref in xrefs:
            try:
                raw = doc.xref_stream(xref)
            except Exception as exc:
                report.failures.append(f"p{i}: 读取内容流 {xref} 失败 {exc}")
                continue
            if not raw:
                continue
            hits = find_red_text_ops(raw)
            if not hits:
                continue
            new = cut_ranges(raw, hits)
            if new == raw:
                continue
            # 原位覆盖内容流对象：不新建对象、不改页面结构
            doc.update_stream(xref, new, new=False, compress=True)

    # 3) 校验
    after = [page_stats(page) for page in doc]
    report.cleaned_pages = sum(
        1 for i, (red, _, _) in enumerate(after) if red == 0 and before[i][0] > 0
    )
    if verify:
        for i, (red, other, _) in enumerate(after):
            report.red_chars_left += red
            if red != 0:
                report.failures.append(f"p{i}: 仍残留 {red} 个红色字符")
            elif other != before[i][1]:
                report.failures.append(
                    f"p{i}: 非红色字符 {before[i][1]} -> {other}"
                )
        if report.failures:
            doc.close()
            report.seconds = round(time.time() - t0, 1)
            return report

    kwargs = {"garbage": 4, "deflate": True, "deflate_images": True} if garbage_collect else {}
    doc.save(dst, **kwargs)
    doc.close()
    report.ok = True
    report.seconds = round(time.time() - t0, 1)
    return report


def find_pdfs(indir: str, pattern: str = "*.pdf", recursive: bool = False) -> List[str]:
    """列出目录下的 PDF 文件。"""
    if recursive:
        out: List[str] = []
        for root, _, names in os.walk(indir):
            out += [os.path.join(root, n) for n in names if fnmatch.fnmatch(n, pattern)]
        return sorted(out)
    return sorted(
        os.path.join(indir, n)
        for n in os.listdir(indir)
        if fnmatch.fnmatch(n, pattern) and n.lower().endswith(".pdf")
    )


def survey_pdfs(indir: str, pattern: str = "*.pdf") -> List[dict]:
    """统计各文件的红色字符数、非红色字符数与红色文本样本。"""
    results = []
    for path in find_pdfs(indir, pattern):
        doc = fitz.open(path)
        red = other = 0
        samples: Dict[str, int] = {}
        for page in doc:
            r, o, s = page_stats(page)
            red += r
            other += o
            for t in s:
                samples[t[:24]] = samples.get(t[:24], 0) + 1
        results.append(
            {
                "file": os.path.basename(path),
                "pages": doc.page_count,
                "red": red,
                "other": other,
                "samples": samples,
            }
        )
        doc.close()
    return results


def default_outdir(indir: str) -> str:
    return indir.rstrip("/") + "_去水印"
