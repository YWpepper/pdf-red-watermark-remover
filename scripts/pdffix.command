#!/bin/bash
# pdffix 启动器（macOS 双击即可运行）
#
#   双击本文件   → 打开图形界面
#   终端带参数   → 等同于 pdffix 命令行，例如：
#                   ./scripts/pdffix.command ~/讲义目录
#
# 首次运行会自动检查并安装依赖 PyMuPDF。

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$(command -v python3 || true)"

if [ -z "$PY" ]; then
  echo "错误：未找到 python3，请先安装 Python 3.8+"
  read -r -p "按回车键退出…" _
  exit 1
fi

# 依赖检查
if ! "$PY" -c "import fitz" >/dev/null 2>&1; then
  echo "正在安装依赖 PyMuPDF …"
  if ! "$PY" -m pip install --user --quiet pymupdf; then
    echo "依赖安装失败，请手动执行：python3 -m pip install pymupdf"
    read -r -p "按回车键退出…" _
    exit 1
  fi
fi

export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

if [ "$#" -eq 0 ]; then
  echo "pdffix 图形界面启动中 …（关闭窗口即退出）"
  exec "$PY" -m pdffix --gui
else
  exec "$PY" -m pdffix "$@"
fi
