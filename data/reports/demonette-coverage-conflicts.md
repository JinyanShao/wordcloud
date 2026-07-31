# Démonette 2.0 覆盖率与冲突报告

> 结论：**通过自动发布质量门**。报告粒度为 maillage 当前可渲染 lemma+POS 与 Démonette 直接关系的精确对齐。

## 核心结果

- Démonette 原始规模：388,354 个 lexeme、222,118 条有向关系记录。
- 当前 7,391 个可渲染词汇单位中，7,346 个可与 Démonette lemma+POS 精确对齐（99.4%）。
- 经过跨词性、方向、复杂度和去重规则后，可发布 1,708 条来源确认的词族边。
- eligible 词的正式词族覆盖预计由 22/7,338（0.3%）提升到 2,801/7,338（38.2%），净新增覆盖 2,779 个词。

## 发布口径

- 发布 `orientation=as2des` 且 `complexite` 为 `simple` 或 `motiv-sem` 的跨词性关系。
- 同词性只发布方向明确、`simple`、且构式为前缀或后缀的直接派生；例如 `poli → impoli`。
- `simple` 表示直接、形式与语义一致的派生；`motiv-sem` 表示语义上直接但形式不规则，前端标为“异形词族”。
- 无法定向但两端均为 conversion 的 `simple` 跨词性关系，发布为无方向“词性转换”。
- `indirect`、`complexe`、`motiv-form`、`accidentel` 以及非简单词缀的同词性关系不发布。

## 跨词性覆盖

| 方向 | 正式边数 |
|---|---:|
| VER→NOM | 545 |
| NOM↔VER | 266 |
| NOM→ADJ | 244 |
| VER→ADJ | 194 |
| ADJ→NOM | 146 |
| NOM→NOM | 102 |
| NOM→VER | 72 |
| VER→VER | 62 |
| ADJ→VER | 37 |
| ADJ→ADJ | 33 |
| ADJ↔NOM | 7 |

### 关系类型

| 类型 | 边数 |
|---|---:|
| suffixation | 976 |
| conversion | 492 |
| prefixation | 136 |
| semantic_derivation | 104 |

## 完整性与冲突

| 检查 | 结果 |
|---|---|
| lexeme / relation 主键重复 | 0 / 0 |
| relation 引用缺失 lid | 0 |
| relation 文本/词性与 lexeme 表不一致 | 0 |
| 原始可发布记录折叠 | 3,197 → 1,708 条唯一边 |
| 同一词对方向冲突 | 1（0.059%） |
| 同一词对分类存在多个版本 | 16 |
| 与现有 trap 冲突并暂缓 | 0 |
| 与现有语义漂移边并存 | 4 |

多条原始记录通常来自 Démonette 合并的不同上游来源，不会在产品里重复成多条线；发布清单保留全部 `rid` 作为追溯记录。方向冲突词对整组暂缓，不参与发布。

## 三个回归样例

| 词对 | 是否进入发布清单 | Démonette 分类 | 产品显示 |
|---|---|---|---|
| affirmer → affirmation | 是 | simple / suffixation | 后缀 · -ion |
| voir → vision | 是 | motiv-sem / semantic_derivation | 异形词族 · -ion |
| poli_ADJ→impoli_ADJ | 是 | simple / prefixation | 前缀 · in- |

## 自动发布质量门

| 门槛 | 结果 |
|---|---|
| official_source_registered_and_hashed | 通过 |
| source_volume_is_plausible | 通过 |
| source_ids_are_unique | 通过 |
| relation_foreign_keys_are_complete | 通过 |
| row_identity_matches_lexeme_table | 通过 |
| direction_conflict_rate_below_0_5pct | 通过 |
| publishable_cross_pos_edges_exist | 通过 |
| affirmer_affirmation_regression | 通过 |
| voir_vision_regression | 通过 |
| poli_impoli_same_pos_regression | 通过 |

## 限制与下一步

- 本报告只衡量 maillage 当前词表与 Démonette 的精确 lemma+POS 对齐；未命中不等于 Démonette 无该词，可能是词性粒度或词表范围不同。
- 同词性只放行简单前/后缀直接派生；间接同族和复杂构词仍暂缓。
- `motiv-sem` 对学习者有价值，但必须保持“异形词族”标签，不能解释成规则性的拼写变化。
- 发布后应再次验证官方边来源完整、全图连通、运行时导出以及样例词的焦点图。
