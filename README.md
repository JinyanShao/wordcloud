# wordcloud

面向中文母语者的法语词汇关系网络。不是词典，而是一张可以探索的词网：全景呈现学习进阶与自然词群，聚焦呈现每个词的正式关系、法语义项与教学辨析。

产品覆盖 A1–C1：A1/A2 只将人工审校的基础核心词提升到主图，B1–C1 实词按可解释规则进入主图。这样保留基础学习入口，同时避免把整套 A1/A2 词表未经审校地扩张到关系图中。

## 产品形态

- **全景词网**：7,300+ 词的交互散点图。半径表示学习进阶（越靠中心越高频、越基础），角度表示可信关系形成的自然词群，坐标构建时计算并固定，每次打开一致。
- **聚焦词网**：点击任意词，以它为中心发散出正式关系——不同关系不同颜色，实线为确认关系，虚线为少量自动候选。侧栏词卡优先展示法语义项（Wiktionnaire），再展示中文提示与关系辨析。
- **关系分层**：词族派生（Démonette）、明示近义/反义（Wiktionnaire/DBnary）来自可追溯数据源；教学辨析须由编辑审核后发布；拼写/读音相似只作为虚线候选，不冒充语言事实。

当前规模：7,900+ 个渲染节点 · 6,400+ 条正式关系 · 31,000+ 条法语义项定义 · 79% 主词至少有一条正式关系 · 全图单连通分量。

## 快速开始

项目仓库：[JinyanShao/wordcloud](https://github.com/JinyanShao/wordcloud)。本地预览可直接启动静态服务器，无需构建：

```bash
python3 -m http.server 8000
# 打开 http://localhost:8000/index.html
```

## 数据管线

词网内容全部可重复构建，持久层是 `data/processed/` 下的 JSON 与 SQLite，浏览器只消费生成的 `graph-data.js`：

发布候选请使用锁定来源的完整构建，而不是手动跳过步骤：

```bash
pnpm data:fetch
pnpm build:verified
```

它会验证每份原始语料的 SHA-256、重建全部生成物，并生成 `data/reports/build-manifest.json`。详见 [DATA_PIPELINE.md](DATA_PIPELINE.md)。

```bash
python3 -m pip install -r requirements-build.txt
pnpm install

python3 scripts/build_data.py build        # 词库（FleLex + Lexique + CFDICT）
python3 scripts/apply_audit_review.py      # 应用人工分层审核决定
python3 scripts/build_data.py sync-review
python3 scripts/build_graph.py             # 关系图：候选、正式边、制图边
node scripts/layout.mjs                    # 确定性坐标
python3 scripts/export_runtime.py          # 导出浏览器载荷
python3 scripts/validate_data.py           # 数据、核心词与运行时不变量校验
```

辅助工具：

- `python3 scripts/build_gap_list.py` — 核心词缺口清单（哪些高频词最缺正式关系）

完整说明见 [DATA_PIPELINE.md](DATA_PIPELINE.md)。

### 基础核心词

`data/processed/editorial-seed.json` 的 `foundationalCore` 是产品 A1/A2 入口的人工审核清单。每项按 lemma + POS 精确匹配，并保存中文教学提示、审核人和日期；它们必须同时拥有 DBnary 法语义项与图中的渲染节点，否则 `validate_data.py` 会失败。不要直接编辑 `graph-data.js`，修改清单后必须完整重建图数据。

### Wiktextract 差异审计

当运行时学习词仍缺少 DBnary 法语定义时，可用固定版本的 [Wiktextract](https://github.com/tatuylonen/wiktextract) 对官方 French Wiktionary dump 做只读差异审计：它不自动写入 SQLite 或运行时词典。

```bash
python3 -m venv /tmp/wordcloud-wiktextract
/tmp/wordcloud-wiktextract/bin/pip install -r requirements-wiktextract-audit.txt
WIKTWORDS_BIN=/tmp/wordcloud-wiktextract/bin/wiktwords pnpm wiktextract:audit
```

将对应月份的 dump 放入 `data/raw/wiktextract/`，再运行命令。报告会明确区分“较新快照有可用释义、但尚不能证明 DBnary 解析漏捕”、“lemma/POS 不匹配”与“该 dump 未覆盖”；原始 dump 和 JSONL 均不纳入 Git。

DBnary 同快照复核后，A1–A2 来源覆盖缺口使用同一份 Wiktextract JSONL 建立人工审校队列：

```bash
pnpm wiktextract:p0:analyze
# 审校 data/reports/wiktextract-p0-review.csv
pnpm wiktextract:p0:analyze
pnpm wiktextract:p0:approve
```

`approve` 要求每个词均已决定，且被接受的词包含批准义项 ID、审核人和审核日期。待审候选不会进入 SQLite 或运行时。

### 学习表层

词条详情将 DBnary 的法语义项及原始例句、编辑审校的常用搭配和编辑审校的词源线索分别呈现。`editorial-seed.json` 的 `editorialLearning` 必须按 lemma + POS 绑定，并携带来源标签、审校人和日期；它不会将自动生成的语言学断言伪装成审校内容。

### 本地学习循环

“加入复习”会把词条保存在当前浏览器的本地学习循环中。新词立即到期；显示提示后可选择“不记得、模糊、记得、很熟”，分别安排 10 分钟、1 天、递增间隔和更长间隔后的下一次复习。学习记录不上传、不依赖账号。

## 数据来源与许可

| 来源 | 用途 | 许可 |
|---|---|---|
| [FLELex / Beacco](https://cental.uclouvain.be/cefrlex/flelex/download/) | CEFR 等级与频率 | CC BY-NC-SA 4.0（**非商业**） |
| [Lexique 4.00](https://www.lexique.org/) | 词形、读音、频率 | CC BY-SA 4.0 |
| [Démonette 2.0](https://demonette.fr/) | 直接派生与词族 | CC BY-SA 4.0 |
| [DBnary（Wiktionnaire）](https://kaiko.getalp.org/about-dbnary/) | 法语义项、明示近义/反义 | CC BY-SA 3.0+ |
| [CFDICT](https://chine.in/mandarin/dictionnaire/CFDICT/) | 中文释义提示 | CC BY-SA 3.0 |

每个来源的版本、哈希与用途登记在 `data/sources.json`。

## 许可

- 代码：暂未指定开源许可（保留所有权利，待补充 LICENSE 文件）
- 数据产物：受上表各来源许可约束。**注意 FLELex 为 CC BY-NC-SA 4.0，本项目及其衍生数据产物不得用于商业用途**，再分发时需保留署名并以相同方式共享。

## 仓库结构

```
index.html / app.js / styles.css   浏览器端（无框架，canvas 渲染）
graph-data.js                      生成的浏览器载荷（勿手改）
scripts/                           数据管线
sql/schema.sql                     SQLite 结构
data/sources.json                  来源登记
data/processed/                    持久层（SQLite 与审核 JSON）
data/reports/                      构建验证与质量报告
handover/                          项目交接文档
```
