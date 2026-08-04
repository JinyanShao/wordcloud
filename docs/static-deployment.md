# 静态部署准备

## 推荐方式

第一阶段推荐使用 GitHub Pages，发布 `dist/` 中的静态文件。项目已经托管在 GitHub，页面没有后端、账号、同步或运行时构建步骤，GitHub Pages 的分支发布和 Actions 发布都适合纯静态站点。

不要直接发布仓库根目录。根目录包含数据管线、审计报告和开发脚本；用户访问站点时只需要运行时静态文件。

备选方案：

| 方案 | 解决的问题 | 集成方式 | 维护状态 | 许可或服务边界 | 风险 |
|---|---|---|---|---|---|
| GitHub Pages | 从 GitHub 仓库发布静态页面 | 发布 `dist/` 到 Pages 分支或 Pages Actions artifact | GitHub 官方维护 | 托管服务，受 GitHub 服务条款约束 | 项目站点路径通常是 `/wordcloud/`，需要保留相对路径；站点公开可访问 |
| Cloudflare Pages | 需要全球边缘缓存和预览部署 | 连接 GitHub 仓库，构建命令用 `pnpm release:package`，输出目录 `dist` | Cloudflare 官方维护 | 托管服务，受 Cloudflare 服务条款约束 | Git 集成会授权第三方读取仓库；直接上传和 Git 集成切换策略要提前定 |
| Netlify | 需要简单拖拽或 Git 部署预览 | 构建命令用 `pnpm release:package`，发布目录 `dist` | Netlify 官方维护 | 托管服务，受 Netlify 服务条款约束 | 免费额度、表单/函数等增值功能不在本项目范围内 |

当前最小选择：GitHub Pages。它不需要新增项目依赖，也不要求改变现有前端架构。

## 发布包边界

发布包由白名单生成，只包含浏览器运行必需文件：

```text
index.html
styles.css
graph-data.js
app.js
sw.js
manifest.webmanifest
icon.svg
src/draft-ui.js
src/draft-tools.mjs
src/search-tools.mjs
src/word-card-tools.mjs
src/local-data-tools.mjs
src/review-tools.mjs
.nojekyll
release-manifest.json
```

不进入发布包：

```text
data/
scripts/
tests/
sql/
README.md
DATA_PIPELINE.md
pnpm-lock.yaml
package.json
```

`graph-data.js` 是权威运行时载荷，但仍是生成物；不要手改。需要更新词库或关系时，走数据管线后再重新打包。

## 发布前检查

```bash
pnpm check
pnpm smoke:browser
pnpm release:package
WORDCLOUD_STATIC_ROOT=dist pnpm smoke:browser
```

本地预览发布包：

```bash
cd dist
python3 -m http.server 8123
```

打开 `http://localhost:8123/index.html`，按 [manual-acceptance.md](manual-acceptance.md) 完成桌面和移动端验收。

## Service Worker

`sw.js` 使用 `wordcloud-learning-` 加内容 hash 作为缓存名，并缓存带相同 hash 的 `graph-data.js` 与 `app.js`。`pnpm check` 会校验 `index.html`、`sw.js` 和当前运行时 hash 是否一致。

如果修改了 `app.js` 或 `graph-data.js`：

```bash
python3 scripts/update_runtime_cache.py
pnpm check
pnpm release:package
```

如果只修改 README、文档或非运行时文件，不需要更新 Service Worker 缓存名。

## 部署后验收

部署完成后，用线上 URL 执行：

1. 打开首页，确认词网可见，浏览器控制台没有未捕获错误。
2. 搜索 `faire`，打开中心词卡。
3. 点击 `图的语言`，确认来源名、非商业来源提示和本地保存提示可见。
4. 点击 `本地数据`，确认隐私、导出、来源许可和三个 localStorage key 说明可见。
5. 点击 `生成导出 JSON`，确认输出包含 `wordcloud.local-learning-export.v1`。
6. 在 390px 左右移动端宽度确认顶部按钮不遮挡搜索框。
7. 刷新页面，确认 Service Worker 没有把旧版本资源缓存住。

## 回滚步骤

1. 在托管平台找到上一个通过验收的部署记录。
2. 将生产流量切回上一个部署；如果平台不支持一键回滚，则重新发布上一版 `dist/`。
3. 用线上 URL 重跑部署后验收的前 4 步。
4. 在发布记录中写明回滚原因、回滚时间、当前线上版本和后续修复负责人。

浏览器可能保留旧 Service Worker。回滚后如用户仍看到异常，可让用户刷新两次，或在浏览器站点设置中清除该站点数据。
