# DBnary 义项与语义关系质量报告

> 结论：**通过发布质量门**。粒度为当前可渲染 lemma+POS、DBnary 词条组和具体义项。

## 覆盖率

- 当前 7,371 个可渲染词汇单位中，7,129 个能对齐至 DBnary 词条（96.7%）。
- 7,129 个词有至少一条法语义项定义，共 31,328 条定义。
- 输入关系折叠为 2,720 条唯一语义边，覆盖 2,828 个词。

## 语义关系

| 关系 | 条数 |
|---|---:|
| syn | 2,200 |
| ant | 520 |

## 关键词例

| 检查 | 结果 |
|---|---|
| poli 多义项 | 2 个词条组 / 4 条定义 |
| poli–respectueux 近义 | 通过 |
| poli–impoli 反义 | 通过 |
| seau–nager 不得成为近义 | 通过 |

## 完整性与冲突

- 对齐后原始关系 2,960 行，去重后 2,720 条。
- 同一词对同时标为近义与反义的 2 组，全部暂缓发布。
- 未对齐目标：{"synonym": 5589, "antonym": 1062, "approximateSynonym": 507}。这些不会自动扩充当前词表。

## 自动发布质量门

| 门槛 | 结果 |
|---|---|
| official_snapshot_hash_matches | 通过 |
| rendered_lexeme_alignment_above_80pct | 通过 |
| sense_definitions_exist | 通过 |
| explicit_semantic_edges_exist | 通过 |
| contradiction_rate_below_1pct | 通过 |
| poli_has_multiple_sense_groups | 通过 |
| poli_respectueux_is_synonym | 通过 |
| poli_impoli_is_antonym | 通过 |
| seau_nager_is_not_synonym | 通过 |

## 限制

- DBnary 反映 Wiktionnaire 的明示关系，有来源但不等于已经 maillage 人工辨析。前端必须显示为“来源确认”，不得冒充“已审校”。
- 语义关系只在目标词以相同词性存在于当前词表时发布，避免多词性词误连。
- 本轮不导入 DBnary `derivedFrom`；构词关系仍由 Démonette 负责。
