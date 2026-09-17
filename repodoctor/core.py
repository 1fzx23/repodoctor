"""RepoDoctor 核心引擎：运行诊断规则并聚合结果。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .rules import RULES, Finding


@dataclass
class Report:
    """一次诊断扫描的完整报告。"""

    repo: Path
    findings: list[Finding] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    @property
    def counts(self) -> dict[str, int]:
        return {
            "info": sum(1 for f in self.findings if f.severity == "info"),
            "warning": sum(1 for f in self.findings if f.severity == "warning"),
            "error": sum(1 for f in self.findings if f.severity == "error"),
        }

    @property
    def ok(self) -> bool:
        return self.counts["warning"] == 0 and self.counts["error"] == 0


class RepoDoctor:
    """Git 仓库健康诊断器。"""

    def __init__(self, repo: Path | str, rules: dict[str, Callable[[Path], list[Finding]]] | None = None):
        self.repo = Path(repo).expanduser().resolve()
        self.rules = rules or RULES

    def run(
        self,
        only: list[str] | None = None,
        exclude: list[str] | None = None,
    ) -> Report:
        """运行诊断规则，返回报告。"""
        import time

        start = time.perf_counter()
        findings: list[Finding] = []
        names = only or list(self.rules.keys())
        if exclude:
            names = [n for n in names if n not in exclude]

        for name in names:
            fn = self.rules.get(name)
            if not fn:
                findings.append(Finding(name, "error", f"未知诊断规则：{name}"))
                continue
            try:
                findings.extend(fn(self.repo))
            except Exception as exc:  # noqa: BLE001
                findings.append(Finding(name, "error", f"规则执行失败：{exc}"))

        elapsed = time.perf_counter() - start
        return Report(repo=self.repo, findings=findings, elapsed_seconds=elapsed)

    def clean_branches(
        self,
        days: int = 90,
        merged_only: bool = True,
        dry_run: bool = True,
        default_branch: str = "main",
    ) -> list[str]:
        """返回可删除的旧分支列表；非 dry_run 时执行删除。"""
        from .rules import rule_old_branches
        from .utils import run_git

        old = rule_old_branches(self.repo, days=days)
        to_delete: list[str] = []
        for finding in old:
            branch = finding.details.get("branch") if finding.details else None
            if not branch:
                continue
            if branch == default_branch:
                continue
            if merged_only:
                result = run_git(self.repo, ["branch", "--merged", default_branch], check=False)
                merged = {b.strip() for b in result.stdout.splitlines()}
                if branch not in merged:
                    continue
            to_delete.append(branch)

        if not dry_run:
            for branch in to_delete:
                run_git(self.repo, ["branch", "-D", branch], check=False)
        return to_delete
