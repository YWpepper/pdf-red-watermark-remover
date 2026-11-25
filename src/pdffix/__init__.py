"""pdffix — 清除 PDF 中的红色水印。

用法：
    from pdffix import remove_red_watermark
    report = remove_red_watermark("in.pdf", "out.pdf")
    print(report.ok, report.cleaned_pages, report.red_chars_left)
"""

from .core import (
    FileReport,
    find_pdfs,
    find_red_text_ops,
    remove_red_watermark,
    survey_pdfs,
)

__version__ = "1.0.0"
__all__ = [
    "FileReport",
    "find_pdfs",
    "find_red_text_ops",
    "remove_red_watermark",
    "survey_pdfs",
    "__version__",
]
