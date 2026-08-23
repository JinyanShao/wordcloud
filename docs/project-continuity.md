# 项目延续说明

这份文档用于在聊天记录、账号或上下文丢失时继续推进项目。

## 当前状态

项目名称：`wordcloud`

项目位置：`/Users/jinyanshao/Developer/wordcloud`

GitHub 仓库：`https://github.com/JinyanShao/wordcloud`

线上试用地址：`https://jinyanshao.github.io/wordcloud/`

当前产品是一张面向中文母语者的法语词汇关系网。它不是普通词典，而是让用户从一个法语词出发，查看词根、派生、近义、反义、搭配、例句和学习提示，并沿着关系继续探索。

当前技术形态：

- 纯静态网站
- 无后端
- 无账号
- 无跨设备同步
- 用户学习记录只保存在当前浏览器的 `localStorage`
- GitHub Pages 从 `dist/` 发布
- `dist/` 由 `pnpm release:package` 生成，不纳入 Git

当前本地 Git 状态：

- `main` 与 `origin/main` 指向同一个提交：`4902eab Add live demo link to README`
- GitHub Pages 最近一次部署成功
- 本地有一个未提交的 `.gitignore` 小改动，内容是增加缓存和日志忽略规则

## 产品定位

目标用户：已经有一定法语词汇积累的中文母语学习者。

核心需求：看到一个法语词时，想知道它和哪些词有关，并通过关系、用法和例句更好地记住它。

第一阶段产品形态：

- 首页是可探索的法语词网
- 用户从搜索框输入法语词
- 点击图上节点进入中心词卡
- 中心词卡展示法语词、词性、中文提示、法语释义、例句、常用搭配、同根词、学习等级和收藏/复习入口
- 用户可以把词或关系加入本地复习
- 用户可以创建和编辑自己的词卡备注
- 本地数据可以导出 JSON

## 已经完成

1. 静态词网

- 已有 canvas 词网
- 支持全景词网和聚焦词网
- 支持点击节点切换中心词
- 保留当前词网视觉形态

2. 搜索与找不到处理

- 支持普通词搜索
- 支持 `se lever` 这类多词/自反词输入
- 支持变形或别名打开原词
- 支持相近拼写建议
- 没有可靠匹配时显示可理解空状态

3. 中心词卡

- 首屏优先展示学习最需要的信息
- 包含法语词、词性、中文提示、法语释义摘要、常用搭配、例句入口和关系入口
- 保留关系点击体验

4. 我的词卡

- 可从当前中心词加入或打开我的词卡
- 本地存储 key：`wordcloud.draft_cards.v1`
- 只允许编辑中文提示和备注
- 不写入权威词库

5. 本地学习数据边界

- 复习数据 key：`wordcloud.learning.v1`
- 我的词网 key：`wordcloud.personal.v2`
- 我的词卡 key：`wordcloud.draft_cards.v1`
- 本地数据读取处理 JSON 损坏、类型错误和缺失字段
- 提供只读 JSON 导出

6. 复习闭环

- 可从中心词卡或审校关系加入复习
- 按到期顺序展示
- 支持查看关系对比说明
- 支持标记记住或再复习
- 本地持久化

7. 学习进度

- 显示复习完成数、到期数、即将到期数
- 显示词条和关系分类统计
- 显示最近复习状态
- 支持按探索路径查看学习进展

8. 内容质量提升

- 已补充一批核心词的审校学习内容
- 已补充一批核心词关系和用法辨析
- 审校关系要求包含 `source`、`reviewer`、`reviewedAt`
- 不手改 `graph-data.js`，内容更新走数据结构和管线

9. 发布准备

- 已添加发布包脚本：`scripts/package_static_release.mjs`
- 已添加部署说明：`docs/static-deployment.md`
- 已添加手动验收：`docs/manual-acceptance.md`
- GitHub Pages workflow 已添加：`.github/workflows/pages.yml`
- 线上地址已可访问

## 重要文件

运行网站必需：

- `index.html`
- `styles.css`
- `app.js`
- `graph-data.js`
- `sw.js`
- `manifest.webmanifest`
- `icon.svg`
- `src/`

本地学习功能：

- `src/draft-tools.mjs`
- `src/draft-ui.js`
- `src/local-data-tools.mjs`
- `src/review-tools.mjs`
- `src/search-tools.mjs`
- `src/word-card-tools.mjs`

测试：

- `tests/`
- `scripts/browser_acceptance_smoke.mjs`

数据和审校：

- `data/processed/editorial-seed.json`
- `data/processed/wiktextract-p0-approved.json`
- `data/processed/wiktextract-p0-review.json`
- `data/processed/wiktextract-p0-form-of-resolutions.json`
- `data/processed/dbnary-alignment-review-queue.json`
- `data/processed/eligible-lexicon.csv`
- `data/reports/`
- `data/sources.json`
- `data/audit-review-v1.json`

数据管线：

- `scripts/build_data.py`
- `scripts/build_graph.py`
- `scripts/export_runtime.py`
- `scripts/update_runtime_cache.py`
- `scripts/validate_data.py`
- `scripts/build_verified.py`
- `DATA_PIPELINE.md`

发布：

- `.github/workflows/pages.yml`
- `scripts/package_static_release.mjs`
- `docs/static-deployment.md`
- `docs/manual-acceptance.md`

## 不要随便删除

不要删除这些内容，除非明确知道后果：

- `graph-data.js`
- `app.js`
- `index.html`
- `styles.css`
- `sw.js`
- `src/`
- `scripts/`
- `tests/`
- `data/processed/editorial-seed.json`
- `data/processed/wiktextract-p0-approved.json`
- `data/processed/wiktextract-p0-review.json`
- `data/processed/dbnary-alignment-review-queue.json`
- `data/reports/`
- `data/sources.json`
- `data/audit-review-v1.json`
- `data.js`
- `dict.js`
- `.github/workflows/`

可以重新生成或重新下载的本地内容：

- `dist/`
- `node_modules/`
- `scripts/__pycache__/`
- `.DS_Store`
- `data/raw/wiktextract/`
- `data/raw/dbnary/`
- `data/raw/demonette-2.0/`
- `data/raw/FleLex_TT_Beacco.tsv`
- `data/raw/Lexique400.tsv`
- `data/processed/wordcloud.sqlite`
- `data/processed/graph-input.json`
- `data/processed/layout-positions.json`
- `data/processed/dbnary-analysis.json`
- `data/processed/dbnary-approved.json`
- `data/processed/demonette-analysis.json`
- `data/processed/demonette-approved.json`
- `data/processed/wiktextract-gap-audit.jsonl`

## 常用命令

本地预览：

```bash
cd /Users/jinyanshao/Developer/wordcloud
python3 -m http.server 8000
```

打开：

```text
http://localhost:8000/index.html
```

安装依赖：

```bash
pnpm install
```

运行检查：

```bash
pnpm check
pnpm smoke:browser
```

生成发布包：

```bash
pnpm release:package
WORDCLOUD_STATIC_ROOT=dist pnpm smoke:browser
```

重新发布到 GitHub Pages：

```bash
git push origin main
```

只要 `.github/workflows/pages.yml` 存在，推送到 `main` 会触发 GitHub Pages 部署。

## 许可证和发布边界

当前项目可以公开试用，但不适合商业发布。

原因：

- FLELex / Beacco 使用 CC BY-NC-SA 4.0，包含非商业限制
- 代码还没有正式 `LICENSE` 文件
- 数据产物受多个来源许可约束

上线和展示必须保留：

- 来源说明
- 非商业来源提示
- 本地数据和隐私说明

未来如果要商业化，需要先处理：

- 替换或重新授权 FLELex
- 明确代码许可证
- 复核所有数据来源的再分发边界

## 下一步路线

### 第 1 步：整理本地和仓库状态

目标：让本地和 GitHub 长期保持清楚。

要做：

- 决定是否提交当前 `.gitignore` 小改动
- 确认 `git status` 干净
- 保留 `main` 作为稳定分支
- 删除旧临时分支或保留为备份

验收：

```bash
git status --short --branch
```

只允许出现明确知道原因的本地改动。

### 第 2 步：线上手动验收

目标：确认公开试用网站真的可用。

要做：

- 打开 `https://jinyanshao.github.io/wordcloud/`
- 搜索 `faire`
- 打开中心词卡
- 点击关系节点
- 打开我的词卡
- 加入复习
- 打开学习进度
- 打开本地数据并导出 JSON
- 用手机宽度检查顶部按钮和弹窗

验收文档：

- `docs/manual-acceptance.md`

### 第 3 步：补齐公开试用说明

目标：让用户知道这是什么、数据存在哪里、有哪些限制。

要做：

- 在页面上确认来源和非商业提示清楚可见
- 在 README 中保留 live demo 链接
- 增加一段更适合普通用户看的项目说明
- 明确“本地保存，不上传，不同步”

验收：

- 新用户打开页面后能理解这是法语词网
- 用户能知道学习记录只在本机浏览器

### 第 4 步：第一批试用反馈

目标：验证产品方向，而不是继续堆功能。

建议找 3 到 5 个中文法语学习者试用。

观察问题：

- 他们会不会搜索词
- 他们是否理解关系图
- 他们最常点什么关系
- 中心词卡里哪些信息有用
- 哪些文案看不懂
- 是否愿意用复习功能

记录方式：

- 新建 `docs/trial-feedback.md`
- 每条反馈记录日期、用户类型、问题、影响和处理决定

### 第 5 步：核心体验打磨

目标：让第一次打开更容易用。

优先事项：

- 改善空状态和引导
- 优化移动端顶部按钮密度
- 让中心词卡的常用搭配和例句更容易扫读
- 让关系类型更容易理解
- 降低初次看到大词网时的陌生感

不要急着做：

- 账号
- 同步
- 后端
- 新框架
- 复杂推荐系统

### 第 6 步：内容质量第二轮

目标：继续提高核心词的可学性。

要做：

- 继续看 `data/reports/core-word-gap-list.csv`
- 优先补 A1/A2 高频词
- 优先补容易混淆的词对
- 优先补常用搭配和短例句
- 每条新增关系继续保留来源、审核人、审核日期

原则：

- 不把自动候选当作审校事实
- 不手改 `graph-data.js`
- 内容变更走 `data/processed/editorial-seed.json` 和数据管线

### 第 7 步：可靠性和测试增强

目标：减少发布时的紧张感。

要做：

- 继续保留 `pnpm check`
- 继续保留 `pnpm smoke:browser`
- 考虑是否引入真正的浏览器端到端测试
- 如果引入，需要评估安装成本和 CI 时间

当前暂不必须引入新依赖。

### 第 8 步：许可证决策

目标：避免公开使用边界模糊。

要做：

- 决定代码是否开源
- 如果开源，选择合适 LICENSE
- 如果不开放复用，保留所有权利并写清楚
- 继续保留 FLELex 非商业提示

验收：

- 仓库根目录有明确 `LICENSE` 或 README 中有明确说明
- 用户不会误以为可以商业使用

### 第 9 步：决定是否做后端和同步

当前不需要。

只有出现这些情况时再考虑：

- 用户强烈需要跨设备同步
- 用户希望长期保存学习记录
- 需要共享收藏夹或班级功能
- 需要管理人工内容后台

如果未来要做，建议顺序：

1. 先做数据导入导出稳定
2. 再做账号
3. 再做云同步
4. 最后做多人或管理后台

## 后续任务优先级

最高优先级：

- 提交或放弃当前 `.gitignore` 小改动
- 做一次线上手动验收
- 写试用反馈记录

中优先级：

- 打磨首页和中心词卡的第一次使用体验
- 继续补核心词关系和用法辨析
- 明确 LICENSE

低优先级：

- 新框架
- 后端
- 账号同步
- 大型重构
- 新的数据源扩张

## 新对话恢复提示

如果以后需要在新聊天里继续，可以直接发送：

```text
项目在 /Users/jinyanshao/Developer/wordcloud。请先阅读 README.md、docs/project-continuity.md、docs/static-deployment.md、docs/manual-acceptance.md 和 DATA_PIPELINE.md，然后告诉我当前状态和下一步建议。不要先写代码。
```

如果要继续开发，可以发送：

```text
请基于 /Users/jinyanshao/Developer/wordcloud 当前真实仓库，先审计现有功能和 git 状态，再实现下一阶段。不要引入后端、账号、同步、新框架或非必要依赖；不要手改 graph-data.js；完成后运行 pnpm check 和 pnpm smoke:browser。
```
