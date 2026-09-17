"""通用工具函数：git 调用、日期解析、颜色输出等。"""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


class Colors:
    """终端颜色转义序列；当输出不是 TTY 时自动禁用。"""

    reset = "\033[0m"
    bold = "\033[1m"
    dim = "\033[2m"
    red = "\033[31m"
    green = "\033[32m"
    yellow = "\033[33m"
    blue = "\033[34m"
    magenta = "\033[35m"
    cyan = "\033[36m"

    @classmethod
    def disable(cls) -> None:
        for name in dir(cls):
            if not name.startswith("_") and isinstance(getattr(cls, name), str):
                setattr(cls, name, "")


def ensure_color(no_color: bool = False) -> None:
    """根据环境变量和 no_color 参数决定是否启用颜色。"""
    if no_color or os.environ.get("NO_COLOR"):
        Colors.disable()


def run_git(
    repo: Path,
    args: list[str],
    check: bool = True,
    capture: bool = True,
    text: bool = True,
    input_data: str | None = None,
) -> subprocess.CompletedProcess:
    """在指定仓库目录下调用 git；input_data 用于需要 stdin 的命令（如 cat-file --batch-check）。"""
    cmd = ["git", "-C", str(repo), *args]
    return subprocess.run(
        cmd,
        input=input_data,
        capture_output=capture,
        text=text,
        check=check,
        encoding="utf-8",
        errors="replace",
    )


def git_ok(repo: Path) -> bool:
    """检查目录是否为有效的 git 仓库。"""
    try:
        result = run_git(repo, ["rev-parse", "--git-dir"], check=False)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def parse_git_date(value: str) -> datetime:
    """解析 git 时间戳（如 '1725148800 +0800'）。"""
    parts = value.strip().split()
    ts = int(parts[0])
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt


def human_size(num_bytes: int) -> str:
    """将字节数转换为人类可读字符串。"""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} PB"


def human_duration(dt: datetime) -> str:
    """计算并返回距今的友好时间差。"""
    now = datetime.now(timezone.utc)
    diff = now - dt
    days = diff.days
    if days >= 365:
        return f"{days // 365} 年前"
    if days >= 30:
        return f"{days // 30} 个月前"
    if days >= 7:
        return f"{days // 7} 周前"
    if days >= 1:
        return f"{days} 天前"
    hours = diff.seconds // 3600
    if hours >= 1:
        return f"{hours} 小时前"
    return "刚刚"


def split_lines(text: str) -> list[str]:
    """按行分割并过滤空行。"""
    return [line for line in text.splitlines() if line.strip()]


def truncate(text: str, width: int = 60) -> str:
    """截断字符串到指定宽度。"""
    if len(text) <= width:
        return text
    return text[: width - 1] + "…"


def read_lines(path: Path, max_size: int = 2 * 1024 * 1024) -> list[str]:
    """读取文件前若干字节并按行返回；避免大文件拖慢扫描。"""
    try:
        data = path.read_bytes()
        if len(data) > max_size:
            data = data[:max_size]
        return data.decode("utf-8", errors="replace").splitlines()
    except (OSError, UnicodeDecodeError):
        return []


def glob_text_files(repo: Path) -> Iterable[Path]:
    """遍历 git 跟踪的文本文件路径（粗略过滤二进制扩展名）。"""
    binary_exts = {
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".ico", ".svg",
        ".mp3", ".mp4", ".avi", ".mov", ".mkv", ".webm",
        ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".exe", ".dll", ".so", ".dylib", ".bin", ".o", ".a",
        ".pyc", ".pyo", ".class", ".jar", ".war",
        ".lock"  # lock 文件通常无敏感信息，可跳过
    }
    result = run_git(repo, ["ls-files"])
    for line in split_lines(result.stdout):
        p = repo / line
        if p.suffix.lower() in binary_exts:
            continue
        if not p.is_file():
            continue
        yield p
