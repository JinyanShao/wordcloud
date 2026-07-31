# DBnary 同快照复核队列

> 共 203 项：Wiktextract 在同 lemma/POS 下有释义、而当前运行时 DBnary 没有定义的候选。此文件不含可发布释义。

## 当前结论

| 分类 | 数量 | 含义 |
|---|---:|---|
| pending_aligned_dbnary_snapshot | 203 | 等待从与 Wiktextract dump 同日期的 DBnary 历史提取物复核；不得判断为解析问题 |
| dbnary_aligned_extract_captured | 0 | 同快照 DBnary 已被现有导入器捕获；应调查当前生产快照/构建范围 |
| dbnary_parser_capture_gap | 0 | 同快照原始 DBnary 含定义信号但现有解析未捕获；修解析器后仍须审核内容 |
| dbnary_extract_entry_without_definition | 0 | 同快照 DBnary 有词条但未给可解析定义；属于 DBnary 提取覆盖限制 |
| dbnary_source_uncovered_same_snapshot | 0 | 同快照 DBnary 无匹配词条；属于 DBnary 来源覆盖限制 |

## 审核规则

- 只有 `dbnary_parser_capture_gap` 可以进入导入器修复任务；修复后仍需重新构建和人工审校。
- 任何 Wiktextract 定义都不能直接进入 SQLite、运行时数据或教学内容。
- `review` 字段必须由具备法语词典审核资格的编辑填写；自动分类不是发布许可。
