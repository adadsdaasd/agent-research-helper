"""
GitHub API 辅助函数模块
处理所有与 GitHub API 的通信
包含：基础模式 + 智能模式（双重模式）
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

# ============== 配置 ==============
GITHUB_API_BASE = "https://api.github.com"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
SEMANTIC_SCHOLAR_API_BASE = "https://api.semanticscholar.org/graph/v1"

# LLM API 配置（支持 OpenAI、DeepSeek、MiniMax、Claude 等）
# 优先级：MINIMAX_API_KEY > OPENAI_API_KEY > ANTHROPIC_API_KEY
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY") or os.getenv("MINIMAX_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# API 类型检测与配置
API_TYPE = "unknown"
API_BASE_URL = "https://api.openai.com/v1"
API_MODEL = "gpt-3.5-turbo"

if MINIMAX_API_KEY:
    API_TYPE = "minimax"
    API_BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1")
    API_MODEL = os.getenv("MINIMAX_MODEL", "MiniMax-Text-01")
    OPENAI_API_KEY = MINIMAX_API_KEY
    logger.info(f"智能模式 (MiniMax): {API_MODEL} @ {API_BASE_URL}")
elif os.getenv("DEEPSEEK_API_KEY"):
    API_TYPE = "deepseek"
    API_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    API_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    OPENAI_API_KEY = os.getenv("DEEPSEEK_API_KEY")
    logger.info(f"智能模式 (DeepSeek): {API_MODEL} @ {API_BASE_URL}")
elif OPENAI_API_KEY:
    API_TYPE = "openai"
    API_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    API_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
    logger.info(f"智能模式 (OpenAI): {API_MODEL} @ {API_BASE_URL}")
elif ANTHROPIC_API_KEY:
    API_TYPE = "anthropic"
    API_BASE_URL = "https://api.anthropic.com"
    API_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    logger.info(f"智能模式 (Claude): {API_MODEL} @ {API_BASE_URL}")
else:
    API_TYPE = "none"
    logger.info("基础模式：无 LLM API Key，使用启发式评分算法")

# 智能模式开关
SMART_MODE = API_TYPE != "none"

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


# ============== 基础模式：启发式评分算法 ==============
def calculate_heuristic_score(repo: dict) -> float:
    """
    基础模式核心评分算法

    公式：
    - Base Score = log(stars + 1) * 0.7 + log(forks + 1) * 0.3
    - Time Factor = 1 / (1 + days_since_last_commit * 0.002)
    - Final Score = Base Score * Time Factor (归一化为 0-100)

    Args:
        repo: 仓库信息字典

    Returns:
        评分 (0-100)
    """
    stars = repo.get("stargazers_count", 0)
    forks = repo.get("forks_count", 0)

    # Base Score: 使用 log 避免极端值影响
    import math
    base_score = math.log(stars + 1) * 0.7 + math.log(forks + 1) * 0.3

    # Time Factor: 新近度衰减
    updated_at = repo.get("updated_at", "")
    if updated_at:
        try:
            updated_date = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            now = datetime.now(updated_date.tzinfo)
            days_since_update = (now - updated_date).days
        except (ValueError, TypeError):
            days_since_update = 365  # 默认一年
    else:
        days_since_update = 365

    time_factor = 1 / (1 + days_since_update * 0.002)

    # Final Score (归一化到 0-100)
    final_score = base_score * time_factor * 10  # 乘以系数使分数更直观

    return round(min(100, final_score), 2)


# ============== 智能模式：LLM 调用 ==============
async def call_llm(prompt: str, system_prompt: str = None) -> str:
    """
    调用 LLM（支持 OpenAI、DeepSeek、MiniMax、Claude 等）

    Args:
        prompt: 用户提示词
        system_prompt: 系统提示词

    Returns:
        LLM 响应文本
    """
    # 懒加载 openai 库
    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai 库未安装，无法使用智能模式")
        return ""

    # MiniMax Anthropic 兼容格式
    extra_headers = {}
    if API_TYPE == "minimax":
        extra_headers["x-minimax-api-type"] = "anthropic"

    # 创建客户端
    client = OpenAI(
        api_key=OPENAI_API_KEY,
        base_url=API_BASE_URL,
        default_headers=extra_headers if extra_headers else None,
    )

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        response = client.chat.completions.create(
            model=API_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=500,
        )

        # 解析响应
        if hasattr(response.choices[0].message, 'content'):
            return response.choices[0].message.content.strip()
        elif hasattr(response.choices[0].message, 'text'):
            return response.choices[0].message.text.strip()

    except Exception as e:
        logger.error(f"LLM ({API_TYPE}) 调用失败: {e}")
        return ""


async def generate_keywords_smart(topic: str) -> list[str]:
    """
    生成搜索关键词

    - Smart Mode: 调用 LLM 生成多个相关英文搜索词
    - Basic Mode: 返回 [topic]

    Args:
        topic: 用户输入的主题

    Returns:
        关键词列表
    """
    if SMART_MODE:
        logger.info(f"智能模式：生成关键词 for '{topic}'")

        system_prompt = """你是一个 GitHub 搜索专家。
用户会给你一个研究主题，你需要生成多个相关的英文搜索关键词。
这些关键词应该能帮助找到该领域的优秀开源项目。

要求：
1. 生成 8-12 个关键词
2. 返回纯 JSON 数组格式，例如：["keyword1", "keyword2"]
3. 不要包含任何解释或 markdown 格式
4. 关键词应该涵盖不同角度（技术名、应用场景、相关术语、具体项目名）
5. 可以包含具体知名项目名（如 whisper, bark, TTS 等）
6. 关键词应该足够具体，能搜到高质量项目"""

        user_prompt = f"研究主题: {topic}\n\n请生成 10 个搜索关键词："

        result = await call_llm(user_prompt, system_prompt)

        # 解析 JSON
        import json
        try:
            # 清理可能的 markdown 格式
            result = result.strip()
            if result.startswith("```"):
                # 提取代码块内容
                lines = result.split("\n")
                result = "\n".join(line for line in lines if not line.startswith("```"))
            keywords = json.loads(result)
            if isinstance(keywords, list):
                return keywords[:12]  # 返回最多12个关键词
        except json.JSONDecodeError as e:
            logger.warning(f"解析关键词失败: {e}, 使用基础关键词")

        return [topic.lower()]
    else:
        # 基础模式：直接使用输入的主题
        logger.info(f"基础模式：使用主题 '{topic}' 作为唯一关键词")
        return [topic.lower()]


async def fetch_readme(owner: str, repo: str) -> str:
    """
    获取仓库 README 内容（前 2000 字符）

    Args:
        owner: 仓库所有者
        repo: 仓库名

    Returns:
        README 文本（截断）
    """
    try:
        readme = await fetch_github(f"repos/{owner}/{repo}/readme")
        import base64
        content = base64.b64decode(readme.get("content", "")).decode("utf-8", errors="ignore")
        return content[:2000]  # 截断避免 Token 溢出
    except Exception as e:
        logger.warning(f"获取 README 失败: {owner}/{repo}")
        return ""


async def analyze_repo_quality(repo: dict, readme_content: str = "") -> dict:
    """
    分析仓库质量

    - Smart Mode: 调用 LLM 阅读 README，判断是否符合 Agent 定义并打分
    - Basic Mode: 使用启发式评分算法

    Args:
        repo: 仓库信息
        readme_content: README 内容（可选）

    Returns:
        {"score": float, "summary": str, "is_agent": bool}
    """
    owner = repo.get("owner", {}).get("login", "")
    repo_name = repo.get("name", "")
    description = repo.get("description", "") or ""

    if SMART_MODE and readme_content:
        logger.info(f"智能模式：分析仓库 {owner}/{repo_name}")

        system_prompt = """你是一个技术评估专家。
请评估以下 GitHub 项目是否属于"Agent/AI 智能体"类别，并打分 0-100。

Agent/AI 智能体的特征：
- 能够自主决策或执行任务
- 包含 AI/ML 模型或算法
- 支持与外部系统交互
- 具有对话/推理/规划能力

输出格式（JSON）：
{"score": 85, "summary": "一句话概括核心功能", "is_agent": true}

要求：
- score: 0-100 的数字
- summary: 一句话概括（中文）
- is_agent: true/false"""

        user_prompt = f"""
项目名称: {owner}/{repo_name}
描述: {description}
README 摘要: {readme_content[:1500]}

请评估：
"""

        result = await call_llm(user_prompt, system_prompt)

        # 解析 JSON
        import json
        try:
            result = result.strip()
            if result.startswith("```"):
                lines = result.split("\n")
                result = "\n".join(line for line in lines if not line.startswith("```"))
            analysis = json.loads(result)
            return {
                "score": float(analysis.get("score", 50)),
                "summary": analysis.get("summary", description[:50]),
                "is_agent": analysis.get("is_agent", False),
            }
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"解析 LLM 结果失败: {e}")
            # 回退到基础模式
    else:
        logger.info(f"基础模式：启发式评分 {owner}/{repo_name}")

    # 基础模式：使用启发式算法
    score = calculate_heuristic_score(repo)
    return {
        "score": score,
        "summary": "基于使用统计（Stars、Forks、活跃度）",
        "is_agent": True,  # 基础模式假设相关
    }


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
        language: 编程语言筛选 (使用 "any" 表示不限语言)
        sort: 排序方式 (stars, updated, forks)
        per_page: 返回结果数量

    Returns:
        仓库信息列表，包含潜力评分

    Raises:
        ValueError: 422 查询语法错误
    """
    logger.info(f"搜索 GitHub 仓库: query={query}, language={language}, sort={sort}")

    # 构建查询参数
    if language and language.lower() != "any":
        search_query = f"{query}+language:{language}"
    else:
        search_query = query  # 不加 language 限制

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


# ============== 自主发现核心函数 ==============
async def discover_and_evaluate(topic: str, max_repos: int = 15) -> list[dict]:
    """
    自主发现并评估特定领域的 Agent 项目

    工作流程：
    1. 调用 DeepSeek 生成多个搜索关键词
    2. 同时搜索 topic 本身（更宽泛）
    3. 添加热门项目名作为补充关键词
    4. 去重、数据丰富化、按评分排序

    Args:
        topic: 研究主题（如：音频 Agent、数字人）
        max_repos: 最大返回数量

    Returns:
        排序后的仓库列表（包含评分和摘要）
    """
    logger.info(f"开始自主发现: topic='{topic}', max_repos={max_repos}")

    # Step 1: 调用 DeepSeek 生成关键词
    keywords = await generate_keywords_smart(topic)
    logger.info(f"生成关键词: {keywords}")

    # Step 1b: 同时搜索 topic 本身（更宽泛，不加过滤词）
    topic_keywords = topic.split()
    logger.info(f"使用 topic 本身作为补充搜索词: {topic_keywords}")

    # Step 1c: 音频领域热门项目名（确保包含顶级项目）
    audio_hot_projects = ["whisper", "TTS", "audiocraft", "Coqui TTS", "bark",
                          "LocalAI", "funNLP", "NeMo", "Vosk", "DeepSpeech",
                          "GPT-SoVITS", "ChatTTS", "so-vits-svc", "OpenVoice",
                          "MusicGen", "CosyVoice"]

    # 合并所有关键词
    all_keywords = list(set(keywords + topic_keywords + audio_hot_projects))
    logger.info(f"合并后总计 {len(all_keywords)} 个搜索词")

    # Step 2: 并行搜索 GitHub
    all_repos = []
    seen_urls = set()

    for keyword in all_keywords:
        try:
            # 搜索时不限制语言，获取更多结果
            repos = await search_github_repos(keyword, language="any", sort="stars", per_page=10)

            for repo in repos:
                url = repo.get("html_url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_repos.append(repo)

            logger.info(f"关键词 '{keyword}': 找到 {len(repos)} 个")
        except Exception as e:
            logger.warning(f"搜索 '{keyword}' 失败: {e}")

    logger.info(f"去重后总计: {len(all_repos)} 个仓库")

    # 如果搜索结果太少，尝试搜索关键词本身（不作为过滤条件）
    if len(all_repos) < 5:
        logger.info("搜索结果较少，尝试备用搜索...")
        basic_keywords = topic.split()
        for kw in basic_keywords[:5]:
            if kw.lower() not in [k.lower() for k in keywords]:
                try:
                    repos = await search_github_repos(kw, language="any", sort="stars", per_page=10)
                    for repo in repos:
                        url = repo.get("html_url", "")
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            all_repos.append(repo)
                    logger.info(f"备用关键词 '{kw}': 找到 {len(repos)} 个")
                except:
                    pass

    # Step 3 & 4: 数据丰富化（并行）
    semaphore = asyncio.Semaphore(3)  # 限制并发

    async def enrich_repo(repo: dict) -> dict:
        async with semaphore:
            owner = repo.get("owner", {}).get("login", "")
            name = repo.get("name", "")

            # 获取 README（仅智能模式需要）
            readme_content = ""
            if SMART_MODE:
                readme_content = await fetch_readme(owner, name)

            # 质量分析
            analysis = await analyze_repo_quality(repo, readme_content)

            return {
                **repo,
                "analysis_score": analysis["score"],
                "analysis_summary": analysis["summary"],
                "is_agent": analysis["is_agent"],
                "search_keywords": keywords,
            }

    # 并行处理所有仓库
    enriched_tasks = [enrich_repo(repo) for repo in all_repos]
    enriched_repos = await asyncio.gather(*enriched_tasks, return_exceptions=True)

    # 过滤异常结果
    valid_repos = [
        r for r in enriched_repos
        if isinstance(r, dict) and r.get("analysis_score", 0) > 0
    ]

    # Step 5: 按评分排序
    valid_repos.sort(key=lambda x: x.get("analysis_score", 0), reverse=True)

    logger.info(f"完成分析，返回前 {min(len(valid_repos), max_repos)} 个")
    return valid_repos[:max_repos]
