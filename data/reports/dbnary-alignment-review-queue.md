# DBnary 同快照复核队列

> 共 203 项：Wiktextract 在同 lemma/POS 下有释义、而当前运行时 DBnary 没有定义的候选。此文件不含可发布释义。

- Wiktextract dump SHA-256：`040166ced172cacd029202fd98f99abe81cfaf91c5978fbe79137738a840aaec`
- 对齐 DBnary SHA-256：`aeb243f402c0acedade522842736e5885b025b5eb77894c45817b8f1bd12062f`
- 两者对应同一 `2026-07-01` Wiktionary 快照；DBnary 文件由官方目录发布。

## 当前结论

| 分类 | 数量 | 含义 |
|---|---:|---|
| pending_aligned_dbnary_snapshot | 0 | 等待从与 Wiktextract dump 同日期的 DBnary 历史提取物复核；不得判断为解析问题 |
| dbnary_aligned_extract_captured | 0 | 同快照 DBnary 已被现有导入器捕获；应调查当前生产快照/构建范围 |
| dbnary_parser_capture_gap | 0 | 同快照原始 DBnary 含定义信号但现有解析未捕获；修解析器后仍须审核内容 |
| dbnary_extract_entry_without_definition | 0 | 同快照 DBnary 有词条但未给可解析定义；属于 DBnary 提取覆盖限制 |
| dbnary_source_uncovered_same_snapshot | 203 | 同快照 DBnary 无匹配词条；属于 DBnary 来源覆盖限制 |

## 审校优先级

| 优先级 | CEFR | 数量 |
|---|---|---:|
| P0 | A1–A2 | 59 |
| P1 | B1 | 38 |
| P2 | B2 | 79 |
| P3 | C1–C2 | 27 |

## 审核规则

- 只有 `dbnary_parser_capture_gap` 可以进入导入器修复任务；修复后仍需重新构建和人工审校。
- 任何 Wiktextract 定义都不能直接进入 SQLite、运行时数据或教学内容。
- `review` 字段必须由具备法语词典审核资格的编辑填写；自动分类不是发布许可。
- 可编辑审校表为 `data/reports/dbnary-alignment-review-queue.csv`；JSON 是机器可读的权威队列。
