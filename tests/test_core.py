"""pdffix 核心逻辑测试。

运行：python3 -m pytest tests/ -v
或：   python3 tests/test_core.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import fitz  # noqa: E402

from pdffix.core import (  # noqa: E402
    cut_ranges,
    find_red_text_ops,
    is_red_rgb,
    page_stats,
    remove_red_watermark,
)
from pdffix.selftest import _make_sample_pdf, run_selftest  # noqa: E402


def test_is_red_rgb():
    assert is_red_rgb(1.0, 0.0, 0.0)
    assert is_red_rgb(1.0, 0.027, 0.027)
    assert not is_red_rgb(0.0, 0.0, 0.0)
    assert not is_red_rgb(0.1, 0.1, 0.1)
    assert not is_red_rgb(0.0, 0.4, 0.8)


def test_find_red_text_ops():
    data = b"q BT 1 0 0 rg (red) Tj ET Q q BT 0 0 0 rg (black) Tj ET Q"
    hits = find_red_text_ops(data)
    assert hits, "应检出红色指令"
    cleaned = cut_ranges(data, hits)
    assert b"red" not in cleaned
    assert b"black" in cleaned


def test_cut_ranges():
    data = b"0123456789"
    assert cut_ranges(data, [(2, 4)]) == b"01456789"
    assert cut_ranges(data, []) == data
    assert cut_ranges(data, [(2, 4), (3, 5)]) == b"0156789"


def test_remove_red_watermark_end_to_end():
    tmp = tempfile.mkdtemp(prefix="pdffix_test_")
    src = os.path.join(tmp, "s.pdf")
    dst = os.path.join(tmp, "d.pdf")
    try:
        _make_sample_pdf(src)
        rep = remove_red_watermark(src, dst)
        assert rep.ok, rep.failures
        assert rep.pages == 3
        assert rep.red_chars_left == 0

        doc = fitz.open(dst)
        assert doc.page_count == 3
        for p in doc:
            red, other, _ = page_stats(p)
            assert red == 0
            assert "IMPORTANT CONTENT" in "".join(
                sp["text"]
                for b in p.get_text("dict")["blocks"]
                if b.get("type") == 0
                for l in b["lines"]
                for sp in l["spans"]
            )
        doc.close()
    finally:
        for f in (src, dst):
            if os.path.exists(f):
                os.remove(f)
        os.rmdir(tmp)


def test_selftest_entrypoint():
    assert run_selftest(verbose=False) == 0


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"✓ {name}")
            except Exception as exc:
                failures += 1
                print(f"✗ {name}: {exc}")
    print("-" * 40)
    print("全部通过" if not failures else f"{failures} 项失败")
    raise SystemExit(1 if failures else 0)
