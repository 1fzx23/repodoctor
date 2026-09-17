"""报告输出格式：终端、JSON、Markdown。"""

from __future__ import annotations

import json
from pathlib import Path

from .core import Report
from .rules import Finding
from .utils import Colors


def print_console(report: Report, verbose: bool = False) -> None:
    """彩色终端输出。"""
    counts = report.counts
    print()
    print(f"{Colors.bold}{Colors.cyan}🩺 RepoDoctor 诊断报告{Colors.reset}")
    print(f"{Colors.dim}仓库：{report.repo}{Colors.reset}")
    print(f"{Colors.dim}耗时：{report.elapsed_seconds:.2f}s  |  "
          f"info: {counts['info']}  warning: {counts['warning']}  error: {counts['error']}{Colors.reset}")
    print()

    if not report.findings:
        print(f"{Colors.green}✓ 没有发现任何问题，仓库非常健康。{Colors.reset}")
        return

    for f in report.findings:
        print(f.format(verbose=verbose))

    print()
    if counts["error"]:
        color = Colors.red
        face = "🚨"
    elif counts["warning"]:
        color = Colors.yellow
        face = "⚠️"
    else:
        color = Colors.green
        face = "✓"
    print(f"{color}{face} 诊断完成：{counts['error']} 个错误，{counts['warning']} 个警告，{counts['info']} 条提示。{Colors.reset}")


def to_dict(report: Report) -> dict:
    """将报告序列化为字典。"""
    return {
        "repo": str(report.repo),
        "elapsed_seconds": report.elapsed_seconds,
        "summary": report.counts,
        "ok": report.ok,
        "findings": [
            {
                "rule": f.rule,
                "severity": f.severity,
                "message": f.message,
                "details": f.details,
            }
            for f in report.findings
        ],
    }


def to_json(report: Report, indent: int = 2) -> str:
    """JSON 字符串。"""
    return json.dumps(to_dict(report), ensure_ascii=False, indent=indent, default=str)


def to_markdown(report: Report) -> str:
    """Markdown 报告。"""
    lines = [
        "# RepoDoctor 诊断报告",
        "",
        f"- **仓库**：`{report.repo}`",
        f"- **耗时**：{report.elapsed_seconds:.2f}s",
        f"- **结果**：error {report.counts['error']} / warning {report.counts['warning']} / info {report.counts['info']}",
        "",
        "## 发现项",
        "",
    ]
    if not report.findings:
        lines.append("✅ 没有发现任何问题。")
    else:
        lines.append("| 规则 | 级别 | 描述 |")
        lines.append("|------|------|------|")
        for f in report.findings:
            lines.append(f"| {f.rule} | {f.severity} | {f.message} |")
    lines.append("")
    return "\n".join(lines)


def save_report(report: Report, path: Path, fmt: str) -> None:
    """保存报告到文件。"""
    path = Path(path)
    if fmt == "json":
        path.write_text(to_json(report), encoding="utf-8")
    elif fmt == "md":
        path.write_text(to_markdown(report), encoding="utf-8")
    else:
        raise ValueError(f"不支持的报告格式：{fmt}")
