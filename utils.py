"""
GitHub API 辅助函数模块
处理所有与 GitHub API 的通信
"""

import os
import logging
import asyncio
from datetime import datetime
from typing import Optional

import httpx
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# GitHub API 配置
GITHUB_API_BASE = "https://api.github.com"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# Semantic Scholar API 配置
SEMANTIC_SCHOLAR_API_BASE = "https://api.semanticscholar.org/graph/v1"

# 需要过滤的目录和文件
IGNORED_DIRS = {".git", "node_modules", "__pycache__", ".idea", ".vscode", "venv", ".venv"}
IGNORED_EXTENSIONS = {
    # 图片
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".ico", ".webp",
    # 视频
    ".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm",
    # 音频
    ".mp3", ".wav", ".ogg", ".flac", ".aac",
    # 文档
    ".pdf", ".zip", ".tar", ".gz", ".7z", ".rar",
    # 字体
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
}

# 默认文件类型过滤器
DEFAULT_FILTER_EXT = ['.py', '.md', '.yaml', '.json', '.yml', '.txt', '.toml', '.ini', '.cfg', '.conf']


def get_headers() -> dict:
    """获取 HTTP 请求头，包含可选的认证 Token"""
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "github-scout-mcp",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    return headers


def parse_repo_url(repo_url: str) -> tuple[str, str]:
    """
    解析仓库 URL，提取 owner 和 repo name

    Args:
        repo_url: GitHub 仓库 URL (支持多种格式)

    Returns:
        (owner, repo) 元组

    Examples:
        >>> parse_repo_url("https://github.com/anthropics/claude-code")
        ("anthropics", "claude-code")
        >>> parse_repo_url("anthropics/claude-code")
        ("anthropics", "claude-code")
    """
    # 清理 URL 前缀
    url = repo_url.strip()
    if url.startswith("https://github.com/"):
        url = url.replace("https://github.com/", "")
    elif url.startswith("http://github.com/"):
        url = url.replace("http://github.com/", "")
    elif url.startswith("github.com/"):
        url = url.replace("github.com/", "")

    # 移除尾部的 .git
    if url.endswith(".git"):
        url = url[:-4]

    parts = url.split("/")
    if len(parts) != 2:
        raise ValueError(f"无效的仓库 URL 格式: {repo_url}")

    return parts[0], parts[1]


async def fetch_github(endpoint: str, params: Optional[dict] = None) -> dict:
    """
    发送 GitHub API 请求

    Args:
        endpoint: API 端点 (不含基础 URL)
        params: 可选的查询参数

    Returns:
        JSON 响应数据

    Raises:
        ValueError: 404 或其他错误
    """
    url = f"{GITHUB_API_BASE}/{endpoint}"
    headers = get_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, params=params, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ValueError(f"资源未找到: {endpoint}")
            elif e.response.status_code == 403:
                raise ValueError(f"API 速率限制或权限不足，请在 .env 中配置 GITHUB_TOKEN")
            elif e.response.status_code == 401:
                raise ValueError(f"认证失败，请检查 GITHUB_TOKEN")
            else:
                raise ValueError(f"GitHub API 错误 ({e.response.status_code}): {e.response.text}")
        except httpx.RequestError as e:
            raise ValueError(f"网络请求失败: {str(e)}")


async def get_repo_info(owner: str, repo: str) -> dict:
    """获取仓库基本信息"""
    logger.info(f"获取仓库信息: {owner}/{repo}")
    return await fetch_github(f"repos/{owner}/{repo}")


async def get_last_commit(owner: str, repo: str) -> dict:
    """获取最后一次提交信息"""
    logger.info(f"获取最近提交: {owner}/{repo}")
    # 获取默认分支的最近一次提交
    commits = await fetch_github(f"repos/{owner}/{repo}/commits", params={"per_page": 1})
    if commits:
        return commits[0]
    return {}


async def get_repo_contents(owner: str, repo: str, path: str = "") -> list:
    """
    获取仓库目录内容

    Args:
        owner: 仓库所有者
        repo: 仓库名
        path: 目录路径（空字符串表示根目录）

    Returns:
    """
    logger.info(f"获取目录内容: {owner}/{repo}/{path if path else '(根目录)'}")
    return await fetch_github(f"repos/{owner}/{repo}/contents/{path}")


def should_ignore(name: str, is_dir: bool) -> bool:
    """
    检查是否应该忽略某个文件或目录

    Args:
        name: 文件/目录名
        is_dir: 是否是目录

    Returns:
        True 如果应该忽略
    """
    name_lower = name.lower()

    # 检查目录
    if is_dir:
        return name_lower in IGNORED_DIRS

    # 检查文件扩展名
    _, ext = os.path.splitext(name)
    return ext.lower() in IGNORED_EXTENSIONS


def should_filter_by_ext(name: str, allowed_ext: Optional[list] = None) -> bool:
    """
    检查文件是否在允许的扩展名列表中

    Args:
        name: 文件名
        allowed_ext: 允许的扩展名列表，默认使用 DEFAULT_FILTER_EXT

    Returns:
        True 如果文件扩展名在列表中
    """
    if allowed_ext is None:
        allowed_ext = DEFAULT_FILTER_EXT

    _, ext = os.path.splitext(name)
    return ext.lower() in [e.lower() for e in allowed_ext]


def calculate_potential_score(stars: int, created_at: str) -> float:
    """
    计算仓库潜力评分（Stars / 仓库创建天数）

    Args:
        stars: Star 数量
        created_at: 仓库创建时间 ISO 格式

    Returns:
        潜力评分（每天获得的 Stars）
    """
    try:
        created_date = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        now = datetime.now(created_date.tzinfo)
        days = (now - created_date).days
        if days <= 0:
            return float(stars)
        return round(stars / days, 2)
    except (ValueError, TypeError):
        return 0.0


async def search_github_repos(
    query: str,
    language: str = "Python",
    sort: str = "stars",
    per_page: int = 10
) -> list[dict]:
    """
    搜索 GitHub 仓库

    Args:
        query: 搜索关键词
        language: 编程语言筛选
        sort: 排序方式 (stars, updated, forks)
        per_page: 返回结果数量

    Returns:
        仓库信息列表，包含潜力评分

    Raises:
        ValueError: 422 查询语法错误
    """
    logger.info(f"搜索 GitHub 仓库: query={query}, language={language}, sort={sort}")

    # 构建查询参数
    search_query = f"{query}+language:{language}"
    params = {"q": search_query, "sort": sort, "per_page": per_page}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{GITHUB_API_BASE}/search/repositories",
                headers=get_headers(),
                params=params,
                timeout=30.0
            )

            if response.status_code == 422:
                error_data = response.json()
                message = error_data.get("message", "")
                raise ValueError(
                    f"查询语法错误: {message}\n"
                    f"提示: GitHub 搜索使用特定语法，如 'audio agent' 搜索包含这些关键词的仓库"
                )

            response.raise_for_status()
            data = response.json()
            items = data.get("items", [])

            # 计算每个仓库的潜力评分
            for item in items:
                item["potential_score"] = calculate_potential_score(
                    item.get("stargazers_count", 0),
                    item.get("created_at", "")
                )

            return items

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                raise ValueError("API 速率限制，请配置 GITHUB_TOKEN 以提高限制")
            raise ValueError(f"GitHub API 错误 ({e.response.status_code})")
        except httpx.RequestError as e:
            raise ValueError(f"网络请求失败: {str(e)}")


async def get_release_downloads(owner: str, repo: str) -> int:
    """
    获取仓库所有 Release 的下载总量

    Args:
        owner: 仓库所有者
        repo: 仓库名

    Returns:
        所有 Release assets 的下载总数
    """
    logger.info(f"获取 Release 下载量: {owner}/{repo}")

    try:
        releases = await fetch_github(f"repos/{owner}/{repo}/releases")
        total_downloads = 0

        for release in releases:
            assets = release.get("assets", [])
            for asset in assets:
                total_downloads += asset.get("download_count", 0)

        return total_downloads

    except ValueError as e:
        if "资源未找到" in str(e):
            return 0
        raise e


async def search_papers(query: str, limit: int = 5) -> list[dict]:
    """
    在 Semantic Scholar 搜索学术论文

    Args:
        query: 搜索关键词
        limit: 返回结果数量

    Returns:
        论文信息列表，包含标题、作者、年份等
    """
    logger.info(f"搜索学术论文: {query}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SEMANTIC_SCHOLAR_API_BASE}/paper/search",
                params={"query": query, "limit": limit},
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
            papers = data.get("data", [])

            # 格式化返回结果
            result = []
            for paper in papers:
                result.append({
                    "paper_id": paper.get("paperId", ""),
                    "title": paper.get("title", ""),
                    "year": paper.get("year", ""),
                    "authors": [a.get("name", "") for a in paper.get("authors", [])[:3]],
                    "citation_count": paper.get("citationCount", 0),
                    "url": paper.get("url", ""),
                })

            return result

    except httpx.RequestError as e:
        logger.warning(f"Semantic Scholar API 请求失败: {e}")
        return []


async def get_paper_citations(paper_id: str) -> dict:
    """
    获取论文的引用统计信息

    Args:
        paper_id: Semantic Scholar 论文 ID

    Returns:
        引用统计，包含总引用数和重要引用数
    """
    logger.info(f"获取论文引用: {paper_id}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SEMANTIC_SCHOLAR_API_BASE}/paper/{paper_id}",
                params={"fields": "citationCount,influentialCitationCount"},
                timeout=30.0
            )
            response.raise_for_status()
            paper = response.json()

            return {
                "citation_count": paper.get("citationCount", 0),
                "influential_citation_count": paper.get("influentialCitationCount", 0),
                "title": paper.get("title", ""),
            }

    except httpx.RequestError as e:
        logger.warning(f"获取论文引用失败: {e}")
        return {}


async def fetch_single_repo(repo_url: str) -> dict:
    """
    获取单个仓库的详细信息

    Args:
        repo_url: 仓库 URL

    Returns:
        仓库信息字典，失败时返回包含错误信息的字典
    """
    try:
        owner, repo = parse_repo_url(repo_url)
        info = await get_repo_info(owner, repo)

        return {
            "success": True,
            "owner": owner,
            "repo": repo,
            "stars": info.get("stargazers_count", 0),
            "forks": info.get("forks_count", 0),
            "open_issues": info.get("open_issues_count", 0),
            "created_at": info.get("created_at", ""),
            "updated_at": info.get("updated_at", ""),
            "description": info.get("description", ""),
            "language": info.get("language", ""),
            "url": repo_url,
        }

    except ValueError as e:
        logger.warning(f"获取仓库信息失败: {repo_url} - {e}")
        return {
            "success": False,
            "url": repo_url,
            "error": str(e),
        }


async def batch_fetch_repos(repo_urls: list[str], max_concurrent: int = 5) -> list[dict]:
    """
    批量获取多个仓库信息

    Args:
        repo_urls: 仓库 URL 列表
        max_concurrent: 最大并发数

    Returns:
        仓库信息列表
    """
    logger.info(f"批量获取仓库信息: {len(repo_urls)} 个仓库，最大并发 {max_concurrent}")

    semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_with_semaphore(url: str) -> dict:
        async with semaphore:
            return await fetch_single_repo(url)

    results = await asyncio.gather(
        *[fetch_with_semaphore(url) for url in repo_urls],
        return_exceptions=True
    )

    # 处理异常结果
    processed = []
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"批量请求异常: {result}")
            continue
        processed.append(result)

    return processed


def search_in_file(content: str, keywords: list, context_lines: int = 10) -> str:
    """
    在内容中搜索关键词，返回匹配行的上下文

    Args:
        content: 文件内容字符串
        keywords: 关键词列表
        context_lines: 上下文行数（前后各多少行），默认 10 行

    Returns:
        格式化后的搜索结果，包含匹配行的上下文

    Examples:
        >>> content = "line1\\nline2\\ndef hello():\\n    pass\\nline5"
        >>> search_in_file(content, ["def hello"])
        "...[上下文省略]...\\ndef hello():\\n    pass\\n...[上下文省略]..."
    """
    if not content or not keywords:
        return ""

    lines = content.split('\n')
    total_lines = len(lines)

    # 收集所有匹配行的索引
    matches = []
    for i, line in enumerate(lines):
        line_lower = line.lower()
        for keyword in keywords:
            keyword_lower = keyword.lower()
            if keyword_lower in line_lower:
                matches.append(i)
                break

    if not matches:
        return "未找到匹配关键词的内容"

    # 合并重叠的上下文区域
    blocks = []
    current_start = max(0, matches[0] - context_lines)
    current_end = min(total_lines, matches[0] + context_lines + 1)

    for i in range(1, len(matches)):
        match_pos = matches[i]
        # 如果当前匹配位置与上一个块重叠，扩展块的 end
        if match_pos - context_lines <= current_end:
            current_end = min(total_lines, match_pos + context_lines + 1)
        else:
            # 不重叠，保存当前块并开始新块
            blocks.append((current_start, current_end))
            current_start = max(0, match_pos - context_lines)
            current_end = min(total_lines, match_pos + context_lines + 1)

    # 保存最后一个块
    blocks.append((current_start, current_end))

    # 构建结果
    result_parts = []
    for start, end in blocks:
        # 添加省略标记（如果不是文件开头）
        if start > 0:
            result_parts.append(f"\n... [前文省略 {start} 行] ...\n")
        else:
            result_parts.append("\n")

        # 添加上下文内容
        for i in range(start, end):
            line_num = i + 1
            marker = ">>>" if i in matches else "   "
            result_parts.append(f"{marker} {line_num:4d} | {lines[i]}")

        # 添加省略标记（如果不是文件结尾）
        if end < total_lines:
            result_parts.append(f"\n... [后文省略 {total_lines - end} 行] ...\n")

    return '\n'.join(result_parts)
