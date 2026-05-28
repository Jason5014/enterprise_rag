# RAG系统优化指南

## 优化流程总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        优化闭环                                  │
│                                                                 │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐ │
│   │ 1.评估   │───→│ 2.分析   │───→│ 3.诊断   │───→│ 4.调优   │ │
│   └──────────┘    └──────────┘    └──────────┘    └──────────┘ │
│        ↑                                              │        │
│        └──────────────────────────────────────────────┘        │
│                         5.验证                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 第一步：评估 - 收集数据

### 1.1 运行评估
```bash
python main.py evaluate --config full
```

### 1.2 收集的指标

| 指标 | 含义 | 计算方式 |
|------|------|----------|
| **Recall@K** | 前K个结果中包含相关文档的比例 | 命中数 / 总相关数 |
| **MRR** | 第一个相关结果的排名倒数 | 1/排名 |
| **NDCG@5** | 前5个结果的排序质量 | DCG/IDCG |
| **延迟** | 各阶段耗时 | 毫秒 |

### 1.3 评估结果示例
```json
{
  "metrics": {
    "recall@1": 0.45,
    "recall@3": 0.62,
    "recall@5": 0.71,
    "recall@10": 0.85,
    "mrr": 0.52,
    "ndcg@5": 0.58
  },
  "results": [
    {
      "query": "中芯国际2024年营收是多少？",
      "latency_ms": 1250,
      "retrieved_ids": ["chunk_001", "chunk_002", ...]
    }
  ]
}
```

---

## 第二步：分析 - 理解指标

### 2.1 指标健康度判断

```
┌─────────────────────────────────────────────────────────────┐
│                    指标健康度参考                             │
├─────────────┬───────────────┬───────────────┬───────────────┤
│ 指标        │ 差            │ 一般          │ 好            │
├─────────────┼───────────────┼───────────────┼───────────────┤
│ Recall@1    │ < 0.4         │ 0.4 - 0.6     │ > 0.6         │
│ Recall@5    │ < 0.6         │ 0.6 - 0.8     │ > 0.8         │
│ Recall@10   │ < 0.7         │ 0.7 - 0.9     │ > 0.9         │
│ MRR         │ < 0.4         │ 0.4 - 0.6     │ > 0.6         │
│ NDCG@5      │ < 0.5         │ 0.5 - 0.7     │ > 0.7         │
│ 延迟        │ > 3000ms      │ 1000-3000ms   │ < 1000ms      │
└─────────────┴───────────────┴───────────────┴───────────────┘
```

### 2.2 指标组合分析

**组合1：Recall@1 低，Recall@10 高**
```
含义：相关文档存在，但排名靠后
原因：向量相似度不够精确，或缺少重排
```

**组合2：Recall@1 高，Recall@5 低**
```
含义：第一个结果好，但多样性不足
原因：检索结果过于集中，缺少多角度召回
```

**组合3：所有 Recall 都低**
```
含义：相关文档根本没被检索到
原因：分块问题、Embedding问题、或查询理解问题
```

**组合4：MRR 低，Recall@5 高**
```
含义：能找到相关文档，但排序不准
原因：需要加强重排
```

---

## 第三步：诊断 - 定位问题

### 3.1 问题诊断决策树

```
                         ┌─────────────────┐
                         │ Recall@5 < 0.7? │
                         └────────┬────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    ↓                           ↓
                   是                          否
                    │                           │
        ┌───────────┴───────────┐    ┌─────────┴─────────┐
        │ Recall@10 > 0.7?      │    │ MRR < 0.5?        │
        └───────────┬───────────┘    └─────────┬─────────┘
                    │                          │
          ┌─────────┴─────────┐      ┌────────┴────────┐
          ↓                   ↓      ↓                 ↓
         是                  否     是                否
          │                   │      │                 │
    ┌─────┴─────┐      ┌─────┴─────┐ │          ┌─────┴─────┐
    │ 排序问题   │      │ 召回问题   │ │          │ 系统健康   │
    │ 需要重排   │      │ 需要扩召回 │ │          │ 继续监控   │
    └───────────┘      └───────────┘ │          └───────────┘
                                     │
                              ┌──────┴──────┐
                              │ 排序不准     │
                              │ 调整重排权重 │
                              └─────────────┘
```

### 3.2 详细诊断表

| 症状 | 可能原因 | 验证方法 |
|------|----------|----------|
| Recall@5 低，Recall@10 高 | 相关文档排名靠后 | 查看检索日志，检查相关文档的排名 |
| Recall@10 也低 | 检索范围不足 | 增加 top_k 测试 |
| MRR 低 | 首个结果不相关 | 查看重排分数 |
| 延迟高 | 某阶段耗时过长 | 分析各阶段耗时 |
| Query Rewrite 无效果 | 改写质量差 | 对比改写前后的检索结果 |
| MultiQuery 无效果 | 变体质量差 | 查看生成的变体 |

### 3.3 检索日志分析

```bash
# 分析最近10条检索日志
python -c "
from src.optimizer import RAGOptimizer
optimizer = RAGOptimizer()
result = optimizer.analyze_retrieval_logs(last_n=10)
print(f'瓶颈阶段: {result[\"summary\"][\"bottleneck\"]}')
"
```

**日志关注点：**
- 各阶段耗时分布
- 错误和异常
- Query 改写是否生效
- MultiQuery 变体数量
- 重排前后排名变化

---

## 第四步：调优 - 配置优化

### 4.1 针对性调优策略

#### 策略1：提升召回率

**问题**：Recall@5 < 0.7，相关文档没被检索到

**方案A：增加检索范围**
```python
retrieval.top_k_retrieval = 30  # 从20增加到30
```

**方案B：启用MultiQuery**
```python
retrieval.enable_multiquery = True
retrieval.num_query_variants = 3  # 生成3个变体
```

**方案C：调整分块策略**
```python
retrieval.chunk_size = 500      # 更小的chunk，更多匹配机会
retrieval.chunk_overlap = 150   # 增加重叠，避免信息断裂
```

#### 策略2：提升排序质量

**问题**：MRR < 0.5，首个结果不相关

**方案A：启用或加强重排**
```python
retrieval.enable_rerank = True
retrieval.rerank_top_k = 10     # 重排前10个结果
retrieval.llm_weight = 0.8      # 增加LLM重排权重
```

**方案B：使用Jina Reranker**
```python
retrieval.use_jina_reranker = True
```

#### 策略3：提升查询理解

**问题**：口语化查询检索效果差

**方案A：启用Query改写**
```python
retrieval.enable_query_rewrite = True
```

**方案B：结合历史上下文**
```python
retrieval.enable_history = True
retrieval.max_history_turns = 5
```

#### 策略4：优化性能

**问题**：延迟 > 3000ms

**方案A：减少检索数量**
```python
retrieval.top_k_retrieval = 10  # 从30减少到10
```

**方案B：禁用耗时功能**
```python
retrieval.enable_multiquery = False
retrieval.enable_rerank = False
```

**方案C：使用更快的模型**
```python
answer.answer_model = "qwen-turbo"  # 使用轻量模型
```

### 4.2 配置预设对照

| 场景 | 推荐预设 | 特点 |
|------|----------|------|
| 测试调试 | `fast` | 禁用所有LLM功能，最快 |
| 日常使用 | `base` | 基础功能，平衡速度和质量 |
| 追求精度 | `precision` | 启用所有功能，最慢但最准 |
| 生产环境 | `full` | 完整功能，适合正式使用 |

### 4.3 配置修改示例

```python
from config.presets import get_preset
from config.retrieval_config import RetrievalConfig

# 获取基础配置
config = get_preset("base")

# 根据诊断结果修改
config.retrieval.top_k_retrieval = 25
config.retrieval.enable_multiquery = True
config.retrieval.num_query_variants = 3
config.retrieval.enable_rerank = True
config.retrieval.rerank_top_k = 10

# 重新评估验证
```

---

## 第五步：验证 - 确认效果

### 5.1 A/B 对比测试

```python
# 配置A：原始配置
config_a = get_preset("base")

# 配置B：优化后配置
config_b = get_preset("base")
config_b.retrieval.enable_rerank = True
config_b.retrieval.top_k_retrieval = 25

# 对比评估
metrics_a = evaluate(config_a)
metrics_b = evaluate(config_b)

print(f"Recall@5: {metrics_a['recall@5']:.3f} -> {metrics_b['recall@5']:.3f}")
print(f"MRR: {metrics_a['mrr']:.3f} -> {metrics_b['mrr']:.3f}")
```

### 5.2 验证检查清单

- [ ] Recall@5 是否提升？
- [ ] MRR 是否提升？
- [ ] 延迟是否可接受？
- [ ] 边界案例是否改善？
- [ ] 是否引入新问题？

### 5.3 迭代优化

```
第一次迭代：解决最明显的问题（通常是召回率）
第二次迭代：优化排序质量
第三次迭代：优化查询理解
第四次迭代：性能优化
```

---

## 快速参考卡

### 问题 → 解决方案速查

| 问题 | 快速解决方案 |
|------|--------------|
| Recall@5 低 | `top_k_retrieval=30, enable_multiquery=True` |
| MRR 低 | `enable_rerank=True, llm_weight=0.8` |
| 延迟高 | `top_k_retrieval=10, enable_multiquery=False` |
| 口语查询差 | `enable_query_rewrite=True` |
| 长文档检索差 | `chunk_size=500, enable_parent_retrieval=True` |

### 命令速查

```bash
# 运行评估
python main.py evaluate --config full

# 生成优化报告
python src/optimizer.py

# 查看检索日志
python -c "from src.optimizer import RAGOptimizer; RAGOptimizer().analyze_retrieval_logs()"

# 测试API连接
python test_dashscope.py
```
