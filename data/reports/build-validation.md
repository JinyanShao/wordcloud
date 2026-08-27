# wordcloud 构建验证

> 28/28 项通过。验证对象为当前 SQLite、稳定坐标与浏览器导出物。

| 检查 | 结果 | 证据 |
|---|---|---|
| 来源登记、许可与哈希 | 通过 | 7 个来源均完整 |
| 词汇单位唯一 | 通过 | 14,251 rows / 14,251 unique lemma+POS |
| 500 条分层人工抽检 | 通过 | sample=500, unique=500, reviewed=500 |
| 自动 eligible 规则 | 通过 | 结构违规=0, 无释义低频违规=0; 人工覆盖例外另有记录 |
| 基础核心词词性、释义、义项与渲染回归 | 通过 | 24 entries verified |
| 审校词源、搭配与义项例句 | 通过 | learning entries=14, collocations=28, sourced sense examples=37,697 |
| 基础核心词教学例句 | 通过 | 6 个基础词、12 条短例句已导出 |
| A1/A2 实词可检索但不强行入图 | 通过 | search-only=1,612, appartenir/VER=present, overlap=0 |
| 运行时学习词范围、内容状态与词形搜索回归 | 通过 | learning=9,017, statuses=9,017, aliases=61,176 |
| 图端点与方向约束 | 通过 | foreign-key errors=0, invalid order=0 |
| 官方边来源完整 | 通过 | 4583/4583 条有来源 |
| 核心词审校关系 | 通过 | 103/103 条具完整审校、来源与例句 |
| 稳定坐标与全图连通 | 通过 | nodes=7,405, components=1, isolated=0 |
| 七类制图信号 | 通过 | derivation=1,708, editorial_seed=195, morphology=3,840, phonetic=6,033, semantic=2,770, skeleton=322, spelling=6,889 |
| Lexique MorphoBase 不冒充派生关系 | 通过 | promoted=0, division↔voir morphology=1, derivation=0 |
| Démonette 直接派生通过质量门 | 通过 | gate=True, candidates=1,708, sourced_official=1,708, same_pos=197, invalid_same_pos=0 |
| 核心词族回归 | 通过 | affirmer↔affirmation=1, voir↔vision=1, poli↔impoli=1 |
| DBnary 义项与语义关系通过质量门 | 通过 | gate=True, entries=9,881, definitions=43,299, sense_lexemes=8,748, semantic=2,770/2,770/2,770, contradictions=0 |
| 中文释义相似只保留为候选 | 通过 | CFDICT candidates=3,487; visible semantic layout=2,770 (DBnary only) |
| 语义样例与多义词回归 | 通过 | poli↔respectueux synonym=1 (expected 1), poli↔impoli antonym=1 (expected 1), seau↔nager synonym=0 (expected 0), poli entries/senses=2/4 |
| 主词与支撑词分账 | 通过 | eligible=7,338, support=67, rendered=7,405 |
| 静态运行时已导出 | 通过 | graph-data.js=17,654,384 bytes |
| 前端不再依赖 CLUSTERS | 通过 | canvas 读取 graph-data.js 固定坐标 |
| 学习表层已导出 | 通过 | 词源、搭配、DBnary 义项例句与可检索学习词进入静态运行时 |
| 运行时图数据缓存按内容版本化 | 通过 | index.html 与 Service Worker 均引用当前 graph-data.js SHA-256 版本 |
| DBnary 同快照审校队列可复现且禁止误导入 | 通过 | items/csv=203/203, aligned_sha256=aeb243f402c0acedade522842736e5885b025b5eb77894c45817b8f1bd12062f, production_sha256=aeb243f402c0acedade522842736e5885b025b5eb77894c45817b8f1bd12062f |
| Wiktextract P0 候选完整且人工批准门关闭 | 通过 | items/csv=59/59, pending=0 |
| Wiktextract P0 批准内容具名且仅含已选义项 | 通过 | entries=58, senses=128, reviewers=['Jinyan Shao'] |

## 边界

这份验证证明构建一致性、许可登记完整性和制图连通性，不证明自动候选等同于可靠语言学关系。只有 `official_edges` 才是产品可陈述关系；其余边继续保留候选或布局身份。
