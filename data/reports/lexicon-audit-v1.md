# 有效词表审计 · v1

> 构建时间：2026-07-27T00:00:00Z  
> 数据粒度：FLELex lemma + TreeTagger 词性；总计 14,251 个候选词汇单位。

## Intended use 与判定规则

自动进入主词表的词，必须是 B1–C1 的名词、动词、形容词或实义副词，能与 Lexique 4 的 lemma+POS 对齐，并满足以下至少一项：

- CFDICT 有中文释义候选；
- FLELex 总频率 ≥ 1.0/百万。

封闭类虚词与 A1/A2 实词进入 auxiliary，不计入主覆盖率；只有已审核官方关系实际用到的少量 auxiliary 才作为支撑节点进入星图。人工抽检覆盖可以修正自动状态，所有例外都保留 manual_audit_override 原因。

## 数据源与规模

| 数据源 | 原始行数/词条 | 用途 |
|---|---:|---|
| FLELex / Beacco | 14,236 | CEFR、词性、学习语料频率 |
| Lexique 4.00 | 189,863 | lemma、频率、IPA、形态 |
| CFDICT 本地反向索引 | 20,664 | 中文释义候选 |

## 对齐质量

在 9,942 个 B1–C1 实词候选中：

- Lexique lemma+POS 精确匹配：9,632（96.9%）
- CFDICT 词形匹配：6,359（64.0%）
- 三方同时匹配：6,257（62.9%）

**高风险发现：CFDICT 覆盖不是随机缺失。它遗漏了一批常用 B1/B2 词，因此不能把“CFDICT 无释义”直接等同于低价值。当前规则用 FLELex 频率兜底，并将这些词保留为 eligible、标记待补释义。**

## 自动判定结果

| 状态 | 数量 | 占比 |
|---|---:|---:|
| eligible | 7,314 | 51.3% |
| needs_review | 3,730 | 26.2% |
| auxiliary | 1,966 | 13.8% |
| excluded | 1,241 | 8.7% |

### eligible：CEFR × 词性

| CEFR | POS | 数量 |
|---|---|---:|
| B1 | ADJ | 257 |
| B1 | ADV | 83 |
| B1 | NOM | 965 |
| B1 | VER | 394 |
| B2 | ADJ | 900 |
| B2 | ADV | 141 |
| B2 | NOM | 2,341 |
| B2 | VER | 864 |
| C1 | ADJ | 271 |
| C1 | ADV | 34 |
| C1 | NOM | 825 |
| C1 | VER | 219 |
| C2 | ADJ | 6 |
| C2 | ADV | 1 |
| C2 | NOM | 6 |
| C2 | VER | 7 |

### 判定原因

| 状态 | 原因 | 数量 |
|---|---|---:|
| eligible | target_content_with_gloss | 6,251 |
| needs_review | low_frequency_missing_gloss | 2,307 |
| auxiliary | foundational_content | 1,748 |
| needs_review | advanced_tail | 1,119 |
| excluded | outside_target_cefr | 994 |
| eligible | target_content_high_frequency_missing_gloss | 985 |
| needs_review | missing_lexique_alignment | 294 |
| excluded | missing_lexique_alignment_outside_target | 159 |
| auxiliary | closed_class | 130 |
| auxiliary | functional_adverb | 56 |
| eligible | manual_audit_override:low_frequency_missing_gloss | 56 |
| excluded | non_content_pos | 53 |
| excluded | manual_audit_override:low_frequency_missing_gloss | 18 |
| eligible | manual_audit_override:advanced_tail | 17 |
| auxiliary | editorial_seed_support | 15 |
| auxiliary | manual_audit_override:advanced_tail | 11 |
| excluded | manual_audit_override:missing_lexique_alignment | 8 |
| excluded | manual_audit_override:target_content_high_frequency_missing_gloss | 4 |
| needs_review | manual_audit_defer:advanced_tail | 4 |
| eligible | manual_audit_override:outside_target_cefr | 3 |
| auxiliary | manual_audit_override:missing_lexique_alignment | 2 |
| auxiliary | manual_audit_override:missing_lexique_alignment_outside_target | 2 |
| eligible | manual_audit_override:missing_lexique_alignment | 2 |
| excluded | manual_audit_override:advanced_tail | 2 |
| needs_review | manual_audit_defer:low_frequency_missing_gloss | 2 |
| needs_review | manual_audit_defer:missing_lexique_alignment | 2 |
| auxiliary | manual_audit_override:outside_target_cefr | 1 |
| auxiliary | manual_audit_override:target_content_with_gloss | 1 |
| excluded | invalid_surface | 1 |
| excluded | manual_audit_override:complex_expression | 1 |
| excluded | manual_audit_override:target_content_with_gloss | 1 |
| needs_review | manual_audit_defer:missing_lexique_alignment_outside_target | 1 |
| needs_review | manual_audit_defer:outside_target_cefr | 1 |

## CFDICT 缺失但因高频保留的示例

| lemma | POS | CEFR | FLELex freq/百万 |
|---|---|---|---:|
| travers | NOM | B1 | 129.723 |
| lors | ADV | B1 | 126.313 |
| plupart | NOM | B1 | 108.364 |
| événement | NOM | B1 | 79.834 |
| familial | ADJ | B1 | 77.279 |
| littéraire | ADJ | B1 | 66.561 |
| dizaine | NOM | B1 | 47.153 |
| millier | NOM | B1 | 45.74 |
| absence | NOM | B1 | 45.687 |
| revanche | NOM | B1 | 44.557 |
| destiner | VER | B1 | 43.613 |
| cesse | NOM | B2 | 36.14 |
| religieux | ADJ | B1 | 36.14 |
| consister | VER | B1 | 35.748 |
| issu | ADJ | B2 | 33.381 |
| largement | ADV | B1 | 31.55 |
| urbain | ADJ | B1 | 31.13 |
| forcément | ADV | B2 | 29.556 |
| réagir | VER | B1 | 26.056 |
| alimentaire | ADJ | B1 | 24.499 |
| trentaine | NOM | B1 | 22.401 |
| judiciaire | ADJ | B2 | 21.721 |
| doter | VER | B2 | 21.56 |
| contenter | VER | B1 | 21.484 |
| redescendre | VER | B1 | 19.623 |

## 500 条分层人工抽检

`lexicon-audit-sample-500.csv` 使用固定随机种子 20260727，按 status × reason × CEFR × POS 分层抽取。空白不代表通过；只有 reviewer 与 reviewed_at 完整才算完成抽检。

- 已人工检查：500/500
- 同意自动状态：361（72.2%）
- 覆盖自动状态：129（25.8%）
- 暂缓判断：10
- 明确标记 CFDICT/释义问题：32

## 自动化质量门

- sources.sha256 必须完整；
- lexemes(normalized, pos) 唯一；
- 自动 eligible 必须为 B1–C1 实词且存在 Lexique 对齐；人工覆盖例外必须带 manual_audit_override；
- 自动 eligible 若缺 CFDICT，FLELex frequency 必须 ≥ 1/百万；人工覆盖例外同上；
- audit sample 必须恰好 500 条且无重复 lexeme；
- 任何 layout link 和 official edge 必须满足端点存在、a_id < b_id。

## 当前限制

- FLELex 为 CC BY-NC-SA 4.0，当前成果仅适用于非商业原型；
- CFDICT 释义质量尚未逐条验证；
- 多义词目前仍按 lemma+POS 合并；
- eligibility 的 1/百万阈值是 v1 可解释规则，需要结合 500 条抽检结果再校准。
