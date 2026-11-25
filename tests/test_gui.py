"""GUI 无头测试：验证处理线程与事件上报逻辑（不需要图形会话）。"""

import os
import queue
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pdffix.gui import App  # noqa: E402
from pdffix.selftest import _make_sample_pdf  # noqa: E402


def test_gui_worker_reports_success():
    """不打开窗口，直接驱动 App._worker，验证事件与统计。"""
    tmp = tempfile.mkdtemp(prefix="pdffix_gui_test_")
    src = os.path.join(tmp, "s.pdf")
    out = os.path.join(tmp, "out")
    try:
        _make_sample_pdf(src)
        app = App.__new__(App)          # 绕过 Tk 初始化
        app._events = queue.Queue()
        app._say = lambda line: None

        app._worker([src], out, False)

        events = []
        while not app._events.empty():
            events.append(app._events.get_nowait())

        kinds = [k for k, _ in events]
        assert "done" in kinds, "应上报 done 事件"
        assert "log" in kinds, "应上报 log 事件"
        assert "progress" in kinds, "应上报 progress 事件"

        done = dict(events)["done"]
        assert done[0] is True, f"处理应成功，实际: {done}"
        assert os.path.exists(os.path.join(out, "s.pdf"))
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    try:
        test_gui_worker_reports_success()
        print("✓ test_gui_worker_reports_success")
        print("-" * 40)
        print("全部通过")
    except Exception as exc:
        print(f"✗ test_gui_worker_reports_success: {exc}")
        raise SystemExit(1)
