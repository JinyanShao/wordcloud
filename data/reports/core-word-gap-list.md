# 核心词缺口清单

> 生成命令：`python3 scripts/build_gap_list.py`。明细见 `core-word-gap-list.csv`（可排序，`in_core=1` 为本轮核心词）。

## 总览

- eligible 主词：7,338
- 存在至少一类缺口的词：7,262（99.0%）
- 本轮核心词目标：1,000 个，按缺口优先级与频率排序取前 1,000

| 优先级 | 缺口类型 | 全部 | 进入核心词 |
|---|---|---:|---:|
| P1_no_official | 高频且没有任何官方关系 | 2,899 | 1,000 |
| P2_single_edge | 高频且只有一条官方关系 | 2,344 | 0 |
| P3_bridge | 多义项桥接词（义项多、连接少） | 632 | 0 |
| P4_confusable | 易混淆候选（有形音候选、无正式 trap/compare） | 1,384 | 0 |
| P5_b2c1_synset | B2–C1 近义集合缺口（有义项、无近/反义边） | 3 | 0 |

一词可命中多类缺口；命中各类的总词数（不限主桶）如下：

| 缺口类型 | 命中词数（含非主桶） |
|---|---:|
| P1_no_official | 2,899 |
| P2_single_edge | 2,344 |
| P3_bridge | 2,681 |
| P4_confusable | 6,810 |
| P5_b2c1_synset | 3,509 |

## 判定规则

- P1：官方关系数 = 0；P2：官方关系数 = 1。
- P3：法语义项数 ≥ 4 且官方关系数 ≤ 2。
- P4：存在 spelling/phonetic 候选，但没有任何正式 trap/compare 边。
- P5：CEFR 为 B2–C2、能对齐 DBnary 义项，但没有任何明示 syn/ant 边。
- 一词可同时命中多类（见 CSV 的 `flags`），`bucket` 取最高优先级；同优先级内按频率降序。
- 频率取 FleLex 频率，缺失时回退 Lexique 词元频率。

## P1 高频零关系 Top 20

| 词 | 词性 | CEFR | 频率 | 义项数 | 形音候选 | 中文提示 |
|---|---|---|---:|---:|---:|---|
| travers | NOM | B1 | 129.7 | 7 | 3 |  |
| sorte | NOM | B1 | 129.5 | 3 | 3 | 种类 |
| lors | ADV | B1 | 126.3 | 2 | 5 |  |
| plupart | NOM | B1 | 108.4 | 2 | 0 |  |
| professionnel | ADJ | B1 | 107.6 | 2 | 4 | 专业；专业人员 |
| politique | NOM | B1 | 103.7 | 8 | 5 | 国事；政事 |
| intérêt | NOM | B1 | 95.4 | 9 | 3 | 兴致；兴趣 |
| poche | NOM | B1 | 89.3 | 33 | 2 | 口袋；囊袋 |
| phénomène | NOM | B1 | 87.0 | 6 | 2 | 怪人；怪圈 |
| que | ADV | B1 | 83.0 | 3 | 4 | 什么；哪一个 |
| adresser | VER | B1 | 79.3 | 4 | 3 | 致 |
| danger | NOM | B1 | 77.5 | 1 | 2 | 危险；危难 |
| familial | ADJ | B1 | 77.3 | 1 | 6 |  |
| franc | NOM | B1 | 71.0 | 4 | 6 | 坦率；坦白 |
| courant | NOM | B1 | 70.9 | 13 | 4 | 常务；常见 |
| preuve | NOM | B1 | 69.4 | 5 | 2 | 佐证；凭证 |
| chercheur | NOM | B2 | 67.6 | 4 | 3 | 研究人员；研究员 |
| littéraire | ADJ | B1 | 66.6 | 3 | 1 |  |
| oser | VER | B1 | 65.9 | 4 | 1 | 勇于；敢于 |
| appel | NOM | B1 | 56.6 | 16 | 6 | 申诉；诉求 |

## P2 高频单关系 Top 20

| 词 | 词性 | CEFR | 频率 | 已有关系 | 中文提示 |
|---|---|---|---:|---|---|
| être | VER | A1 | 28371.5 | syn×1 | 是；处于 |
| avoir | VER | A1 | 19212.1 | syn×1 | 有；拥有 |
| venir | VER | A1 | 1547.0 | other×1 | 来；来到 |
| pauvre | ADJ | B1 | 139.2 | fam×1 | 可怜；困苦 |
| état | NOM | B1 | 123.0 | syn×1 | 国家；国度 |
| commissaire | NOM | B1 | 117.9 | fam×1 | 专员；总监 |
| assurer | VER | B1 | 103.5 | syn×1 | 保证；保障 |
| crime | NOM | B1 | 92.0 | fam×1 | 犯罪；犯罪行为 |
| valoir | VER | B1 | 91.4 | fam×1 | 值得；有价值 |
| terme | NOM | B2 | 89.5 | ant×1 | 尽头；届满 |
| contraire | NOM | B1 | 88.3 | syn×1 | 反义；相反 |
| formation | NOM | B1 | 82.4 | syn×1 | 地层；教养 |
| événement | NOM | B1 | 79.8 | syn×1 |  |
| rejoindre | VER | B1 | 75.4 | fam×1 | 加入；加盟 |
| tendance | NOM | B1 | 73.5 | fam×1 | 倾向；动向 |
| affirmer | VER | B1 | 73.0 | fam×1 | 断定；断言 |
| comportement | NOM | B1 | 72.9 | fam×1 | 为人；习性 |
| majorité | NOM | B1 | 70.4 | fam×1 | 大多数 |
| planète | NOM | B1 | 69.9 | fam×1 | 地球；星球 |
| atteindre | VER | B1 | 67.6 | fam×1 | 击中；到达 |
