"""pdffix 图形界面：拖入目录即可批量清除 PDF 红色水印。"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .core import default_outdir, find_pdfs, remove_red_watermark


class App(ttk.Frame):
    def __init__(self, master: tk.Tk):
        super().__init__(master, padding=16)
        self.master.title("pdffix — PDF 红色水印清除工具")
        self.master.minsize(720, 520)
        self.master.geometry("760x600")
        self.grid(row=0, column=0, sticky="nsew")
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        self._indir = tk.StringVar()
        self._outdir = tk.StringVar()
        self._recursive = tk.BooleanVar(value=False)
        self._inplace = tk.BooleanVar(value=False)
        self._status = tk.StringVar(value="就绪")
        self._events: "queue.Queue[tuple]" = queue.Queue()

        self._build()
        self.master.after(120, self._drain_events)

    # ---------------- 界面 ----------------
    def _build(self) -> None:
        ttk.Label(self, text="PDF 红色水印批量清除", font=("TkDefaultFont", 15, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            self,
            text="只删除内容流中以红色绘制的文字指令，图像与正文一字不动。默认不改原文件。",
        ).grid(row=1, column=0, sticky="w", pady=(2, 12))

        # 输入目录
        ttk.Label(self, text="输入目录").grid(row=2, column=0, sticky="w")
        row = ttk.Frame(self)
        row.grid(row=3, column=0, sticky="ew", pady=(2, 10))
        row.columnconfigure(0, weight=1)
        ttk.Entry(row, textvariable=self._indir).grid(row=0, column=0, sticky="ew")
        ttk.Button(row, text="选择…", command=self._pick_indir).grid(
            row=0, column=1, padx=(8, 0)
        )

        # 输出目录
        ttk.Label(self, text="输出目录").grid(row=4, column=0, sticky="w")
        row2 = ttk.Frame(self)
        row2.grid(row=5, column=0, sticky="ew", pady=(2, 10))
        row2.columnconfigure(0, weight=1)
        ttk.Entry(row2, textvariable=self._outdir).grid(row=0, column=0, sticky="ew")
        ttk.Button(row2, text="选择…", command=self._pick_outdir).grid(
            row=0, column=1, padx=(8, 0)
        )

        # 选项
        opts = ttk.Frame(self)
        opts.grid(row=6, column=0, sticky="w", pady=(0, 10))
        ttk.Checkbutton(opts, text="递归处理子目录", variable=self._recursive).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Checkbutton(opts, text="原地覆盖原文件（危险）", variable=self._inplace).grid(
            row=0, column=1, sticky="w", padx=(16, 0)
        )

        # 操作
        self._btn_start = ttk.Button(self, text="开始处理", command=self._start)
        self._btn_start.grid(row=7, column=0, sticky="w", pady=(0, 10))
        self._btn_selftest = ttk.Button(self, text="运行自检", command=self._selftest)
        self._btn_selftest.grid(row=7, column=0, sticky="e", pady=(0, 10))

        # 进度
        self._bar = ttk.Progressbar(self, mode="determinate")
        self._bar.grid(row=8, column=0, sticky="ew", pady=(0, 4))
        ttk.Label(self, textvariable=self._status).grid(row=9, column=0, sticky="w")

        # 日志
        ttk.Label(self, text="处理日志").grid(row=10, column=0, sticky="w", pady=(12, 2))
        text_frame = ttk.Frame(self)
        text_frame.grid(row=11, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(11, weight=1)
        self._log = tk.Text(text_frame, height=12, wrap="none")
        self._log.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(text_frame, command=self._log.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self._log.configure(yscrollcommand=scroll.set)

    # ---------------- 交互 ----------------
    def _pick_indir(self) -> None:
        d = filedialog.askdirectory(title="选择包含 PDF 的目录")
        if d:
            self._indir.set(d)
            if not self._outdir.get():
                self._outdir.set(default_outdir(d))

    def _pick_outdir(self) -> None:
        d = filedialog.askdirectory(title="选择输出目录")
        if d:
            self._outdir.set(d)

    def _say(self, line: str) -> None:
        self._log.insert("end", line + "\n")
        self._log.see("end")

    def _drain_events(self) -> None:
        try:
            while True:
                kind, payload = self._events.get_nowait()
                if kind == "log":
                    self._say(payload)
                elif kind == "status":
                    self._status.set(payload)
                elif kind == "progress":
                    cur, total = payload
                    self._bar.configure(maximum=max(total, 1), value=cur)
                elif kind == "done":
                    self._bar.configure(value=self._bar["maximum"])
                    self._btn_start.configure(state="normal")
                    ok, msg = payload
                    if ok:
                        messagebox.showinfo("处理完成", msg)
                    else:
                        messagebox.showerror("处理失败", msg)
        except queue.Empty:
            pass
        self.master.after(120, self._drain_events)

    def _start(self) -> None:
        indir = self._indir.get().strip()
        if not indir:
            messagebox.showwarning("提示", "请先选择输入目录")
            return
        if not os.path.isdir(indir):
            messagebox.showerror("错误", f"目录不存在：{indir}")
            return

        inplace = self._inplace.get()
        outdir = self._outdir.get().strip() or (
            indir if inplace else default_outdir(indir)
        )
        if not inplace:
            try:
                os.makedirs(outdir, exist_ok=True)
            except OSError as exc:
                messagebox.showerror("错误", f"无法创建输出目录：{exc}")
                return

        files = find_pdfs(indir, "*.pdf", self._recursive.get())
        if not files:
            messagebox.showwarning("提示", "该目录下没有找到 PDF 文件")
            return

        self._btn_start.configure(state="disabled")
        self._bar.configure(maximum=len(files), value=0)
        self._status.set("处理中…")
        self._say(f"输入：{indir}")
        self._say(f"输出：{outdir}")
        self._say(f"共 {len(files)} 个 PDF，开始处理…")
        self._say("-" * 56)

        thread = threading.Thread(
            target=self._worker,
            args=(files, outdir, inplace),
            daemon=True,
        )
        thread.start()

    def _worker(self, files, outdir: str, inplace: bool) -> None:
        if not inplace:
            os.makedirs(outdir, exist_ok=True)
        ok_count = 0
        bad: list[str] = []
        for idx, path in enumerate(files, 1):
            dst = os.path.join(outdir, os.path.basename(path))
            try:
                rep = remove_red_watermark(path, dst)
            except Exception as exc:
                bad.append(f"{os.path.basename(path)}: {exc}")
                self._events.put(("log", f"[{idx}/{len(files)}] ✗ {os.path.basename(path)} — {exc}"))
            else:
                if rep.ok:
                    ok_count += 1
                    self._events.put(
                        (
                            "log",
                            f"[{idx}/{len(files)}] ✓ {os.path.basename(path)} — "
                            f"{rep.pages} 页，清除 {rep.cleaned_pages} 页，"
                            f"残留红字 {rep.red_chars_left}",
                        )
                    )
                else:
                    bad.append(f"{os.path.basename(path)}: {rep.failures[:2]}")
                    self._events.put(
                        ("log", f"[{idx}/{len(files)}] ✗ {os.path.basename(path)} — 校验失败")
                    )
            self._events.put(("progress", (idx, len(files))))
        self._events.put(
            (
                "done",
                (
                    not bad,
                    f"成功 {ok_count} 个 / 失败 {len(bad)} 个\n输出目录：{outdir}",
                ),
            )
        )

    def _selftest(self) -> None:
        from .selftest import run_selftest

        try:
            ok, detail = run_selftest(verbose=False)
        except Exception as exc:
            messagebox.showerror("自检失败", str(exc))
            return
        if ok:
            messagebox.showinfo("自检通过", detail)
        else:
            messagebox.showerror("自检失败", detail)


def launch() -> int:
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0
