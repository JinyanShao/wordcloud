# maillage 构建验证

> 17/17 项通过。验证对象为当前 SQLite、稳定坐标与浏览器导出物。

| 检查 | 结果 | 证据 |
|---|---|---|
| 来源登记、许可与哈希 | 通过 | 6 个来源均完整 |
| 词汇单位唯一 | 通过 | 14,251 rows / 14,251 unique lemma+POS |
| 500 条分层人工抽检 | 通过 | sample=500, unique=500, reviewed=500 |
| 自动 eligible 规则 | 通过 | 结构违规=0, 无释义低频违规=0; 人工覆盖例外另有记录 |
| 图端点与方向约束 | 通过 | foreign-key errors=0, invalid order=0 |
| 官方边来源完整 | 通过 | 6495/6495 条有来源 |
| 稳定坐标与全图连通 | 通过 | nodes=7,985, components=1, isolated=0 |
| 七类制图信号 | 通过 | derivation=1,675, editorial_seed=1,694, morphology=4,478, phonetic=6,747, semantic=2,720, skeleton=241, spelling=7,448 |
| Lexique MorphoBase 不冒充派生关系 | 通过 | promoted=0, division↔voir morphology=1, derivation=0 |
| Démonette 直接派生通过质量门 | 通过 | gate=True, candidates=1,675, sourced_official=1,675, same_pos=190, invalid_same_pos=0 |
| 核心词族回归 | 通过 | affirmer↔affirmation=1, voir↔vision=1, poli↔impoli=1 |
| DBnary 义项与语义关系通过质量门 | 通过 | gate=True, entries=7,979, definitions=31,328, sense_lexemes=7,129, semantic=2,720/2,720/2,720, contradictions=0 |
| 中文释义相似只保留为候选 | 通过 | CFDICT candidates=4,250; visible semantic layout=2,720 (DBnary only) |
| 语义样例与多义词回归 | 通过 | poli↔respectueux syn=1 (expected 1), poli↔impoli ant=1 (expected 1), seau↔nager syn=0 (expected 0), poli entries/senses=2/4 |
| 主词与支撑词分账 | 通过 | eligible=7,314, support=671, rendered=7,985 |
| 静态运行时已导出 | 通过 | graph-data.js=13,116,653 bytes |
| 前端不再依赖 CLUSTERS | 通过 | canvas 读取 graph-data.js 固定坐标 |

## 边界

这份验证证明构建一致性、许可登记完整性和制图连通性，不证明自动候选等同于可靠语言学关系。只有 `official_edges` 才是产品可陈述关系；其余边继续保留候选或布局身份。
