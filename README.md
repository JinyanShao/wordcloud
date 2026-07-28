# maillage

面向中文母语者的法语词汇关系网络。不是词典，而是一张可以探索的词网：全景呈现学习进阶与自然词群，聚焦呈现每个词的正式关系、法语义项与教学辨析。

## 产品形态

- **全景词网**：7,300+ 词的交互散点图。半径表示学习进阶（越靠中心越高频、越基础），角度表示可信关系形成的自然词群，坐标构建时计算并固定，每次打开一致。
- **聚焦词网**：点击任意词，以它为中心发散出正式关系——不同关系不同颜色，实线为确认关系，虚线为少量自动候选。侧栏词卡优先展示法语义项（Wiktionnaire），再展示中文提示与关系辨析。
- **关系分层**：词族派生（Démonette）、明示近义/反义（Wiktionnaire/DBnary）来自可追溯数据源；`compare` 等教学辨析由 AI 起草、人工终审后发布；拼写/读音相似只作为虚线候选，不冒充语言事实。

当前规模：7,900+ 个渲染节点 · 6,400+ 条正式关系 · 31,000+ 条法语义项定义 · 79% 主词至少有一条正式关系 · 全图单连通分量。

## 快速开始

直接使用右侧已deploy的页面（amphibi-ch.github.io/maillage）；或者浏览器直接用静态文件即可，无需构建：

```bash
python3 -m http.server 8000
# 打开 http://localhost:8000/index.html
```

## 数据管线

词网内容全部可重复构建，持久层是 `data/processed/` 下的 JSON 与 SQLite，浏览器只消费生成的 `graph-data.js`：

```bash
python3 -m pip install -r requirements-build.txt
pnpm install

python3 scripts/build_data.py build        # 词库（FleLex + Lexique + CFDICT）
python3 scripts/apply_audit_review.py      # 应用人工分层审核决定
python3 scripts/build_data.py sync-review
python3 scripts/build_graph.py             # 关系图：候选、正式边、制图边
node scripts/layout.mjs                    # 确定性坐标
python3 scripts/export_runtime.py          # 导出浏览器载荷
python3 scripts/validate_data.py           # 17 项不变量校验
```

辅助工具：

- `python3 scripts/build_gap_list.py` — 核心词缺口清单（哪些高频词最缺正式关系）
- `python3 scripts/ai_compare_draft.py` — 为高频近义对起草 `compare` 教学辨析（completion API，人工终审后入库）
- `python3 scripts/ai_first_edge_draft.py` — 为零关系核心词起草首条正式关系（同上）

完整说明见 [DATA_PIPELINE.md](DATA_PIPELINE.md)。

### AI 起草配置

两个 AI 起草脚本读取环境变量 `MAILLAGE_API_KEY` / `MAILLAGE_MODEL` / `MAILLAGE_API_BASE`，或项目根目录的 `.env.local`（已被 `.gitignore` 忽略，请勿提交密钥）。AI 草稿一律先写入 `data/processed/ai-*-drafts.json`，人工把 `review.status` 改为 `accepted` 后，下次 `build_graph.py` 重建时才进入正式词网——AI 生成物不会未经审校直接发布。

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
scripts/                           数据管线与 AI 起草脚本
sql/schema.sql                     SQLite 结构
data/sources.json                  来源登记
data/processed/                    持久层（SQLite、审核与草稿 JSON）
data/reports/                      构建验证与质量报告
handover/                          项目交接文档
```
