#!/usr/bin/env python3
"""企业RAG知识库系统 - CLI入口"""
import os
import sys
import click
import time
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 最先加载环境变量，override=True 确保 .env 文件覆盖系统环境变量
from dotenv import load_dotenv
load_dotenv(override=True)

from config import PRESETS, get_preset, list_presets
from config.settings import ConfigBundle
from config.retrieval_config import RetrievalConfig
from config.answer_config import AnswerConfig
from config.pdf_config import PDFConfig
from config.embedding_config import EmbeddingConfig
from config.eval_config import EvalConfig
from config.indexer_config import IndexerConfig
from config.retrieval_config import RetrievalConfig
from config.embedding_config import EmbeddingConfig
from config.logging_config import LogConfig
from src.logging_setup import init_logging


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """企业RAG知识库系统 CLI"""
    init_logging(LogConfig())


@cli.command()
def init():
    """初始化项目结构"""
    click.echo("初始化项目结构...")

    dirs = [
        "data/pdf_reports",
        "data/parsed",
        "data/chunked",
        "data/vector_db",
        "data/bm25",
        "data/eval_results",
        "data/feedback",
        "data/logs",
        "config",
        "src",
        "ui",
        "tests",
    ]

    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)
        click.echo(f"  创建目录: {d}")

    # 创建.env文件
    env_file = Path(".env")
    if not env_file.exists():
        env_content = """# 阿里云DashScope（推荐，使用qwen-turbo模型）
DASHSCOPE_API_KEY=your_dashscope_api_key_here

# OpenAI（如使用openai相关配置）
OPENAI_API_KEY=your_openai_api_key_here

# Google Gemini（如使用gemini相关配置）
GEMINI_API_KEY=your_gemini_api_key_here
"""
        env_file.write_text(env_content)
        click.echo("  创建文件: .env")

    click.echo("\n初始化完成！请编辑 .env 文件填入API密钥。")


@cli.command()
def list_configs():
    """列出所有可用配置"""
    presets = list_presets()
    click.echo("可用配置:")
    for name in presets:
        preset = get_preset(name)
        click.echo(f"\n  [{name}]")
        if preset.retrieval:
            r = preset.retrieval
            click.echo(f"    - chunk_size: {r.chunk_size}")
            click.echo(f"    - top_k_retrieval: {r.top_k_retrieval}")
            click.echo(f"    - enable_rerank: {r.enable_rerank}")
            click.echo(f"    - enable_multiquery: {r.enable_multiquery}")
            click.echo(f"    - enable_history: {r.enable_history}")


@cli.command()
@click.option("--name", "-n", default="full", help="配置名称")
def use_config(name):
    """查看指定配置详情"""
    try:
        preset = get_preset(name)
        click.echo(f"\n配置: {name}")
        click.echo("=" * 50)

        if preset.retrieval:
            click.echo("\n[检索配置]")
            for k, v in preset.retrieval.to_dict().items():
                click.echo(f"  {k}: {v}")

        if preset.answer:
            click.echo("\n[答案配置]")
            for k, v in preset.answer.to_dict().items():
                click.echo(f"  {k}: {v}")

        if preset.pdf:
            click.echo("\n[PDF配置]")
            for k, v in preset.pdf.to_dict().items():
                click.echo(f"  {k}: {v}")

        if preset.embedding:
            click.echo("\n[Embedding配置]")
            for k, v in preset.embedding.to_dict().items():
                click.echo(f"  {k}: {v}")

    except ValueError as e:
        click.echo(f"错误: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("question")
@click.option("--config", "-c", default="base", help="配置名称")
@click.option("--details", is_flag=True, default=False, help="显示检索详情")
def query(question, config, details):
    """单次问答"""
    from src.pipeline import RAGPipeline
    from config.embedding_config import EmbeddingConfig

    try:
        preset = get_preset(config)
    except ValueError:
        click.echo(f"配置 '{config}' 不存在，使用 base", err=True)
        preset = get_preset("base")

    config_bundle = ConfigBundle(
        retrieval=preset.retrieval or RetrievalConfig(),
        answer=preset.answer or AnswerConfig(),
        pdf=preset.pdf,
        embedding=preset.embedding or EmbeddingConfig()
    )

    click.echo(f"使用配置 [{config}]，加载 Pipeline...")
    pipeline = RAGPipeline(config_bundle)

    click.echo(f"\n问题: {question}\n")
    result = pipeline.answer_single_question(question, return_retrieval_details=details)

    click.echo("=" * 60)
    click.echo(f"答案: {result['final_answer']}")

    if result.get("step_by_step_analysis"):
        click.echo(f"\n推理过程:\n{result['step_by_step_analysis'][:300]}...")

    if result.get("relevant_pages"):
        click.echo(f"\n引用页码: {result['relevant_pages']}")

    if details and result.get("retrieval_details"):
        rd = result["retrieval_details"]
        click.echo(f"\n改写查询: {rd.get('rewritten_query', '')}")
        click.echo(f"查询变体: {rd.get('query_variants', [])}")
        click.echo(f"检索结果数: {len(rd.get('retrieval_results', []))}")
    click.echo("=" * 60)


@cli.command()
@click.option("--config", "-c", default="base", help="配置名称")
@click.option("--pdf-dir", "-d", default="data/pdf_reports", help="PDF目录")
@click.option("--output-dir", "-o", default="data/parsed", help="输出目录")
def parse_pdfs(config, pdf_dir, output_dir):
    """解析PDF文件（使用MinerU在线API）"""
    try:
        preset = get_preset(config)
    except ValueError:
        click.echo(f"配置 '{config}' 不存在，使用 base 配置", err=True)
        preset = get_preset("base")

    pdf_config = preset.pdf if preset.pdf else PDFConfig()

    click.echo(f"使用配置 [{config}] 解析PDF...")
    click.echo(f"PDF目录: {pdf_dir}")
    click.echo(f"输出目录: {output_dir}")

    from src.pdf_mineru import PDFParser

    parser = PDFParser(config=pdf_config)
    results = parser.parse_directory(pdf_dir, output_dir)
    click.echo(f"\n解析完成: {len(results)} 个文件")


@cli.command()
@click.option("--config", "-c", default="base", help="配置名称")
@click.option("--input-dir", "-i", default="data/parsed", help="解析结果目录")
@click.option("--output-dir", "-o", default="data/parsed", help="输出目录")
@click.option("--max-workers", "-w", default=3, help="并行工作数")
def serialize_tables(config, input_dir, output_dir, max_workers):
    """序列化表格（将HTML表格转换为文本）"""
    try:
        preset = get_preset(config)
    except ValueError:
        click.echo(f"配置 '{config}' 不存在，使用 base 配置", err=True)
        preset = get_preset("base")

    pdf_config = preset.pdf if preset.pdf else PDFConfig()
    pdf_config.max_workers = max_workers

    click.echo(f"使用配置 [{config}] 序列化表格...")
    click.echo(f"输入目录: {input_dir}")
    click.echo(f"输出目录: {output_dir}")

    from src.table_serializer import TableSerializer, DASHSCOPE_AVAILABLE

    if not DASHSCOPE_AVAILABLE:
        click.echo("警告: dashscope 未安装，将使用简单HTML解析", err=True)

    serializer = TableSerializer(config=pdf_config)

    # 处理目录中所有JSON文件
    import glob
    json_files = glob.glob(f"{input_dir}/*.json")
    click.echo(f"找到 {len(json_files)} 个解析文件")

    for json_file in json_files:
        try:
            output_file = Path(output_dir) / Path(json_file).name
            serializer.process_parsed_report(json_file, str(output_file))
            click.echo(f"  处理: {Path(json_file).name}")
        except Exception as e:
            click.echo(f"  失败: {Path(json_file).name} - {e}", err=True)

    click.echo("\n表格序列化完成")


@cli.command()
@click.option("--config", "-c", default="base", help="配置名称")
@click.option("--input-dir", "-i", default="data/parsed", help="解析结果目录")
@click.option("--output-dir", "-o", default="data/chunked", help="输出目录")
def process_reports(config, input_dir, output_dir):
    """处理报告（分块+索引）"""
    try:
        preset = get_preset(config)
    except ValueError:
        click.echo(f"配置 '{config}' 不存在，使用 base 配置", err=True)
        preset = get_preset("base")

    retrieval_config = preset.retrieval if preset.retrieval else RetrievalConfig()
    embedding_config = preset.embedding if preset.embedding else EmbeddingConfig()

    click.echo(f"使用配置 [{config}] 处理报告...")
    click.echo(f"输入目录: {input_dir}")
    click.echo(f"输出目录: {output_dir}")

    import glob
    import json
    from src.text_splitter import TextSplitter
    from src.vector_store import VectorStore
    from src.bm25_index import BM25Index

    # 1. 分块
    click.echo("\n[1/3] 开始分块...")
    splitter = TextSplitter(config=retrieval_config)

    json_files = glob.glob(f"{input_dir}/*.json")
    # 只处理主体文件（不含 _part_ 的合并后文件）
    main_files = [f for f in json_files if "_part_" not in f]
    click.echo(f"找到 {len(main_files)} 个主体文件（过滤掉 {len(json_files) - len(main_files)} 个分片）")

    all_chunks = []
    all_parent_chunks = []

    for json_file in main_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                report = json.load(f)

            # 提取文本（优先使用 markdown，它包含清理后的表格）
            markdown = report.get("content", {}).get("markdown", "")

            # 使用 markdown 作为完整文本（已经过表格序列化处理）
            if markdown:
                doc = {
                    "text": markdown,
                    "doc_id": report.get("metainfo", {}).get("sha1_name", ""),
                    "metadata": {"page": 0}
                }
                result = splitter.split_documents([doc])
                all_chunks.extend(result["chunks"])
                all_parent_chunks.extend(result["parent_chunks"])

        except Exception as e:
            click.echo(f"  分块失败: {json_file} - {e}", err=True)

    click.echo(f"  分块完成: {len(all_chunks)} 个子Chunk, {len(all_parent_chunks)} 个父Chunk")

    # 2. 创建向量库
    click.echo("\n[2/3] 创建向量库...")
    try:
        vector_store = VectorStore(config=embedding_config)
        vector_store.create_index()

        texts = [c["text"] for c in all_chunks]
        chunk_ids = [c["chunk_id"] for c in all_chunks]
        metadata = [c.get("metadata", {}) for c in all_chunks]

        vector_store.add_texts(texts, chunk_ids, metadata)
        vector_store.save(output_dir + "/vector_db")
        click.echo(f"  向量库创建完成: {vector_store.get_stats()}")
    except ImportError as e:
        click.echo(f"  向量库创建跳过: {e}", err=True)

    # 3. 创建BM25索引
    click.echo("\n[3/3] 创建BM25索引...")
    try:
        bm25_index = BM25Index()
        texts = [c["text"] for c in all_chunks]
        chunk_ids = [c["chunk_id"] for c in all_chunks]
        metadata = [c.get("metadata", {}) for c in all_chunks]

        bm25_index.index(texts, chunk_ids, metadata)
        bm25_index.save(output_dir + "/bm25")
        click.echo(f"  BM25索引创建完成: {bm25_index.get_stats()}")
    except ImportError as e:
        click.echo(f"  BM25索引创建跳过: {e}", err=True)

    # 保存分块结果
    chunked_data = {
        "chunks": all_chunks,
        "parent_chunks": all_parent_chunks
    }
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    with open(output_dir + "/chunks.json", 'w', encoding='utf-8') as f:
        json.dump(chunked_data, f, ensure_ascii=False, indent=2)

    click.echo("\n报告处理完成！")
    click.echo(f"输出目录: {output_dir}")


@cli.command()
@click.option("--config", "-c", default="base", help="配置名称")
@click.option("--input", "-i", "input_file", default="data/eval_questions.json", help="问题文件路径（JSON）")
@click.option("--output", "-o", default="data/eval_results/answers.json", help="答案输出路径")
def process_questions(config, input_file, output):
    """批量处理问题，输出答案文件"""
    import json as _json
    from src.pipeline import RAGPipeline
    from config.embedding_config import EmbeddingConfig
    from datetime import datetime

    try:
        preset = get_preset(config)
    except ValueError:
        click.echo(f"配置 '{config}' 不存在，使用 base", err=True)
        preset = get_preset("base")

    questions_path = Path(input_file)
    if not questions_path.exists():
        click.echo(f"问题文件不存在: {input_file}", err=True)
        sys.exit(1)

    with open(questions_path, "r", encoding="utf-8") as f:
        data = _json.load(f)

    questions = data.get("questions", [])
    if not questions:
        click.echo("问题列表为空", err=True)
        sys.exit(1)

    click.echo(f"使用配置 [{config}]，共 {len(questions)} 个问题")

    config_bundle = ConfigBundle(
        retrieval=preset.retrieval or RetrievalConfig(),
        answer=preset.answer or AnswerConfig(),
        pdf=preset.pdf,
        embedding=preset.embedding or EmbeddingConfig()
    )
    pipeline = RAGPipeline(config_bundle)

    answers = {}
    with click.progressbar(questions, label="处理问题") as bar:
        for q in bar:
            result = pipeline.answer_single_question(q)
            answers[q] = result["final_answer"]

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_data = {
        "config": config,
        "timestamp": datetime.now().isoformat(),
        "question_count": len(questions),
        "answers": answers
    }
    with open(output_path, "w", encoding="utf-8") as f:
        _json.dump(output_data, f, ensure_ascii=False, indent=2)

    click.echo(f"\n完成！答案已保存至: {output}")


@cli.command()
def ui():
    """启动Web UI"""
    click.echo("启动Streamlit UI...")
    import subprocess
    import os
    venv_python = os.path.join(os.path.dirname(__file__), ".venv", "bin", "python3")
    subprocess.run([venv_python, "-m", "streamlit", "run", "ui/app.py"])


@cli.command()
@click.option("--config", "-c", default="base", help="配置名称")
@click.option("--questions", "-q", default="data/eval_questions.json", help="问题文件路径")
def evaluate(config, questions):
    """运行评估 - 测试RAG系统效果"""
    import json
    from src.pipeline import RAGPipeline
    from src.evaluator import RetrievalEvaluator

    click.echo("=" * 60)
    click.echo("📊 企业RAG知识库 - 评估测试")
    click.echo("=" * 60)

    # 加载预设配置
    try:
        preset = get_preset(config)
    except ValueError:
        click.echo(f"配置 '{config}' 不存在，使用 base", err=True)
        preset = get_preset("base")

    click.echo(f"\n使用配置: {config}")
    click.echo("-" * 40)

    # 加载测试问题
    questions_path = Path(questions)
    if questions_path.exists():
        with open(questions_path, 'r', encoding='utf-8') as f:
            test_data = json.load(f)
        eval_questions = test_data.get("questions", [])
        ground_truth = test_data.get("ground_truth", {})
        click.echo(f"加载测试问题: {len(eval_questions)} 个")
    else:
        # 使用内置默认问题
        eval_questions = [
            "中芯国际2024年营收是多少？",
            "公司的研发投入是多少？",
            "公司有多少员工？",
        ]
        ground_truth = {}
        click.echo(f"使用默认测试问题: {len(eval_questions)} 个")

    if not eval_questions:
        click.echo("没有测试问题，请提供问题文件", err=True)
        return

    # 创建RAG管道
    from config.embedding_config import EmbeddingConfig
    config_bundle = ConfigBundle(
        retrieval=preset.retrieval or RetrievalConfig(),
        answer=preset.answer or AnswerConfig(),
        pdf=preset.pdf,
        embedding=preset.embedding or EmbeddingConfig()
    )
    pipeline = RAGPipeline(config_bundle)

    click.echo(f"\n开始评估...\n")

    # 创建检索评估器
    evaluator = RetrievalEvaluator(top_k=[1, 3, 5, 10])

    # 准备ground_truth（如果没有提供，用chunk_id匹配）
    if not ground_truth:
        # 简单方法：对于每个问题，执行检索并假设返回的chunk_id是正确的
        # 实际应该有人工标注的ground_truth
        click.echo("注意: 没有ground_truth标注，将使用检索结果作为参考")
        click.echo("请创建评估问题文件以获得准确指标\n")

    # 执行评估
    retrieval_func = lambda query: pipeline.retriever.search(query, top_k=20)

    # 收集结果
    query_results = []
    total_start = click.get_current_context().command.get_context(None).params

    for i, q in enumerate(eval_questions):
        click.echo(f"[{i+1}/{len(eval_questions)}] {q[:40]}...")

        # 执行检索
        start_time = time.time()
        results = retrieval_func(q)
        elapsed = time.time() - start_time

        # 提取检索到的chunk_ids
        retrieved_ids = [r.get("chunk_id", "") for r in results[:10]]

        # 计算延迟
        latency_ms = elapsed * 1000

        query_results.append({
            "query": q,
            "retrieved_ids": retrieved_ids,
            "latency_ms": latency_ms,
            "top1_relevant": retrieved_ids[0] if retrieved_ids else None
        })

    # 计算指标
    click.echo("\n" + "=" * 60)
    click.echo("📈 评估结果")
    click.echo("=" * 60)

    # 如果有ground_truth，计算完整指标
    if ground_truth:
        metrics = evaluator.evaluate(
            queries=eval_questions,
            relevant_chunks=ground_truth,
            retrieval_func=retrieval_func
        )
        click.echo(f"\nRecall@1:  {metrics.get('recall@1', 0):.4f}")
        click.echo(f"Recall@3:  {metrics.get('recall@3', 0):.4f}")
        click.echo(f"Recall@5:  {metrics.get('recall@5', 0):.4f}")
        click.echo(f"Recall@10: {metrics.get('recall@10', 0):.4f}")
        click.echo(f"MRR:       {metrics.get('mrr', 0):.4f}")
        click.echo(f"NDCG@5:    {metrics.get('ndcg@5', 0):.4f}")
    else:
        # 无ground_truth时只显示基本统计
        click.echo(f"\n检索延迟统计:")
        latencies = [r["latency_ms"] for r in query_results]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        click.echo(f"  平均延迟: {avg_latency:.1f}ms")
        click.echo(f"  最快: {min(latencies):.1f}ms")
        click.echo(f"  最慢: {max(latencies):.1f}ms")

        # 显示检索结果样例
        click.echo(f"\n检索结果样例 (前3条):")
        for i, r in enumerate(query_results[:3]):
            click.echo(f"  Q{i+1}: {r['query'][:30]}...")
            click.echo(f"      Top1: {r['retrieved_ids'][0] if r['retrieved_ids'] else 'N/A'}")

    click.echo("\n" + "=" * 60)

    # 保存结果
    output_dir = Path("data/eval_results")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"eval_{config}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    eval_report = {
        "config": config,
        "timestamp": datetime.now().isoformat(),
        "questions_count": len(eval_questions),
        "results": query_results,
        "metrics": metrics if ground_truth else {}
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(eval_report, f, ensure_ascii=False, indent=2)

    click.echo(f"评估报告已保存: {output_file}")


@cli.command()
@click.option("--config", "-c", default="base", help="配置名称")
def incremental_index(config):
    """增量索引（监控模式）"""
    click.echo(f"使用配置 [{config}] 启动增量索引监控...")
    click.echo("(增量索引功能待实现)")


if __name__ == "__main__":
    cli()
