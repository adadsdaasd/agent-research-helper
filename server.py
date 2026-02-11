"""
GitHub Scout MCP Server
帮助 LLM 快速调研和分析 GitHub 仓库结构与质量
"""

import asyncio
import httpx
import logging
from datetime import datetime
from typing import Optional

from mcp.server.fastmcp import FastMCP
from utils import (
    parse_repo_url,
    get_repo_info,
    get_last_commit,
    get_repo_contents,
    should_ignore,
    should_filter_by_ext,
    search_in_file,
    search_github_repos,
    get_release_downloads,
    search_papers,
    get_paper_citations,
    batch_fetch_repos,
    calculate_potential_score,
    discover_and_evaluate,
    calculate_heuristic_score,
    SMART_MODE,
    DEFAULT_FILTER_EXT,
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


def analyze_star_trend(stars: int, forks: int, open_issues: int) -> str:
    """
    分析 Stars 趋势，返回简单描述

    Args:
        stars: Star 数量
        forks: Fork 数量
        open_issues: Open Issues 数量

    Returns:
        趋势描述字符串
    """
    if stars == 0:
        return "新仓库，暂无数据"

    # 计算 fork/star 比例
    fork_ratio = forks / stars if stars > 0 else 0

    # 计算 issue/star 比例
    issue_ratio = open_issues / stars if stars > 0 else 0

    # 生成趋势描述
    trend_parts = []

    # Fork 比例分析
    if fork_ratio > 0.5:
        trend_parts.append("社区参与度高（Fork 比例 > 50%）")
    elif fork_ratio > 0.2:
        trend_parts.append("社区参与度良好（Fork 比例 20%-50%）")
    elif fork_ratio > 0.05:
        trend_parts.append("社区参与度一般（Fork 比例 5%-20%）")
    else:
        trend_parts.append("社区参与度较低（Fork 比例 < 5%）")

    # Issue 处理情况
    if issue_ratio > 0.5:
        trend_parts.append("Issue 较多，可能需要更多维护")
    elif issue_ratio > 0.1:
        trend_parts.append("Issue 数量适中")
    else:
        trend_parts.append("Issue 较少，项目较稳定")

    # 总体活跃度评估
    if stars > 10000:
        trend_parts.append("热门项目（Stars > 10K）")
    elif stars > 1000:
        trend_parts.append("中等规模项目（Stars 1K-10K）")
    elif stars > 100:
        trend_parts.append("成长中项目（Stars 100-1K）")
    else:
        trend_parts.append("小型/新项目（Stars < 100）")

    return " | ".join(trend_parts)


@mcp.tool()
async def get_repo_health(repo_url: str) -> str:
    """
    快速评估项目活跃度，获取仓库关键指标

    Args:
        repo_url: GitHub 仓库 URL

    Returns:
        格式化的仓库健康报告，包含 Stars、Fork 数、Issues 数、Star 趋势分析和最后提交时间

    Examples:
        >>> await get_repo_health("https://github.com/anthropics/claude-code")
        "Stars: 65,964 | Fork 比例: 高 | Issue 比例: 适中"
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

        # 分析 Star 趋势
        trend = analyze_star_trend(stars, forks, open_issues)

        # 构建健康报告
        report = f"""
## 仓库健康报告: {owner}/{repo}

| 指标 | 数量 |
|------|------|
| Stars | {stars:,} |
| Forks | {forks:,} |
| Open Issues | {open_issues:,} |
| License | {license_id} |

### Star 趋势分析

{trend}

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
    current_depth: int,
    allowed_ext: Optional[list] = None
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
        allowed_ext: 允许的文件扩展名列表

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

        # 如果指定了扩展名过滤，只保留匹配的文件
        if allowed_ext is not None:
            items = [
                item for item in items
                if item["type"] == "dir" or should_filter_by_ext(item["name"], allowed_ext)
            ]

        # 按目录优先、字母顺序排序
        items.sort(key=lambda x: (x["type"] != "dir", x["name"].lower()))

        for i, item in enumerate(items):
            is_last = (i == len(items) - 1)
            name = item["name"]
            item_type = item["type"]

            # 根据类型添加不同的前缀
            if item_type == "dir":
                symbol = "[DIR] "
                new_prefix = prefix + ("    " if is_last else "|   ")
            else:
                symbol = "[FILE] "
                new_prefix = prefix + "    "

            # 添加当前行
            connector = "|-- " if is_last else "|-+ "
            lines.append(f"{prefix}{connector}{symbol}{name}")

            # 递归处理子目录
            if item_type == "dir" and current_depth < max_depth:
                subtree = await build_tree(
                    owner, repo, item["path"], new_prefix, max_depth, current_depth + 1, allowed_ext
                )
                lines.append(subtree)

    except Exception as e:
        logger.warning(f"获取目录内容失败 {path}: {e}")

    return "\n".join(lines)


@mcp.tool()
async def analyze_repo_structure(
    repo_url: str,
    max_depth: int = 2,
    filter_ext: Optional[list] = None
) -> str:
    """
    获取项目目录树结构

    Args:
        repo_url: GitHub 仓库 URL
        max_depth: 最大递归深度 (默认 2)
        filter_ext: 文件扩展名过滤器，默认只显示代码相关文件

    Returns:
        格式化的目录树字符串

    Examples:
        >>> await analyze_repo_structure("https://github.com/anthropics/claude-code")
        "[DIR] src/... [FILE] README.md..."
    """
    logger.info(f"开始分析仓库结构: {repo_url}, 最大深度: {max_depth}")

    # 默认过滤器
    if filter_ext is None:
        filter_ext = DEFAULT_FILTER_EXT.copy()

    try:
        owner, repo = parse_repo_url(repo_url)
    except ValueError as e:
        return f"错误: {e}"

    try:
        # 获取仓库信息验证存在
        repo_info = await get_repo_info(owner, repo)
        full_name = repo_info.get("full_name", f"{owner}/{repo}")

        # 构建目录树
        tree = await build_tree(owner, repo, "", "", max_depth, 0, filter_ext)

        header = f"""
## 仓库结构: {full_name}

```
{repo}/
{tree}
```

**说明**:
- [DIR] 表示目录
- [FILE] 表示文件
- 已自动过滤: .git, node_modules, __pycache__, .idea, .vscode, 图片/视频等
- 文件类型过滤器: {', '.join(filter_ext)}
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


async def fetch_file_content(owner: str, repo: str, file_path: str) -> str:
    """
    获取文件的原始内容

    Args:
        owner: 仓库所有者
        repo: 仓库名
        file_path: 文件路径

    Returns:
        文件内容字符串
    """
    from utils import fetch_github
    content = await fetch_github(f"repos/{owner}/{repo}/contents/{file_path}")

    raw_url = content.get("download_url")
    if not raw_url:
        raise ValueError(f"无法读取文件: {file_path}（可能是目录）")

    async with httpx.AsyncClient() as client:
        response = await client.get(raw_url, timeout=30.0)
        response.raise_for_status()
        return response.text


@mcp.tool()
async def fetch_logic_by_keywords(
    repo_url: str,
    file_path: str,
    keywords: list[str],
    context_lines: int = 10
) -> str:
    """
    根据关键词搜索文件中的相关代码

    Args:
        repo_url: GitHub 仓库 URL
        file_path: 文件路径（相对于仓库根目录）
        keywords: 关键词列表，用于搜索相关代码
        context_lines: 上下文行数（前后各多少行），默认 10 行

    Returns:
        包含关键词及其上下文的高亮代码片段

    Examples:
        >>> await fetch_logic_by_keywords(
        ...     "https://github.com/anthropics/claude-code",
        ...     "src/main.py",
        ...     ["def main", "class"]
        ... )
        "... def main(): ..."
    """
    logger.info(f"开始搜索关键词: {keywords} 在文件 {file_path} 中")

    try:
        owner, repo = parse_repo_url(repo_url)
    except ValueError as e:
        return f"错误: {e}"

    try:
        # 获取文件内容
        content = await fetch_file_content(owner, repo, file_path)

        # 搜索关键词
        search_result = search_in_file(content, keywords, context_lines)

        # 获取文件信息
        from utils import fetch_github
        file_info = await fetch_github(f"repos/{owner}/{repo}/contents/{file_path}")
        size = file_info.get("size", 0)
        lines = len(content.split('\n'))

        result = f"""
## 关键词搜索结果: {file_path}

**搜索关键词**: {', '.join(keywords)}
**上下文行数**: 前后各 {context_lines} 行
**文件总行数**: {lines}
**文件大小**: {size} bytes

---

### 代码片段

```
{search_result}
```

---
*使用 >>> 标记匹配行*
"""
        logger.info(f"关键词搜索完成: {file_path}")
        return result

    except ValueError as e:
        logger.error(f"搜索失败: {e}")
        return f"错误: {e}"
    except Exception as e:
        logger.exception(f"未知错误: {e}")
        return f"错误: 处理请求时发生未知错误 - {str(e)}"


@mcp.tool()
async def search_github_repos(
    query: str,
    language: str = "Python",
    sort: str = "stars",
    per_page: int = 10
) -> str:
    """
    搜索 GitHub 仓库并返回潜力评估

    Args:
        query: 搜索关键词
        language: 编程语言筛选 (默认 Python)
        sort: 排序方式 (stars, updated, forks，默认 stars)
        per_page: 返回结果数量 (默认 10)

    Returns:
        Markdown 格式的仓库列表表格

    Examples:
        >>> await search_github_repos("audio agent", language="Python", per_page=5)
    """
    logger.info(f"搜索仓库: {query}, 语言: {language}")

    try:
        repos = await search_github_repos(
            query=query,
            language=language,
            sort=sort,
            per_page=per_page
        )

        if not repos:
            return f"未找到符合条件的仓库，请尝试调整搜索关键词"

        # 构建 Markdown 表格
        table_rows = []
        for repo in repos:
            name = repo.get("full_name", "")
            description = repo.get("description", "") or "无描述"
            stars = repo.get("stargazers_count", 0)
            updated = repo.get("updated_at", "")[:10] if repo.get("updated_at") else "未知"
            potential = repo.get("potential_score", 0)
            url = repo.get("html_url", "")

            # 截断过长的描述
            if len(description) > 60:
                description = description[:57] + "..."

            table_rows.append(
                f"| [{name}]({url}) | {description} | {stars:,} | {updated} | {potential} |"
            )

        table_header = "| 仓库名 | 描述 | Stars | 更新日期 | 潜力评分 |\n"
        table_separator = "|--------|------|-------|----------|----------|\n"

        result = f"""
## GitHub 仓库搜索结果: "{query}"

**筛选条件**: 语言={language} | 排序={sort} | 数量={len(repos)}

### 潜力评分说明
- 潜力评分 = Stars / 仓库创建天数
- 反映项目的每日平均 Star 增长速度

### 搜索结果

{table_header}{table_separator}{''.join(table_rows)}

---
*提示: 配置 GITHUB_TOKEN 可提高 API 速率限制*
"""
        return result

    except ValueError as e:
        logger.error(f"搜索失败: {e}")
        return f"错误: {e}"
    except Exception as e:
        logger.exception(f"未知错误: {e}")
        return f"错误: 处理请求时发生未知错误 - {str(e)}"


@mcp.tool()
async def batch_analyze_repos(repo_urls: list[str]) -> str:
    """
    批量分析多个仓库的对比数据

    Args:
        repo_urls: 仓库 URL 列表

    Returns:
        Markdown 格式的对比表格

    Examples:
        >>> await batch_analyze_repos([
        ...     "https://github.com/owner/repo1",
        ...     "https://github.com/owner/repo2"
        ... ])
    """
    logger.info(f"批量分析仓库: {len(repo_urls)} 个")

    if not repo_urls:
        return "错误: 未提供仓库 URL 列表"

    # 限制并发数量
    max_concurrent = min(len(repo_urls), 5)

    try:
        results = await batch_fetch_repos(repo_urls, max_concurrent=max_concurrent)

        # 过滤成功获取的仓库
        success_repos = [r for r in results if r.get("success")]
        failed_repos = [r for r in results if not r.get("success")]

        if not success_repos:
            return f"错误: 未能获取任何仓库信息"

        # 构建对比表格
        table_rows = []
        for repo in success_repos:
            name = f"{repo['owner']}/{repo['repo']}"
            stars = repo.get("stars", 0)
            forks = repo.get("forks", 0)
            issues = repo.get("open_issues", 0)

            # 计算创建时长
            created_at = repo.get("created_at", "")
            age = "未知"
            if created_at:
                try:
                    created_date = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    now = datetime.now(created_date.tzinfo)
                    days = (now - created_date).days
                    if days > 365:
                        age = f"{days // 365}年{days % 365}天"
                    else:
                        age = f"{days}天"
                except ValueError:
                    pass

            table_rows.append(
                f"| [{name}](https://github.com/{name}) | {stars:,} | {forks:,} | {issues:,} | {age} |"
            )

        table_header = "| 仓库 | Stars | Forks | Open Issues | 创建时长 |\n"
        table_separator = "|--------|-------|-------|------------|----------|\n"

        result = f"""
## 仓库对比分析

| 指标 | 说明 |
|------|------|
| Stars | Star 数量，反映用户基数 |
| Forks | Fork 数量，反映代码复用 |
| Issues | Open Issue 数量 |
| 创建时长 | 仓库创建至今的时间 |

### 分析结果

{table_header}{table_separator}{''.join(table_rows)}
"""

        # 添加失败信息
        if failed_repos:
            failed_urls = [r.get("url", "") for r in failed_repos if r.get("url")]
            if failed_urls:
                result += f"\n**无法获取的仓库**: {', '.join(failed_urls)}\n"

        return result

    except Exception as e:
        logger.exception(f"批量分析失败: {e}")
        return f"错误: 处理请求时发生未知错误 - {str(e)}"


@mcp.tool()
async def get_project_intelligence(repo_url: str) -> str:
    """
    获取项目综合情报（Release 下载量 + 学术引用）

    Args:
        repo_url: GitHub 仓库 URL

    Returns:
        Markdown 格式的综合情报报告

    Examples:
        >>> await get_project_intelligence("https://github.com/owner/repo")
    """
    logger.info(f"获取项目情报: {repo_url}")

    try:
        owner, repo = parse_repo_url(repo_url)
    except ValueError as e:
        return f"错误: {e}"

    try:
        # 并行获取仓库信息、Release 下载量、搜索论文
        repo_info, releases_data, papers = await asyncio.gather(
            get_repo_info(owner, repo),
            get_release_downloads(owner, repo),
            search_papers(f"{owner} {repo}"),
            return_exceptions=True
        )

        # 处理异常
        if isinstance(releases_data, Exception):
            releases_data = 0
        if isinstance(papers, Exception):
            papers = []

        stars = repo_info.get("stargazers_count", 0)
        forks = repo_info.get("forks_count", 0)
        description = repo_info.get("description", "") or "无描述"
        language = repo_info.get("language", "") or "未知"
        updated_at = repo_info.get("updated_at", "")[:10] if repo_info.get("updated_at") else "未知"

        # 构建报告
        sections = []

        # 基本信息
        sections.append(f"""
## 项目基本信息

| 指标 | 值 |
|------|-----|
| 仓库 | [{owner}/{repo}](https://github.com/{owner}/{repo}) |
| Stars | {stars:,} |
| Forks | {forks:,} |
| 语言 | {language} |
| 最后更新 | {updated_at} |
| 描述 | {description} |
""")

        # Release 下载量
        sections.append(f"""
## Release 下载量

| 指标 | 值 |
|------|-----|
| 总下载量 | {releases_data:,} |

{"*注: 累计所有 Release assets 的下载次数*" if releases_data > 0 else "*注: 该项目暂无 Release 或下载统计*"}
""")

        # 学术引用
        if papers:
            paper_rows = []
            for paper in papers[:3]:  # 最多显示 3 篇
                title = paper.get("title", "")[:50]
                year = paper.get("year", "") or "未知"
                citations = paper.get("citation_count", 0)
                paper_url = paper.get("url", "")
                paper_rows.append(f"| [{title}]({paper_url}) | {year} | {citations} |")

            paper_header = "| 论文标题 | 年份 | 引用数 |\n|----------|------|--------|\n"

            # 获取引用统计
            citation_info = []
            for paper in papers[:2]:  # 获取前 2 篇的详细引用
                pid = paper.get("paper_id", "")
                if pid:
                    details = await get_paper_citations(pid)
                    if details:
                        citation_info.append(
                            f"**{details.get('title', '')[:40]}**: "
                            f"{details.get('citation_count', 0)} 引用, "
                            f"{details.get('influential_citation_count', 0)} 重要引用"
                        )

            sections.append(f"""
## 学术关联

| 维度 | 情况 |
|------|------|
| 关联论文数 | {len(papers)} 篇 |

### 主要论文

{paper_header}{''.join(paper_rows)}
""")

            if citation_info:
                sections.append(f"""
### 引用详情

- {chr(10).join(f'- {c}' for c in citation_info)}
""")
        else:
            sections.append("""
## 学术关联

未在主流学术库（Semantic Scholar）中检索到关联论文

可能原因:
- 项目较新，尚未被学术研究引用
- 项目非学术性质
- 使用了不同的项目名称
""")

        # 潜力评分
        created_at = repo_info.get("created_at", "")
        potential = calculate_potential_score(stars, created_at)

        sections.append(f"""
## 潜力评估

| 评分维度 | 值 |
|---------|-----|
| 潜力评分 | {potential} (Stars/天) |
| 活跃度 | {"高" if stars > 1000 else "中" if stars > 100 else "低"} |

---
*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
""")

        return '\n'.join(sections)

    except ValueError as e:
        logger.error(f"获取情报失败: {e}")
        return f"错误: {e}"
    except Exception as e:
        logger.exception(f"未知错误: {e}")
        return f"错误: 处理请求时发生未知错误 - {str(e)}"


@mcp.tool()
async def autonomous_discover(topic: str, max_repos: int = 15) -> str:
    """
    自主发现特定领域的 Agent 项目

    该工具会根据用户输入的研究主题，自动：
    1. 生成多语言搜索关键词（智能模式使用 LLM）
    2. 并行搜索 GitHub
    3. 去重并评估每个仓库
    4. 按质量评分排序返回

    Args:
        topic: 研究主题（如：音频、数字人、图像生成、LLM Agent）
        max_repos: 最大返回数量（默认 15，最大 30）

    Returns:
        Markdown 格式的智能评估报告

    Examples:
        >>> await autonomous_discover("音频 Agent", max_repos=10)
        >>> await autonomous_discover("数字人", max_repos=15)
    """
    logger.info(f"自主发现: topic='{topic}', max_repos={max_repos}")

    # 限制 max_repos
    max_repos = min(max(1, max_repos), 30)

    try:
        # Step 1-5: 发现与评估（在 utils.discover_and_evaluate 中完成）
        repos = await discover_and_evaluate(topic, max_repos)

        if not repos:
            return f"""
## 自主发现结果: {topic}

未找到相关项目，可能原因：
1. 主题过于冷门
2. GitHub 搜索限制（配置 GITHUB_TOKEN 可提高限制）
3. 智能模式未启用（配置 OPENAI_API_KEY 可启用）

建议：
- 尝试更宽泛的搜索词
- 检查主题拼写
- 或使用 basic_search 进行简单搜索
"""

        # 构建 Markdown 报告
        mode_note = "智能模式 (LLM 语义分析)" if SMART_MODE else "基础模式 (启发式评分)"

        # 构建表格
        table_rows = []
        for i, repo in enumerate(repos, 1):
            name = repo.get("full_name", "")
            score = repo.get("analysis_score", 0)
            summary = repo.get("analysis_summary", "")[:60]
            stars = repo.get("stargazers_count", 0)
            url = repo.get("html_url", "")

            # 评分颜色标记
            if score >= 80:
                score_emoji = "🟢"
            elif score >= 60:
                score_emoji = "🟡"
            elif score >= 40:
                score_emoji = "🟠"
            else:
                score_emoji = "🔴"

            table_rows.append(
                f"| {i} | [{name}]({url}) | {score_emoji} {score} | {summary} | {stars:,} |"
            )

        table_header = "| 排名 | 仓库 | 评分 | 摘要 | Stars |\n"
        table_separator = "|------|------|------|------|-------|\n"

        # 关键词信息
        keywords = repos[0].get("search_keywords", []) if repos else []
        keywords_str = ", ".join(keywords[:5]) if keywords else topic

        report = f"""
# 自主发现报告: {topic}

**运行模式**: {mode_note}
**搜索关键词**: {keywords_str}
**发现数量**: {len(repos)} 个项目

---

## 评分说明

| 评分范围 | 含义 |
|---------|------|
| 🟢 80-100 | 强烈推荐 - 高质量 Agent 项目 |
| 🟡 60-79 | 推荐 - 较好的相关项目 |
| 🟠 40-59 | 一般 - 可能相关 |
| 🔴 0-39 | 不推荐 - 可能不相关 |

---

## 发现结果

{table_header}{table_separator}{''.join(table_rows)}

---

## 详细信息

"""

        # 添加每个仓库的详细信息
        for i, repo in enumerate(repos[:5], 1):  # 只显示前5个的详细信息
            name = repo.get("full_name", "")
            score = repo.get("analysis_score", 0)
            summary = repo.get("analysis_summary", "")
            desc = repo.get("description", "") or "无描述"
            stars = repo.get("stargazers_count", 0)
            forks = repo.get("forks_count", 0)
            lang = repo.get("language", "") or "Unknown"
            url = repo.get("html_url", "")

            report += f"""
### {i}. {name}

- **评分**: {score}/100 | **Stars**: {stars:,} | **Forks**: {forks:,} | **语言**: {lang}
- **摘要**: {summary}
- **描述**: {desc}
- **链接**: [GitHub]({url})
"""

        report += f"""
---
*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*

**提示**:
- 配置 `OPENAI_API_KEY` 环境变量可启用智能模式，获得更准确的评分
- 配置 `GITHUB_TOKEN` 可提高 GitHub API 速率限制
"""

        return report

    except Exception as e:
        logger.exception(f"自主发现失败: {e}")
        return f"错误: 处理请求时发生未知错误 - {str(e)}"


# 启动服务器
if __name__ == "__main__":
    mcp.run()
