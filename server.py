"""
GitHub Scout MCP Server
帮助 LLM 快速调研和分析 GitHub 仓库结构与质量
"""

import asyncio
import httpx
import logging
from datetime import datetime

from mcp.server.fastmcp import FastMCP
from utils import (
    parse_repo_url,
    get_repo_info,
    get_last_commit,
    get_repo_contents,
    should_ignore,
)

# 初始化 MCP Server
mcp = FastMCP("github-scout")

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def format_date(date_str: str) -> str:
    """格式化 ISO 日期字符串为可读格式"""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except ValueError:
        return date_str


@mcp.tool()
async def get_repo_health(repo_url: str) -> str:
    """
    快速评估项目活跃度，获取仓库关键指标

    Args:
        repo_url: GitHub 仓库 URL

    Returns:
        格式化的仓库健康报告，包含 Stars、Fork 数、Issues 数和最后提交时间

    Examples:
        >>> await get_repo_health("https://github.com/anthropics/claude-code")
        "⭐ Stars: 12,345 | 🍴 Forks: 1,234 | 🐛 Issues: 56 | 最后提交: 2024-01-15"
    """
    logger.info(f"开始评估仓库健康: {repo_url}")

    try:
        owner, repo = parse_repo_url(repo_url)
    except ValueError as e:
        return f"错误: {e}"

    try:
        # 并行获取仓库信息和最近提交
        repo_info, last_commit = await asyncio.gather(
            get_repo_info(owner, repo),
            get_last_commit(owner, repo)
        )

        # 提取关键指标
        stars = repo_info.get("stargazers_count", 0)
        forks = repo_info.get("forks_count", 0)
        open_issues = repo_info.get("open_issues_count", 0)

        # 获取最后提交时间
        last_commit_date = ""
        if last_commit:
            commit_date = last_commit.get("commit", {}).get("committer", {}).get("date", "")
            if commit_date:
                last_commit_date = format_date(commit_date)

        # 获取 License
        license_info = repo_info.get("license")
        license_id = license_info.get("spdx_id", "N/A") if license_info else "N/A"

        # 构建健康报告
        report = f"""
## 仓库健康报告: {owner}/{repo}

| 指标 | 数量 |
|------|------|
| Stars | {stars:,} |
| Forks | {forks:,} |
| Open Issues | {open_issues:,} |
| License | {license_id} |

### 最后活跃

最后提交时间: {last_commit_date or "未知"}

默认分支: {repo_info.get('default_branch', 'main')}

---
*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
        logger.info(f"仓库健康评估完成: {owner}/{repo}")
        return report

    except ValueError as e:
        logger.error(f"获取仓库信息失败: {e}")
        return f"错误: {e}"
    except Exception as e:
        logger.exception(f"未知错误: {e}")
        return f"错误: 处理请求时发生未知错误 - {str(e)}"


async def build_tree(
    owner: str,
    repo: str,
    path: str,
    prefix: str,
    max_depth: int,
    current_depth: int
) -> str:
    """
    递归构建目录树

    Args:
        owner: 仓库所有者
        repo: 仓库名
        path: 当前路径
        prefix: 当前行的前缀符号
        max_depth: 最大递归深度
        current_depth: 当前深度

    Returns:
        格式化目录树字符串
    """
    if current_depth > max_depth:
        return ""

    lines = []

    try:
        contents = await get_repo_contents(owner, repo, path)

        # 过滤掉忽略的文件和目录
        items = [
            item for item in contents
            if not should_ignore(item["name"], item["type"] == "dir")
        ]

        # 按目录优先、字母顺序排序
        items.sort(key=lambda x: (x["type"] != "dir", x["name"].lower()))

        for i, item in enumerate(items):
            is_last = (i == len(items) - 1)
            name = item["name"]
            item_type = item["type"]

            # 根据类型添加不同的前缀
            if item_type == "dir":
                symbol = "📁 "
                new_prefix = prefix + ("    " if is_last else "│   ")
            else:
                symbol = "📄 "
                new_prefix = prefix + "    "

            # 添加当前行
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{symbol}{name}")

            # 递归处理子目录
            if item_type == "dir" and current_depth < max_depth:
                subtree = await build_tree(
                    owner, repo, item["path"], new_prefix, max_depth, current_depth + 1
                )
                lines.append(subtree)

    except Exception as e:
        logger.warning(f"获取目录内容失败 {path}: {e}")

    return "\n".join(lines)


@mcp.tool()
async def analyze_repo_structure(repo_url: str, max_depth: int = 2) -> str:
    """
    获取项目目录树结构

    Args:
        repo_url: GitHub 仓库 URL
        max_depth: 最大递归深度 (默认 2)

    Returns:
        ASCII 格式的目录树字符串

    Examples:
        >>> await analyze_repo_structure("https://github.com/anthropics/claude-code")
        "📁 claude-code/\n├── 📁 src/\n│   ├── 📄 main.py\n│   └── 📄 utils.py\n└── 📄 README.md"
    """
    logger.info(f"开始分析仓库结构: {repo_url}, 最大深度: {max_depth}")

    try:
        owner, repo = parse_repo_url(repo_url)
    except ValueError as e:
        return f"错误: {e}"

    try:
        # 获取仓库信息验证存在
        repo_info = await get_repo_info(owner, repo)
        full_name = repo_info.get("full_name", f"{owner}/{repo}")

        # 构建目录树
        tree = await build_tree(owner, repo, "", "", max_depth, 0)

        header = f"""
## 📂 仓库结构: {full_name}

```
📁 {repo}/
{tree}
```

**说明**:
- 📁 表示目录
- 📄 表示文件
- 已自动过滤: .git, node_modules, __pycache__, .idea, .vscode 等
- 当前深度限制: {max_depth} 层
"""
        logger.info(f"仓库结构分析完成: {full_name}")
        return header

    except ValueError as e:
        logger.error(f"分析仓库结构失败: {e}")
        return f"错误: {e}"
    except Exception as e:
        logger.exception(f"未知错误: {e}")
        return f"错误: 处理请求时发生未知错误 - {str(e)}"


@mcp.tool()
async def fetch_critical_logic(repo_url: str, file_paths: list[str]) -> str:
    """
    读取指定文件的核心代码

    Args:
        repo_url: GitHub 仓库 URL
        file_paths: 要读取的文件路径列表 (相对于仓库根目录)

    Returns:
        文件内容字符串，大文件会截取前 200 行和最后 50 行

    Examples:
        >>> await fetch_critical_logic(
        ...     "https://github.com/anthropics/claude-code",
        ...     ["src/main.py", "src/utils.py"]
        ... )
    """
    logger.info(f"开始读取关键文件: {repo_url}, 文件数: {len(file_paths)}")

    try:
        owner, repo = parse_repo_url(repo_url)
    except ValueError as e:
        return f"错误: {e}"

    result_parts = []

    for file_path in file_paths:
        try:
            logger.info(f"读取文件: {owner}/{repo}/{file_path}")

            # 获取文件内容
            from utils import fetch_github
            content = await fetch_github(f"repos/{owner}/{repo}/contents/{file_path}")

            # 获取文件内容 (需要使用 raw URL)
            raw_url = content.get("download_url")
            if not raw_url:
                # 可能是目录或子模块
                result_parts.append(f"\n### ❌ {file_path}\n无法读取: 可能是目录")
                continue

            async with httpx.AsyncClient() as client:
                response = await client.get(raw_url, timeout=30.0)
                response.raise_for_status()
                text_content = response.text

            # 获取文件大小信息
            size = content.get("size", 0)
            encoding = content.get("encoding", "base64")

            # 检查是否需要截断
            lines = text_content.split("\n")
            total_lines = len(lines)

            header = f"\n### 📄 {file_path}\n"
            header += f"- **总行数**: {total_lines}\n"
            header += f"- **大小**: {size} bytes\n"

            if total_lines <= 500:
                # 不需要截断
                header += "- **完整内容**:\n"
                body = f"\n```\n{text_content}\n```\n"
            else:
                # 需要截断
                header += f"- **截取内容**: 前 200 行 + 后 50 行\n"
                truncated = (
                    "\n".join(lines[:200])
                    + "\n\n... [中间内容省略，共 "
                    + f"{total_lines - 250} 行] ...\n\n"
                    + "\n".join(lines[-50:])
                )
                body = f"\n```\n{truncated}\n```\n"

            result_parts.append(header + body)

        except ValueError as e:
            result_parts.append(f"\n### ❌ {file_path}\n错误: {e}")
        except Exception as e:
            logger.error(f"读取文件失败 {file_path}: {e}")
            result_parts.append(f"\n### ❌ {file_path}\n错误: {str(e)}")

    return f"""## 🔍 关键代码分析

{chr(10).join(result_parts)}

---
*共读取 {len(file_paths)} 个文件*
"""


# 启动服务器
if __name__ == "__main__":
    mcp.run()
