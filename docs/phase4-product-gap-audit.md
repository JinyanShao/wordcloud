# Phase 4A — Product Gap Audit

这是对 production 静态输入的覆盖审计，不是用户行为分析；不生成 learner content，也不改变任何事实数据。

## 覆盖现状

- searchable lexical entries：9067；eligible main-map entries：9046；support entries：21。
- learner aids：598（eligible content 的 6.61%；全部 searchable 的 6.6%）。
- cohorts：Phase 2C 99 reviewed；Phase 3 499 externally semantic-authored。

| CEFR | eligible entries | learner aids | coverage |
|---|---:|---:|---:|
| A1 | 1093 | 268 | 24.52% |
| A2 | 649 | 232 | 35.75% |
| B1 | 1695 | 74 | 4.37% |
| B2 | 4242 | 24 | 0.57% |
| C1 | 1347 | 0 | 0.0% |
| C2 | 20 | 0 | 0.0% |

## 最大结构性缺口

- 整体覆盖仍只有 6.61%；A1、A2 并非已覆盖完毕，且 B1/B2 覆盖明显更低。
- POS 不均衡：NOM 的覆盖低于 VER、ADJ 和 ADV；完整 CEFR × POS 与 frequency band 明细见 JSON。
- 4231 个 sourced-family members 没有 learner aid；现有 410 条 learner aids 有 sourced family，188 条没有。
- 没有生产点击、完成或留存数据；CEFR、FLELex、Lexique、contextual diversity、多义性和 family 连通性只是静态排序 proxy，不能称作用户需求。

## 高频缺口（每组展示前 12；完整前 50 在 JSON）

### A1

| 词条 | POS | CEFR | FLELex | Lexique | CD | family | senses |
|---|---|---:|---:|---:|---:|---:|---:|
| autre\|ADJ | ADJ | A1 | 2237.400 | 812.582 | 95.086 | yes | 0 |
| même\|ADJ | ADJ | A1 | 900.835 | 427.671 | 95.439 | no | 0 |
| oeil\|NOM | NOM | A1 | 543.748 | 384.203 | 56.231 | no | 0 |
| partie\|NOM | NOM | A1 | 261.405 | 249.241 | 65.159 | yes | 12 |
| âge\|NOM | NOM | A1 | 260.077 | 109.405 | 30.432 | yes | 7 |
| société\|NOM | NOM | A1 | 258.015 | 72.563 | 17.289 | no | 13 |
| musique\|NOM | NOM | A1 | 256.213 | 133.377 | 24.801 | yes | 9 |
| rien\|NOM | NOM | A1 | 254.695 | 6.421 | 97.921 | no | 3 |
| suite\|NOM | NOM | A1 | 252.810 | 237.642 | 56.349 | no | 18 |
| fenêtre\|NOM | NOM | A1 | 251.121 | 73.076 | 17.851 | no | 10 |
| café\|NOM | NOM | A1 | 249.796 | 129.275 | 31.073 | no | 6 |
| milieu\|NOM | NOM | A1 | 248.833 | 73.500 | 25.367 | no | 13 |

### A2

| 词条 | POS | CEFR | FLELex | Lexique | CD | family | senses |
|---|---|---:|---:|---:|---:|---:|---:|
| seul\|NOM | NOM | A2 | 85.945 | 106.728 | 78.363 | no | 0 |
| communauté\|NOM | NOM | A2 | 53.096 | 25.462 | 7.483 | yes | 9 |
| décision\|NOM | NOM | A2 | 53.062 | 94.453 | 23.299 | yes | 2 |
| galerie\|NOM | NOM | A2 | 51.842 | 11.009 | 2.535 | no | 26 |
| liste\|NOM | NOM | A2 | 51.109 | 104.133 | 25.571 | no | 4 |
| ingénieur\|NOM | NOM | A2 | 51.091 | 15.475 | 3.328 | no | 1 |
| conversation\|NOM | NOM | A2 | 50.316 | 62.234 | 18.983 | yes | 5 |
| carrière\|NOM | NOM | A2 | 50.208 | 51.813 | 16.246 | no | 12 |
| discours\|NOM | NOM | A2 | 49.970 | 42.566 | 11.966 | no | 5 |
| secteur\|NOM | NOM | A2 | 49.741 | 22.554 | 6.269 | no | 11 |
| profession\|NOM | NOM | A2 | 49.636 | 7.861 | 2.932 | yes | 6 |
| progrès\|NOM | NOM | A2 | 49.200 | 17.747 | 6.957 | yes | 4 |

### B1

| 词条 | POS | CEFR | FLELex | Lexique | CD | family | senses |
|---|---|---:|---:|---:|---:|---:|---:|
| travers\|NOM | NOM | B1 | 129.723 | 80.095 | 25.599 | no | 7 |
| crime\|NOM | NOM | B1 | 92.036 | 123.896 | 22.498 | yes | 6 |
| maladie\|NOM | NOM | B1 | 90.996 | 57.076 | 13.324 | yes | 4 |
| assassin\|NOM | NOM | B1 | 90.749 | 36.674 | 8.334 | yes | 2 |
| victime\|NOM | NOM | B1 | 89.662 | 148.930 | 18.507 | no | 5 |
| poche\|NOM | NOM | B1 | 89.266 | 51.130 | 13.455 | no | 33 |
| contraire\|NOM | NOM | B1 | 88.295 | 44.057 | 18.746 | no | 1 |
| phénomène\|NOM | NOM | B1 | 87.044 | 8.953 | 2.532 | no | 6 |
| mesure\|NOM | NOM | B1 | 86.662 | 35.032 | 10.317 | yes | 15 |
| formation\|NOM | NOM | B1 | 82.423 | 16.864 | 5.516 | yes | 13 |
| individu\|NOM | NOM | B1 | 81.959 | 13.709 | 3.194 | yes | 6 |
| événement\|NOM | NOM | B1 | 79.834 | 28.108 | 5.721 | no | 1 |

### B2

| 词条 | POS | CEFR | FLELex | Lexique | CD | family | senses |
|---|---|---:|---:|---:|---:|---:|---:|
| cesse\|NOM | NOM | B2 | 36.140 | 17.864 | 10.311 | yes | 2 |
| protection\|NOM | NOM | B2 | 33.357 | 35.623 | 11.436 | yes | 5 |
| criminel\|NOM | NOM | B2 | 33.256 | 40.022 | 9.346 | no | 3 |
| quantité\|NOM | NOM | B2 | 32.115 | 14.038 | 4.806 | no | 5 |
| sondage\|NOM | NOM | B2 | 31.182 | 6.282 | 1.092 | no | 10 |
| univers\|NOM | NOM | B2 | 30.879 | 36.171 | 9.069 | yes | 12 |
| fonctionnement\|NOM | NOM | B2 | 30.689 | 3.652 | 1.549 | yes | 1 |
| éprouver\|VER | VER | B2 | 30.474 | 12.902 | 1.684 | yes | 4 |
| introduire\|VER | VER | B2 | 30.471 | 15.190 | 2.655 | yes | 8 |
| égalité\|NOM | NOM | B2 | 30.341 | 7.696 | 2.730 | yes | 6 |
| échelle\|NOM | NOM | B2 | 29.668 | 17.709 | 6.053 | no | 12 |
| favoriser\|VER | VER | B2 | 29.616 | 3.247 | 0.432 | yes | 4 |

## 策略比较与推荐

| 策略 | learner value | authoring / QA 成本 | 风险与边际收益 |
|---|---|---|---|
| A 再扩 500 | 覆盖面大但递减 | 很高 / 很高 | sense-priority 与质量风险高，边际收益高递减 |
| B 补 100–200 高价值缺口 | 高 | 中 / 中 | learner-first review 可控，递减低到中 |
| C 加深现有 598 | 中 | 中 / 中 | 价值集中于已覆盖词，可能回避真正缺口 |
| D family-learning 优先 | 中高 | 低中 / 中 | 不能把 sourced morphology 夸大为机械规则 |
| E 有界混合 | 最高 | 中 / 中 | 需固定范围与独立 semantic review，递减低 |

**推荐：Strategy E，但由 Strategy B 主导。** 先对 100–200 个高频 A1/A2/B1 缺口做 learner-first sense review；只在已有 sourced relation 对学习确有价值时补充 family context。不要再启动无差别的 500 条批次。

**Phase 4A conclusion：Phase 3 is closed.**
