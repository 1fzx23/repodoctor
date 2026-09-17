# 🩺 RepoDoctor

Git 仓库健康诊断工具。扫描本地仓库，发现历史大文件、长期未更新的分支、潜在敏感信息、未跟踪文件、未提交改动以及落后于远程的分支，并生成可读的诊断报告。

## 功能特性

- **综合扫描** (`scan`)：一键运行全部诊断规则，彩色终端摘要。
- **大文件检测** (`large-blobs`)：基于 git blob 大小，找出历史中的“肥胖”对象。
- **旧分支清理** (`old-branches` / `clean`)：列出或删除长期未更新、且已合并的分支。
- **敏感信息扫描** (`secrets`)：基于正则启发式，检查工作区文件中的疑似密钥、token、私钥等。
- **工作区检查**：提醒未跟踪文件、未提交改动、本地分支落后于远程。
- **多种输出**：终端彩色报告、JSON、Markdown，方便集成到 CI。
- **零第三方依赖**：仅使用 Python 标准库 + 系统 `git`。

## 安装

### 从源码安装

```bash
git clone https://github.com/1fzx23/repodoctor.git
cd repodoctor
pip install -e .
```

安装后全局可用：

```bash
repodoctor --version
```

### 直接运行（无需安装）

```bash
python -m repodoctor.cli scan
```

## 使用方法

### 综合扫描

```bash
# 扫描当前目录的 git 仓库
repodoctor scan

# 扫描指定仓库
repodoctor -C /path/to/repo scan

# 排除 secrets 检查
repodoctor scan -e secrets

# 仅检查大文件和旧分支
repodoctor scan -r large-blobs -r old-branches

# 导出 Markdown 报告
repodoctor scan -o report.md
```

### 查找历史大文件

```bash
# 默认阈值 1MB
repodoctor large-blobs

# 自定义阈值 2MB
repodoctor large-blobs -t 2
```

### 查找旧分支

```bash
# 默认 90 天
repodoctor old-branches

# 自定义 60 天
repodoctor old-branches -d 60
```

### 扫描敏感信息

```bash
repodoctor secrets
```

当前支持检测：AWS Access Key、GitHub Token、Slack Token、私钥、通用 API Key、密码赋值、JWT 等。

> ⚠️ 本功能基于正则启发式，适合日常自查，不能替代专业 secret scanner（如 `git-secrets`、`truffleHog`）。

### 生成分报告

```bash
repodoctor report
repodoctor report -f json
repodoctor report -f md -o health.md
```

### 清理旧分支

```bash
# 预览会删除哪些分支（dry-run）
repodoctor clean

# 真正删除 90 天未更新且已合并到 main 的分支
repodoctor clean -d 90 --default-branch main --yes
```

## 诊断规则说明

| 规则 | 级别 | 说明 |
|------|------|------|
| `large-blobs` | warning | 历史 blob 超过阈值，可能导致 clone 变慢 |
| `old-branches` | warning | 分支超过阈值天数未更新 |
| `secrets` | error | 工作区文件疑似包含敏感信息 |
| `untracked-files` | info | 存在未跟踪文件 |
| `working-tree` | warning | 工作区有未提交改动 |
| `remote-sync` | warning | 本地分支落后于远程 |

## 退出码

| 退出码 | 含义 |
|--------|------|
| 0 | 一切正常，或无问题 |
| 1 | 参数错误或不是有效 git 仓库 |
| 2 | 发现 warning 或 error |

## 开发

```bash
# 本地安装可编辑版本
pip install -e .

# 对当前仓库跑综合扫描
repodoctor scan -v
```

## License

MIT © 1fzx23
