"""内置自检：合成一份带红色水印的 PDF，验证清除逻辑是否正确。

不依赖外部文件，可在任何机器上运行，用来快速确认安装是否正常。
"""

from __future__ import annotations

import os
import tempfile

import fitz

from .core import find_red_text_ops, page_stats, remove_red_watermark


def _make_sample_pdf(path: str) -> None:
    """生成 3 页样本：黑字正文 + 红色页眉水印 + 红色斜向水印。"""
    doc = fitz.open()
    for page_no in range(3):
        page = doc.new_page(width=595, height=842)
        # 黑色正文（必须完整保留）
        page.insert_text((72, 120), f"第 {page_no + 1} 页正文 black body text 12345", fontsize=12,
                         color=(0, 0, 0))
        page.insert_text((72, 150), "第二行黑色正文 IMPORTANT CONTENT", fontsize=12, color=(0, 0, 0))
        # 红色页眉水印
        page.insert_text((200, 30), "RED HEADER WATERMARK 严禁复制", fontsize=9, color=(1, 0, 0))
        # 红色斜向水印（用 morph 做 45° 旋转）
        origin = fitz.Point(150, 480)
        page.insert_text(
            origin,
            "RED DIAGONAL 避免侵权",
            fontsize=28,
            color=(1, 0, 0),
            morph=(origin, fitz.Matrix(45)),
        )
    doc.save(path)
    doc.close()


def run_selftest(verbose: bool = True) -> int:
    """返回进程退出码；verbose=True 时打印过程。"""
    tmpdir = tempfile.mkdtemp(prefix="pdffix_selftest_")
    src = os.path.join(tmpdir, "sample.pdf")
    dst = os.path.join(tmpdir, "sample_clean.pdf")
    try:
        _make_sample_pdf(src)

        doc = fitz.open(src)
        red_before = sum(page_stats(p)[0] for p in doc)
        black_before = [page_stats(p)[1] for p in doc]
        doc.close()

        if red_before == 0:
            raise RuntimeError("样本 PDF 未生成红色文字，无法自检")

        report = remove_red_watermark(src, dst)
        if not report.ok:
            raise RuntimeError(f"清除失败：{report.failures[:3]}")

        doc = fitz.open(dst)
        red_after = sum(page_stats(p)[0] for p in doc)
        black_after = [page_stats(p)[1] for p in doc]
        pages_after = doc.page_count
        doc.close()

        problems = []
        if red_after != 0:
            problems.append(f"仍残留 {red_after} 个红色字符")
        if black_after != black_before:
            problems.append(f"黑色正文被改动：{black_before} -> {black_after}")
        if pages_after != 3:
            problems.append(f"页数异常：{pages_after}")

        if problems:
            raise RuntimeError("；".join(problems))

        if verbose:
            print("自检通过 ✓")
            print(f"  红色字符 {red_before} -> {red_after}")
            print(f"  黑色正文 {black_before} -> {black_after}（逐页一致）")
            print(f"  页数 {pages_after} 保持不变")
        else:
            print(
                f"自检通过 ✓：红色字符 {red_before} → {red_after}，"
                f"黑色正文逐页一致，页数 {pages_after} 不变。"
            )
        return 0
    except Exception as exc:
        if verbose:
            print(f"自检失败 ✗：{exc}")
        else:
            print(f"自检失败 ✗：{exc}")
        return 1
    finally:
        for f in (src, dst):
            if os.path.exists(f):
                os.remove(f)
        if os.path.isdir(tmpdir):
            os.rmdir(tmpdir)
