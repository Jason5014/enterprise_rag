# 企业RAG知识库系统

基于 RAG Challenge 获奖方案设计理念的企业级知识库问答系统。

## 特性

- **PDF解析** - 使用 MinerU 进行 PDF 解析
- **父子Chunk检索** - Parent Document Retrieval 改善检索效果
- **LLM重排** - 使用 LLM 对检索结果重排
- **Chain-of-Thought** - 结构化推理输出
- **MultiQuery** - 查询扩展改善召回
- **多配置对比** - 支持多种配置组合对比实验

## 快速开始

### 1. 安装依赖

```bash
cd enterprise_rag
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

### 2. 配置API密钥

```bash
cp env .env
# 编辑 .env 填入你的API密钥
```

### 3. 初始化项目

```bash
python main.py init
```

### 4. 使用CLI

```bash
# 列出可用配置
python main.py list-configs

# 查看配置详情
python main.py use-config --name full

# 启动UI
python main.py ui
```

## 项目结构

```
enterprise_rag/
├── config/              # 配置目录
│   ├── settings.py     # 配置基类
│   ├── retrieval_config.py
│   ├── answer_config.py
│   ├── pdf_config.py
│   ├── embedding_config.py
│   ├── eval_config.py
│   ├── indexer_config.py
│   └── presets.py       # 预设配置
├── src/                 # 源代码
│   └── pipeline.py      # 主流程管道
├── data/               # 数据目录
├── ui/                 # UI目录
├── tests/              # 测试目录
├── main.py             # CLI入口
└── requirements.txt    # 依赖
```

## 配置说明

| 配置 | 说明 |
|------|------|
| base | 基础配置 |
| fast | 快速配置 |
| precision | 精度配置 |
| full | 完整配置（所有功能） |

## License

MIT
