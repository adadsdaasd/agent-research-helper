# GitHub Scout MCP Server

帮助 LLM 快速调研和分析 GitHub 仓库结构与质量的 MCP Server。

## 功能概览

GitHub Scout 提供三个核心工具，让 AI 能够快速了解任意 GitHub 仓库的状态和结构：

| 工具 | 功能 | 返回值 |
|------|------|--------|
| `get_repo_health` | 评估项目活跃度，获取关键指标 | Stars、Forks、Issues、最后提交时间 |
| `analyze_repo_structure` | 获取项目目录树结构 | ASCII 树状图 |
| `fetch_critical_logic` | 读取指定文件的核心代码 | 原始代码内容（自动截断大文件） |

## 技术栈

- **Python**: 3.10+
- **MCP SDK**: `mcp` - 官方 MCP Python SDK
- **HTTP 客户端**: `httpx` - 异步 HTTP 请求
- **环境管理**: `python-dotenv`

## 项目结构

```
my-mini-agent/
├── server.py           # MCP Server 主入口，定义三个工具
├── utils.py            # GitHub API 辅助函数
├── requirements.txt    # Python 依赖列表
├── .env               # GitHub Token 配置（可选）
└── .gitignore         # Git 忽略规则
```

## 核心工具详解

### 1. get_repo_health

快速评估项目活跃度，决定是否值得深入调研。

**输入参数：**
- `repo_url`: GitHub 仓库 URL（支持多种格式）

**返回示例：**
```markdown
## 仓库健康报告: anthropics/claude-code

| 指标 | 数量 |
|------|------|
| Stars | 65,964 |
| Forks | 5,069 |
| Open Issues | 6,662 |
| License | N/A |

最后提交时间: 2026-02-10 23:10:48 UTC
默认分支: main
```

### 2. analyze_repo_structure

获取项目目录树结构，了解代码组织方式。

**输入参数：**
- `repo_url`: GitHub 仓库 URL
- `max_depth`: 最大递归深度（默认 2）

**返回示例：**
```markdown
## 仓库结构: anthropics/claude-code

📁 claude-code/
├── 📁 .claude
│   └── 📁 commands
│       ├── 📄 commit-push-pr.md
│       └── 📄 dedupe.md
├── 📁 plugins
│   ├── 📁 agent-sdk-dev
│   ├── 📁 code-review
│   └── 📄 README.md
├── 📄 README.md
└── 📄 LICENSE.md

（已自动过滤 .git, node_modules, __pycache__ 等）
```

**过滤规则：**
- 目录: `.git`, `node_modules`, `__pycache__`, `.idea`, `.vscode`, `venv`
- 文件扩展名: `.png`, `.jpg`, `.mp4`, `.pdf`, `.zip` 等

### 3. fetch_critical_logic

读取指定文件的核心代码，用于深入分析。

**输入参数：**
- `repo_url`: GitHub 仓库 URL
- `file_paths`: 文件路径列表（相对于仓库根目录）

**返回示例：**
```markdown
## 关键代码分析

### 📄 src/main.py
- **总行数**: 150
- **大小**: 5200 bytes
- **完整内容**:

```python
import os
def main():
    ...
```

### ❌ README.md
错误: 资源未找到
```

**Token 节省策略：**
- 文件 ≤ 500 行：返回完整内容
- 文件 > 500 行：返回前 200 行 + 后 50 行

## 安装与配置

### 1. 创建 Python 3.10+ 环境

```bash
# 使用 conda
conda create -n github-scout python=3.10 -y
conda activate github-scout

# 或使用 uv
uv venv --python 3.10
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置 GitHub Token（可选）

编辑 `.env` 文件：

```bash
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
```

**作用：**
- 匿名访问：60 次/小时
- 认证访问：5,000 次/小时

### 4. 运行 MCP Server

```bash
python server.py
```

## 在 Claude Code 中使用

编辑 `~/.claude/mcp.json`：

```json
{
  "mcpServers": {
    "github-scout": {
      "command": "python",
      "args": ["C:/Users/28252/Desktop/my-mini-agent/server.py"]
    }
  }
}
```

## 使用示例

```python
import asyncio
from server import get_repo_health, analyze_repo_structure, fetch_critical_logic

async def demo():
    repo = "https://github.com/anthropics/claude-code"
    
    # 1. 检查项目活跃度
    health = await get_repo_health(repo)
    print(health)
    
    # 2. 查看目录结构
    structure = await analyze_repo_structure(repo, max_depth=2)
    print(structure)
    
    # 3. 读取关键文件
    code = await fetch_critical_logic(repo, ["README.md", "package.json"])
    print(code)

asyncio.run(demo())
```

## 工作流程

```
用户请求
    │
    ▼
┌─────────────────────────────────────┐
│  1. 解析仓库 URL                     │
│     (支持多种格式自动识别)           │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  2. 调用 GitHub REST API            │
│     (并发请求优化性能)               │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  3. 数据处理与格式化                 │
│     - 过滤无关文件/目录              │
│     - 大文件智能截断                 │
│     - Markdown 表格输出              │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  4. 返回结果给 LLM                  │
└─────────────────────────────────────┘
```

## API 接口

GitHub Scout 内部调用的 API：

| 端点 | 用途 |
|------|------|
| `GET /repos/{owner}/{repo}` | 获取仓库元数据 |
| `GET /repos/{owner}/{repo}/commits` | 获取最近提交 |
| `GET /repos/{owner}/{repo}/contents/{path}` | 获取目录/文件列表 |
| `Raw URL` | 下载文件原始内容 |

## 错误处理

| 错误类型 | 处理方式 |
|----------|----------|
| 404 Not Found | 返回"资源未找到"提示 |
| 403 Rate Limit | 返回"API 速率限制"警告 |
| 401 Auth Failed | 返回"认证失败"提示 |
| 网络错误 | 返回"网络请求失败"提示 |

## 贡献

欢迎提交 Issue 和 PR！

## 许可证

MIT License
