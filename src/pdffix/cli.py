"""pdffix 命令行入口。"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List

from . import __version__
from .core import (
    default_outdir,
    find_pdfs,
    remove_red_watermark,
    survey_pdfs,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pdffix",
        description="清除 PDF 中的红色水印（原文件不动，结果写入独立目录）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  pdffix ~/讲义目录                      处理目录内所有 PDF，输出到 ~/讲义目录_去水印
  pdffix ~/讲义目录 -o ~/干净讲义         指定输出目录
  pdffix ~/讲义目录 --recursive          递归处理子目录
  pdffix ~/讲义目录 --in-place           原地覆盖（不推荐）
  pdffix ~/讲义目录 --survey             只统计红色水印，不写文件
  pdffix --selftest                      运行内置自检
  pdffix --gui                           打开图形界面
""",
    )
    p.add_argument("input", nargs="?", help="输入目录或 PDF 文件")
    p.add_argument("-o", "--outdir", help="输出目录（默认 <输入目录>_去水印）")
    p.add_argument("-p", "--pattern", default="*.pdf", help="文件匹配模式，默认 *.pdf")
    p.add_argument("--recursive", action="store_true", help="递归处理子目录")
    p.add_argument("--in-place", action="store_true", help="原地覆盖原文件（危险）")
    p.add_argument("--survey", action="store_true", help="只统计红色水印，不写文件")
    p.add_argument("--dry-run", action="store_true", help="只扫描统计，不写文件")
    p.add_argument("--no-verify", action="store_true", help="跳过处理后的自动校验")
    p.add_argument("--gui", action="store_true", help="打开图形界面")
    p.add_argument("--selftest", action="store_true", help="运行内置自检")
    p.add_argument("-V", "--version", action="version", version=f"pdffix {__version__}")
    return p


def _run_survey(indir: str, pattern: str) -> int:
    print(f"{'文件':<40}{'页数':>7}{'红色字符':>12}{'非红色字符':>14}")
    print("-" * 73)
    for r in survey_pdfs(indir, pattern):
        print(f"{r['file'][:38]:<40}{r['pages']:>7}{r['red']:>12}{r['other']:>14}")
        for text, cnt in sorted(r["samples"].items(), key=lambda kv: -kv[1])[:3]:
            print(f"      红色文本 x{cnt}: {text!r}")
    return 0


def _run_batch(args) -> int:
    src = os.path.abspath(os.path.expanduser(args.input))
    if os.path.isfile(src):
        files = [src]
        base = os.path.dirname(src)
    elif os.path.isdir(src):
        files = find_pdfs(src, args.pattern, args.recursive)
        base = src
    else:
        print(f"路径不存在：{src}", file=sys.stderr)
        return 2

    if not files:
        print(f"未找到匹配 {args.pattern} 的 PDF", file=sys.stderr)
        return 2

    if args.in_place:
        outdir = base
    else:
        outdir = os.path.abspath(
            os.path.expanduser(args.outdir or default_outdir(base))
        )
        os.makedirs(outdir, exist_ok=True)

    total = sum(os.path.getsize(f) for f in files)
    print(f"输入：{src}")
    print(f"输出：{outdir}")
    print(f"文件：{len(files)} 个 / {total / 1024**3:.2f} GB")
    print("-" * 70)

    failures = []
    for idx, path in enumerate(files, 1):
        dst = os.path.join(outdir, os.path.basename(path))
        print(f"[{idx}/{len(files)}] {os.path.basename(path)}")
        try:
            rep = remove_red_watermark(path, dst, verify=not args.no_verify)
        except Exception as exc:
            print(f"      ✗ 处理异常：{exc}")
            failures.append((os.path.basename(path), str(exc)))
            continue
        if rep.ok:
            print(
                f"      ✓ 页数 {rep.pages} | 清除页面 {rep.cleaned_pages} | "
                f"水印对象 {rep.watermark_objects} | 残留红字 {rep.red_chars_left} | "
                f"{rep.seconds}s"
            )
        else:
            print(f"      ✗ 校验失败，已丢弃：{rep.failures[:3]}")
            failures.append((os.path.basename(path), str(rep.failures[:3])))

    print("-" * 70)
    print(f"完成：成功 {len(files) - len(failures)} / 失败 {len(failures)}")
    if failures:
        for name, why in failures:
            print(f"  ✗ {name}: {why}")
    print(f"输出目录：{outdir}")
    return 1 if failures else 0


def main(argv: List[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.selftest:
        from .selftest import run_selftest

        return run_selftest()

    if args.gui or (not args.input and sys.stdout.isatty()):
        try:
            from .gui import launch
        except ImportError as exc:
            print(f"无法启动图形界面：{exc}", file=sys.stderr)
            return 2
        return launch()

    if not args.input:
        build_parser().print_help()
        return 2

    if args.survey or args.dry_run:
        src = os.path.abspath(os.path.expanduser(args.input))
        if not os.path.isdir(src):
            print(f"目录不存在：{src}", file=sys.stderr)
            return 2
        return _run_survey(src, args.pattern)

    return _run_batch(args)


if __name__ == "__main__":
    raise SystemExit(main())
