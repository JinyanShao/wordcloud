# wordcloud

Live Demo: https://jinyanshao.github.io/wordcloud/

An interactive French vocabulary graph demo built from DBnary/Wiktionary-derived lexical data.

面向中文母语者的法语词汇关系网络。不是词典，而是一张可以探索的词网：全景呈现学习进阶与自然词群，聚焦呈现每个词的正式关系、法语义项与教学辨析。

产品覆盖 A1–C1：A1/A2 只将编辑审校的基础核心词提升到主图，B1–C1 实词按可解释规则进入主图。这样保留基础学习入口，同时避免把整套 A1/A2 词表未经审校地扩张到关系图中。

### 不做什么

- 不是背单词软件，不提供间隔重复、打卡或复习队列——先把词和词的关系摆对位置，记忆交给你自己惯用的工具
- 不是词典，不追求释义完整度——法语释义来自 Wiktionnaire/DBnary 原文，是参考而不是产品核心
- 不用少量人工挑选的词群冒充"全局词网"——全景图基于完整候选词表和确定性坐标算法生成，不是先划定几个主题再填词

## 产品形态

- **全景词网**：7,400+ 词的交互散点图。半径表示学习进阶（越靠中心越高频、越基础），角度表示可信关系形成的自然词群，坐标构建时计算并固定，每次打开一致。
- **聚焦词网**：点击任意词，以它为中心发散出正式关系——不同关系不同颜色，实线为确认关系，虚线为少量自动候选。侧栏词卡优先展示关系绑定的具体法语义项（Wiktionnaire），再展示中文提示与关系辨析。
- **关系分层**：每种数据源只证明它能证明的事，不越界（详见下表）。

### 关系分层与来源边界

| 关系类型 | 生产方式 | 能证明什么 |
|---|---|---|
| `fam` 构词 | Démonette 直接派生 | 只回答"是不是直接词族"，不判断语义强弱或是否可互换 |
| `syn` / `ant` 近义 / 反义 | DBnary / Wiktionnaire 显式标注 | 只回答"词典是否明示"，标为"来源确认"，不代表已经过教学层面的细致辨析 |
| `compare` 教学辨析 | AI 起草，绑定具体义项后经编辑核实发布 | 例句在数据中标记为 `editorial_example` / `ai_drafted`；不写成"人工核对"，不冒充外部引用或独立人工逐句审校 |
| 拼写 / 读音相似 | 自动算法，高阈值筛选 | 只作虚线自动候选，从不冒充已确认的语言事实 |
| 中文释义重叠 | CFDICT | 只用于阅读提示和搜索召回，从不参与关系判定或制图坐标 |

只有通过完整证据（解释 + 例句 + 审校记录）的关系才会作为"经过编辑整理的词汇关系"公开显示；其余候选留在数据库里，不在界面上冒充已确认关系。

### 当前规模（如实分开统计）

- 7,405 个渲染节点，7,338 个主词（`eligible`），67 个官方关系支撑词，全图单连通分量
- 43,299 条法语义项定义，覆盖 8,748 个词
- 结构库中共有 4,576 条带来源的候选关系（词族派生、词典明示近义反义等），但只有其中 **43 条**通过完整审校证据、已作为"经过编辑整理的词汇关系"公开发布，覆盖 75 个词（含 2026-08 首批 20 条 Démonette 构词试点关系）
- 换句话说：数据层的"可追溯候选覆盖率"和界面上"用户实际能看到几条关系"是两个数字，不要混用——当前公开发布的教学关系数量还很小，这是有意为之的质量门槛，不是隐藏的缺口

## 快速开始

项目仓库：[JinyanShao/wordcloud](https://github.com/JinyanShao/wordcloud)。本地预览可直接启动静态服务器，无需构建：

```bash
python3 -m http.server 8000
# 打开 http://localhost:8000/index.html
```

## 静态发布

发布前先生成白名单静态包，避免把数据管线、审计报告和开发脚本一起发布：

```bash
pnpm check
pnpm smoke:browser
pnpm release:package
WORDCLOUD_STATIC_ROOT=dist pnpm smoke:browser
```

发布目录是 `dist/`。上线步骤、发布包边界和回滚步骤见 [docs/static-deployment.md](docs/static-deployment.md)。

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

`data/processed/editorial-seed.json` 的 `foundationalCore` 是产品 A1/A2 入口的编辑审校清单。每项按 lemma + POS 精确匹配，并保存中文教学提示、审校人和日期；它们必须同时拥有 DBnary 法语义项与图中的渲染节点，否则 `validate_data.py` 会失败。不要直接编辑 `graph-data.js`，修改清单后必须完整重建图数据。

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

词条详情将 DBnary 的法语义项及原始例句、编辑审校的常用搭配分别呈现。`editorial-seed.json` 的 `editorialLearning` 必须按 lemma + POS 绑定，并携带来源标签、审校人和日期；它不会将未审校的语言学断言伪装成审校内容。

## 隐私与本地数据

当前版本是静态网页，没有账号、服务器写入或跨设备同步。用户数据只保存在当前浏览器的 `localStorage`：

- `wordcloud.personal.v2`：我的词网节点和个人联想边
- `wordcloud.draft_cards.v1`：我的词卡中文提示和备注

“本地数据”里的导出 JSON 只读取这些本地记录，方便用户自查或备份；导出不会写入权威词库，也不会上传。清除浏览器站点数据会删除这些本地学习记录。

## 数据来源与许可

| 来源 | 用途 | 许可 |
|---|---|---|
| [FLELex / Beacco](https://cental.uclouvain.be/cefrlex/flelex/download/) | CEFR 等级与频率 | CC BY-NC-SA 4.0（**非商业**） |
| [Lexique 4.00](https://www.lexique.org/) | 词形、读音、频率 | CC BY-SA 4.0 |
| [Démonette 2.0](https://demonette.fr/) | 直接派生与词族 | CC BY-SA 4.0 |
| [DBnary（Wiktionnaire）](https://kaiko.getalp.org/about-dbnary/) | 法语义项、明示近义/反义 | CC BY-SA 3.0+ |
| [CFDICT](https://chine.in/mandarin/dictionnaire/CFDICT/) | 中文释义提示 | CC BY-SA 3.0 |

每个来源的版本、哈希与用途登记在 `data/sources.json`。

上线展示必须保留来源与许可提示，尤其是 FLELex / Beacco 的 CC BY-NC-SA 4.0 非商业限制。若未来要商业化或提供再分发包，需要替换该来源、取得额外授权，或重新评估衍生数据许可边界。

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
docs/                              部署、验收与项目延续说明
```
