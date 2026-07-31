# Wiktextract 与 DBnary 缺口差异审计

> 审计 327 个运行时学习词中缺少 DBnary 定义的词。Wiktextract 仅用于分类，不自动发布其结果。

## 可复现输入

- dump：`data/raw/wiktextract/frwiktionary-20260701-pages-articles.xml.bz2`
- SHA-256：`040166ced172cacd029202fd98f99abe81cfaf91c5978fbe79137738a840aaec`
- extractor：Wiktextract 1.99.7，Git commit `d9fa2335957c9089ce2c3fb110a075cf072903da`（MIT 代码）
- lexical data：French Wiktionary；后续任何发布仍须按 Wiktionary/CC BY-SA 要求归属与许可。

## 分类

| 分类 | 数量 | 占缺口比例 | 含义与处理建议 |
|---|---:|---:|---|
| wiktionary_usable_differential | 203 | 62.1% | 较新 Wiktionary 快照有同词性释义；属 DBnary 快照/解析差异候选，须同版本复核后才能认定解析漏捕 |
| matched_without_definition | 0 | 0.0% | 检查模板、重定向或词形条目；不得自动补定义 |
| lemma_found_pos_mismatch | 122 | 37.3% | 进入 lemma/POS 映射审计队列 |
| not_found_in_dump | 2 | 0.6% | 标为来源未覆盖，进入独立来源或人工编纂队列 |

## 每类样本

### wiktionary_usable_differential

- abeille · NOM · B2
- abondance · NOM · B2
- aboutir · VER · B2
- accessoire · NOM · B2
- accident · NOM · A1
- achat · NOM · A2
- affecter · VER · B2
- agiter · VER · B1
- anonymat · NOM · B2
- antenne · NOM · B2
- appartenir · VER · A2
- assemblage · NOM · B2

### lemma_found_pos_mismatch

- abondamment · ADV · B2
- administratif · ADJ · A2
- agile · ADJ · B2
- antan · NOM · B2
- antique · ADJ · B2
- atmosphérique · ADJ · B2
- autre · ADJ · A1
- blessé · ADJ · B2
- bon · ADV · B1
- boeuf · NOM · A1
- cancérogène · NOM · C1
- capital · ADJ · B2

### not_found_in_dump

- vitro · NOM · B2
- voeu · NOM · A2
