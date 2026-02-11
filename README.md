# GitHub Scout MCP Server

一个智能 GitHub 仓库发现与评估工具，支持自主搜索和智能分析。

## 功能特性

### 核心功能

| 功能 | 说明 |
|------|------|
| 🔍 **自主搜索** | 无需手动维护列表，AI 自动生成搜索关键词发现相关项目 |
| 📊 **智能评估** | 基于 Stars、Forks、活跃度多维度评分 |
| 🌍 **跨语言** | 支持中英文搜索，不限编程语言 |
| ⚡ **双重模式** | 智能模式（LLM API）/ 基础模式（免费无需配置） |

### 支持的 LLM

- **DeepSeek** (推荐)
- **OpenAI**
- **MiniMax**
- **Claude**

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
# GitHub Token (用于搜索 API)
GITHUB_TOKEN=ghp_xxx

# DeepSeek API Key (用于智能关键词生成)
DEEPSEEK_API_KEY=sk-xxx
```

### 3. 运行 MCP Server

```bash
python server.py
```

## MCP 工具

### autonomous_discover

自主发现特定领域的 Agent 项目：

```python
# MCP 工具调用
autonomous_discover(topic="音频 Agent", max_repos=15)
```

**参数：**
- `topic`: 研究主题（如：音频、数字人、图像生成）
- `max_repos`: 最大返回数量（默认 15）

**返回：**
- Markdown 格式的智能评估报告
- 包含仓库排名、Stars、评分、活跃度

### search_github_repos

搜索 GitHub 仓库：

```python
search_github_repos(
    query="audio agent",
    language="any",  # 不限语言
    sort="stars",    # 按 Stars 排序
    per_page=10       # 每页数量
)
```

### batch_analyze_repos

批量分析多个仓库：

```python
batch_analyze_repos(
    repo_urls=[
        "https://github.com/openai/whisper",
        "https://github.com/coqui-ai/TTS"
    ]
)
```

## 项目结构

```
my-mini-agent/
├── server.py         # MCP Server 入口
├── utils.py          # GitHub API + LLM 调用
├── requirements.txt  # 依赖列表
├── .env.example      # 配置示例
├── .env              # 环境变量（不提交）
└── README.md        # 本文档
```

## 配置文件说明

### .env 配置项

| 变量 | 必需 | 说明 |
|------|------|------|
| `GITHUB_TOKEN` | 可选 | GitHub Personal Access Token，增加 API 速率限制 |
| `DEEPSEEK_API_KEY` | 可选 | DeepSeek API Key，启用智能搜索模式 |
| `OPENAI_API_KEY` | 可选 | OpenAI API Key |
| `ANTHROPIC_API_KEY` | 可选 | Claude API Key |

### GitHub Token 申请

1. 访问 https://github.com/settings/tokens
2. 点击 "Generate new token (classic)"
3. 设置名称，勾选 `repo` 权限
4. 生成 Token 并添加到 `.env`

## 评分算法

### 综合评分公式

```
综合评分 = Base Score × Time Factor × 10
```

- **Base Score**: `log(stars+1) × 0.7 + log(forks+1) × 0.3`
- **Time Factor**: `1 / (1 + days_since_update × 0.002)`
- **评分范围**: 0-100

### 潜力评分

```
潜力评分 = Stars / 创建天数
```

## 使用示例

### 搜索音频类项目

```python
# 搜索音频相关的 Agent 项目
await autonomous_discover("音频 Agent", max_repos=10)
```

### 搜索数字人类项目

```python
# 搜索数字人/虚拟人相关项目
await autonomous_discover("数字人", max_repos=15)
```

### 搜索图像生成类项目

```python
# 搜索图像生成相关项目
await autonomous_discover("图像生成", max_repos=10)
```

## 搜索结果示例

```
# GitHub Scout - 音频 Agent 精选报告

| 排名 | 仓库 | Stars | 综合评分 |
|------|------|-------|----------|
| 1 | openai/whisper | 94,460 | 100.0 |
| 2 | coqui-ai/TTS | 44,516 | 99.2 |
| 3 | suno-ai/bark | 38,971 | 95.0 |
| 4 | RVC-Boss/GPT-SoVITS | 54,916 | 98.0 |
| 5 | 2noise/ChatTTS | 38,696 | 94.0 |
```

## 技术栈

- **Python**: 3.10+
- **MCP SDK**: `mcp` - 官方 MCP Python SDK
- **HTTP 客户端**: `httpx` - 异步 HTTP 请求
- **环境管理**: `python-dotenv`

## 安装与配置

### 1. 创建 Python 环境

```bash
# 使用 conda
conda create -n github-scout python=3.10 -y
conda activate github-scout

# 或使用 venv
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，填入你的 API Keys
```

### 4. 运行

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

## API 接口

GitHub Scout 内部调用的 API：

| 端点 | 用途 |
|------|------|
| `GET /search/repositories` | 搜索仓库 |
| `GET /repos/{owner}/{repo}` | 获取仓库元数据 |
| `GET /repos/{owner}/{repo}/commits` | 获取最近提交 |
| `GET /repos/{owner}/{repo}/readme` | 获取 README |

## 常见问题

### Q: 没有 API Key 能用吗？

A: 可以！没有配置 LLM API Key 时，会使用基础模式，直接使用输入的关键词搜索。

### Q: GitHub Token 是必须的吗？

A: 不是必须，但不配置会有速率限制（10 次/分钟），配置后可提升到 60 次/分钟。

### Q: 搜索结果太少怎么办？

A: 检查 `.env` 中是否配置了 LLM API Key，智能模式会自动扩展搜索词。

### Q: DeepSeek API Key 从哪里获取？

A: 访问 https://platform.deepseek.com 注册并创建 API Key。

## 参考项目

- [openai/whisper](https://github.com/openai/whisper) - 语音识别
- [coqui-ai/TTS](https://github.com/coqui-ai/TTS) - 文本转语音
- [RVC-Boss/GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) - 语音合成
- [suno-ai/bark](https://github.com/suno-ai/bark) - 文本转语音模型

## 贡献

欢迎提交 Issue 和 PR！

## 许可证

MIT License
