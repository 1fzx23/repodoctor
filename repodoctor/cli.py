"""命令行入口。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .core import RepoDoctor
from .reporters import print_console, save_report, to_json, to_markdown
from .rules import RULES
from .utils import Colors, ensure_color, git_ok


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repodoctor",
        description="🩺 RepoDoctor — Git 仓库健康诊断工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  repodoctor scan                         # 综合扫描当前仓库
  repodoctor large-blobs -t 2             # 查找大于 2MB 的历史大文件
  repodoctor old-branches -d 60           # 查找 60 天未更新的分支
  repodoctor secrets                      # 扫描潜在敏感信息
  repodoctor report -o report.md          # 生成 Markdown 报告
  repodoctor clean -d 90 --yes            # 删除 90 天未更新且已合并的分支
        """,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-C", "--repo", default=".", help="目标 git 仓库目录（默认当前目录）")
    parser.add_argument("--no-color", action="store_true", help="禁用彩色输出")

    # 共享给子命令的 verbose 参数
    verbose_parent = argparse.ArgumentParser(add_help=False)
    verbose_parent.add_argument("-v", "--verbose", action="store_true", help="显示详细细节")

    sub = parser.add_subparsers(dest="command", required=True)

    # scan
    scan = sub.add_parser("scan", help="运行所有诊断规则并输出摘要", parents=[verbose_parent])
    scan.add_argument("-e", "--exclude", action="append", help="排除指定规则，可多次使用")
    scan.add_argument("-r", "--only", action="append", help="仅运行指定规则，可多次使用")
    scan.add_argument("-o", "--output", help="输出报告文件（.json 或 .md）")

    # large-blobs
    lb = sub.add_parser("large-blobs", help="查找历史中的大 blob", parents=[verbose_parent])
    lb.add_argument("-t", "--threshold", type=float, default=1.0, help="阈值（MB，默认 1.0）")

    # old-branches
    ob = sub.add_parser("old-branches", help="查找长期未更新的分支", parents=[verbose_parent])
    ob.add_argument("-d", "--days", type=int, default=90, help="天数阈值（默认 90）")

    # secrets
    sub.add_parser("secrets", help="扫描工作区中的潜在敏感信息", parents=[verbose_parent])

    # report
    rep = sub.add_parser("report", help="生成综合健康报告", parents=[verbose_parent])
    rep.add_argument("-f", "--format", choices=["console", "json", "md"], default="console", help="报告格式")
    rep.add_argument("-o", "--output", help="输出文件路径")
    rep.add_argument("-e", "--exclude", action="append", help="排除指定规则")

    # clean
    clean = sub.add_parser("clean", help="交互式清理旧分支", parents=[verbose_parent])
    clean.add_argument("-d", "--days", type=int, default=90, help="天数阈值")
    clean.add_argument("--merged-only", action="store_true", default=True, help="仅删除已合并分支")
    clean.add_argument("--no-merged-only", action="store_false", dest="merged_only", help="允许删除未合并分支")
    clean.add_argument("--default-branch", default="main", help="默认分支名（默认 main）")
    clean.add_argument("--yes", action="store_true", help="跳过确认直接删除")

    return parser


def run_cli(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    ensure_color(no_color=args.no_color)

    repo = Path(args.repo).expanduser().resolve()
    if not git_ok(repo):
        print(f"{Colors.red}错误：{repo} 不是有效的 git 仓库。{Colors.reset}", file=sys.stderr)
        return 1

    doctor = RepoDoctor(repo)

    if args.command == "scan":
        report = doctor.run(only=args.only, exclude=args.exclude)
        print_console(report, verbose=args.verbose)
        if args.output:
            fmt = "json" if args.output.endswith(".json") else "md"
            save_report(report, Path(args.output), fmt)
            print(f"\n{Colors.dim}报告已保存：{args.output}{Colors.reset}")
        return 0 if report.ok else 2

    if args.command == "large-blobs":
        from .rules import rule_large_blobs
        findings = rule_large_blobs(repo, threshold_mb=args.threshold)
        for f in findings:
            print(f.format(verbose=args.verbose))
        return 0 if not findings else 2

    if args.command == "old-branches":
        from .rules import rule_old_branches
        findings = rule_old_branches(repo, days=args.days)
        for f in findings:
            print(f.format(verbose=args.verbose))
        return 0 if not findings else 2

    if args.command == "secrets":
        from .rules import rule_secrets
        findings = rule_secrets(repo)
        for f in findings:
            print(f.format(verbose=args.verbose))
        return 0 if not findings else 2

    if args.command == "report":
        report = doctor.run(exclude=args.exclude)
        if args.format == "json":
            out = to_json(report)
        elif args.format == "md":
            out = to_markdown(report)
        else:
            print_console(report, verbose=args.verbose)
            out = ""
        if out:
            if args.output:
                Path(args.output).write_text(out, encoding="utf-8")
                print(f"报告已保存：{args.output}")
            else:
                print(out)
        return 0 if report.ok else 2

    if args.command == "clean":
        to_delete = doctor.clean_branches(
            days=args.days,
            merged_only=args.merged_only,
            dry_run=not args.yes,
            default_branch=args.default_branch,
        )
        if not to_delete:
            print(f"{Colors.green}✓ 没有需要清理的分支。{Colors.reset}")
            return 0
        print(f"{Colors.yellow}即将删除以下 {len(to_delete)} 个分支：{Colors.reset}")
        for b in to_delete:
            print(f"  - {b}")
        if args.yes:
            print(f"{Colors.green}已删除。{Colors.reset}")
        else:
            print(f"\n{Colors.dim}这是 dry-run，未执行删除。加 --yes 真正清理。{Colors.reset}")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
