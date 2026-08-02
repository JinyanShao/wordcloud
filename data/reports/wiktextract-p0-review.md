# Wiktextract P0 法语定义审校队列

> 59 个 A1–A2 DBnary 未覆盖词。候选来自固定日期法语 Wiktionnaire dump，经 Wiktextract 提取；未审核内容不得进入运行时。

- 候选词：59
- 候选义项：496
- 候选例句：728
- dump SHA-256：`040166ced172cacd029202fd98f99abe81cfaf91c5978fbe79137738a840aaec`
- Wiktextract commit：`d9fa2335957c9089ce2c3fb110a075cf072903da`

## 审核方法

1. 在 JSON 中查看每个词的候选义项及例句。
2. 在 CSV 中将 `review_status` 改为 `accepted` 或 `rejected`。
3. 接受时填写以 `|` 分隔的 `approved_sense_ids`、`reviewer`、`reviewed_at`；可在 `notes` 记录删改理由。
4. 重新运行 analyze 合并审核字段，再运行 approve；approve 会拒绝任何 pending 或无署名记录。

## 当前状态

| 状态 | 数量 |
|---|---:|
| pending | 0 |
| accepted | 58 |
| rejected | 1 |
