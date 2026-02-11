"""
GitHub API 辅助函数模块
处理所有与 GitHub API 的通信
"""

import os
import logging
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
                raise ValueError(f"API 速率限制或权限不足")
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
