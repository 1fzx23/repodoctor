"""内置诊断规则：大文件、旧分支、敏感信息、未跟踪文件等。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from .utils import (
    Colors,
    git_ok,
    glob_text_files,
    human_duration,
    human_size,
    parse_git_date,
    read_lines,
    run_git,
    split_lines,
)


@dataclass
class Finding:
    """单条诊断发现。"""

    rule: str
    severity: str  # info / warning / error
    message: str
    details: dict | None = None

    def format(self, verbose: bool = False) -> str:
        icon = {"info": "ℹ️", "warning": "⚠️", "error": "🚨"}.get(self.severity, "•")
        lines = [f"{icon} [{self.rule}] {self.message}"]
        if verbose and self.details:
            for k, v in self.details.items():
                lines.append(f"   {Colors.dim}{k}:{Colors.reset} {v}")
        return "\n".join(lines)


# 敏感信息检测规则（简单启发式，不保证 100% 覆盖）
SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("AWS Access Key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("GitHub Token (classic)", re.compile(r"ghp_[A-Za-z0-9_]{36}")),
    ("GitHub Fine-Grained Token", re.compile(r"github_pat_[A-Za-z0-9_]{22}_[A-Za-z0-9_]{59}")),
    ("Slack Token", re.compile(r"xox[baprs]-[0-9a-zA-Z]{10,48}")),
    ("Private Key", re.compile(r"-----BEGIN (RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("API Key (generic)", re.compile(r"(?i)(api[_-]?key|apikey)\s*[:=]\s*['\"]?[a-z0-9_\-]{16,}['\"]?")),
    ("Password assignment", re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"][^'\"]{8,}['\"]")),
    ("JWT", re.compile(r"eyJ[A-Za-z0-9_\-]*\.eyJ[A-Za-z0-9_\-]*\.[A-Za-z0-9_\-]*")),
]


def rule_large_blobs(repo: Path, threshold_mb: float = 1.0) -> list[Finding]:
    """扫描 git 历史中超过阈值的大 blob。"""
    findings: list[Finding] = []
    threshold = int(threshold_mb * 1024 * 1024)
    if not git_ok(repo):
        return [Finding("large-blobs", "error", "不是有效的 git 仓库")]

    result = run_git(repo, ["rev-list", "--objects", "--all"], check=False)
    if result.returncode != 0:
        return [Finding("large-blobs", "error", f"无法枚举对象：{result.stderr.strip()}")]

    objects: dict[str, tuple[str, str]] = {}  # sha -> (path, ref)
    for line in split_lines(result.stdout):
        parts = line.split(" ", 1)
        sha = parts[0]
        path = parts[1] if len(parts) > 1 else ""
        objects[sha] = (path, "")

    # 获取每个对象的大小（通过 stdin 批量查询）
    if not objects:
        return findings

    cat = run_git(
        repo,
        ["cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)"],
        input_data="\n".join(objects.keys()) + "\n",
    )
    sizes: dict[str, int] = {}
    for line in split_lines(cat.stdout):
        parts = line.split()
        if len(parts) >= 3 and parts[1] == "blob":
            sizes[parts[0]] = int(parts[2])

    for sha, (path, _) in objects.items():
        size = sizes.get(sha, 0)
        if size > threshold:
            findings.append(
                Finding(
                    "large-blobs",
                    "warning",
                    f"发现大 blob：{truncate(path) or '<未知路径>'} ({human_size(size)})",
                    {"sha": sha, "size_bytes": size, "path": path},
                )
            )
    return findings


def rule_old_branches(repo: Path, days: int = 90) -> list[Finding]:
    """找出超过指定天数未更新的分支。"""
    findings: list[Finding] = []
    if not git_ok(repo):
        return [Finding("old-branches", "error", "不是有效的 git 仓库")]

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = run_git(repo, ["for-each-ref", "--sort=-committerdate", "refs/heads/", "--format=%(refname:short) %(committerdate:iso) %(upstream:short)"])

    for line in split_lines(result.stdout):
        parts = line.split(" ", 2)
        if len(parts) < 2:
            continue
        branch = parts[0]
        date_str = " ".join(parts[1:3]) if len(parts) == 3 else parts[1]
        upstream = parts[2] if len(parts) == 3 else ""
        try:
            dt = datetime.fromisoformat(date_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if dt < cutoff:
            findings.append(
                Finding(
                    "old-branches",
                    "warning",
                    f"分支太久未更新：{branch}（{human_duration(dt)}）",
                    {"branch": branch, "last_commit": dt.isoformat(), "upstream": upstream},
                )
            )
    return findings


def rule_secrets(repo: Path, max_files: int = 500) -> list[Finding]:
    """扫描工作区文本文件中的潜在敏感信息（含未跟踪文件）。"""
    findings: list[Finding] = []
    if not git_ok(repo):
        return [Finding("secrets", "error", "不是有效的 git 仓库")]

    # 已跟踪文件
    tracked = list(glob_text_files(repo))
    # 未跟踪文件
    status = run_git(repo, ["status", "--porcelain"], check=False)
    untracked: list[Path] = []
    for line in split_lines(status.stdout):
        if line.startswith("??"):
            p = repo / line[3:]
            if p.is_file():
                untracked.append(p)

    files = (tracked + untracked)[:max_files]
    for p in files:
        lines = read_lines(p)
        rel = p.relative_to(repo).as_posix()
        for lineno, raw in enumerate(lines, start=1):
            for name, pattern in SECRET_PATTERNS:
                if pattern.search(raw):
                    snippet = raw.strip()
                    findings.append(
                        Finding(
                            "secrets",
                            "error",
                            f"疑似 {name}：{rel}:{lineno}",
                            {"file": rel, "line": lineno, "snippet": snippet[:120]},
                        )
                    )
    return findings


def rule_untracked_files(repo: Path) -> list[Finding]:
    """检查未跟踪文件与忽略规则。"""
    findings: list[Finding] = []
    if not git_ok(repo):
        return findings

    result = run_git(repo, ["status", "--porcelain"])
    untracked: list[str] = []
    for line in split_lines(result.stdout):
        if line.startswith("??"):
            untracked.append(line[3:])
    if untracked:
        sample = ", ".join(untracked[:5]) + (" ..." if len(untracked) > 5 else "")
        findings.append(
            Finding(
                "untracked-files",
                "info",
                f"有 {len(untracked)} 个未跟踪文件：{sample}",
                {"count": len(untracked), "samples": untracked[:10]},
            )
        )
    return findings


def rule_working_tree(repo: Path) -> list[Finding]:
    """检查工作区是否有未提交更改。"""
    findings: list[Finding] = []
    if not git_ok(repo):
        return findings

    result = run_git(repo, ["status", "--porcelain"])
    dirty = [line for line in split_lines(result.stdout) if not line.startswith("??")]
    if dirty:
        findings.append(
            Finding(
                "working-tree",
                "warning",
                f"工作区有 {len(dirty)} 处未提交改动，建议及时 commit",
                {"count": len(dirty)},
            )
        )
    return findings


def rule_remote_sync(repo: Path) -> list[Finding]:
    """检查本地分支是否落后于远程。"""
    findings: list[Finding] = []
    if not git_ok(repo):
        return findings

    result = run_git(repo, ["for-each-ref", "--format=%(refname:short) %(upstream:short)", "refs/heads"])
    for line in split_lines(result.stdout):
        parts = line.split()
        if len(parts) != 2:
            continue
        local, upstream = parts
        rev = run_git(repo, ["rev-list", f"{upstream}..{local}", "--count"], check=False)
        ahead = int(rev.stdout.strip() or 0)
        rev2 = run_git(repo, ["rev-list", f"{local}..{upstream}", "--count"], check=False)
        behind = int(rev2.stdout.strip() or 0)
        if behind > 0:
            findings.append(
                Finding(
                    "remote-sync",
                    "warning",
                    f"本地分支 {local} 落后于 {upstream} {behind} 个提交",
                    {"branch": local, "upstream": upstream, "behind": behind, "ahead": ahead},
                )
            )
    return findings


def truncate(s: str, width: int = 50) -> str:
    return s if len(s) <= width else s[: width - 1] + "…"


RULES: dict[str, Callable[[Path], list[Finding]]] = {
    "large-blobs": rule_large_blobs,
    "old-branches": rule_old_branches,
    "secrets": rule_secrets,
    "untracked-files": rule_untracked_files,
    "working-tree": rule_working_tree,
    "remote-sync": rule_remote_sync,
}
