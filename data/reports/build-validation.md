# maillage 构建验证

> 11/11 项通过。验证对象为当前 SQLite、稳定坐标与浏览器导出物。

| 检查 | 结果 | 证据 |
|---|---|---|
| 来源登记、许可与哈希 | 通过 | 4 个来源均完整 |
| 词汇单位唯一 | 通过 | 14,251 rows / 14,251 unique lemma+POS |
| 500 条分层人工抽检 | 通过 | sample=500, unique=500, reviewed=500 |
| 自动 eligible 规则 | 通过 | 结构违规=0, 无释义低频违规=0; 人工覆盖例外另有记录 |
| 图端点与方向约束 | 通过 | foreign-key errors=0, invalid order=0 |
| 官方边来源完整 | 通过 | 98/98 条有来源 |
| 稳定坐标与全图连通 | 通过 | nodes=7,371, components=1, isolated=0 |
| 六类制图信号 | 通过 | derivation=3,769, editorial_seed=98, phonetic=5,998, semantic=10,071, skeleton=107, spelling=6,861 |
| 主词与支撑词分账 | 通过 | eligible=7,314, support=57, rendered=7,371 |
| 静态运行时已导出 | 通过 | graph-data.js=1,129,919 bytes |
| 前端不再依赖 CLUSTERS | 通过 | canvas 读取 graph-data.js 固定坐标 |

## 边界

这份验证证明构建一致性、许可登记完整性和制图连通性，不证明自动候选等同于可靠语言学关系。只有 `official_edges` 才是产品可陈述关系；其余边继续保留候选或布局身份。
