# 浏览器手动验收

## 运行入口

```bash
cd /Users/jinyanshao/Developer/wordcloud
python3 -m http.server 8123
```

打开 `http://localhost:8123/index.html`。如果 8123 被占用，换一个端口。

## 桌面验收

1. 首页加载后能看到词网 canvas、搜索框、`本地数据`、`我的词卡`、`重置视图`。
2. 搜索 `faire`，结果中出现 `faire`，点击后右侧中心词卡打开。
3. 中心词卡首屏先显示法语词、词性、中文提示、关系绑定的具体法语义项、常用搭配/例句入口、关系入口。
4. 点击中心词卡里的 `我的词卡 · 加入 / 打开`，打开 `我的词卡`，并自动创建或定位当前词。
5. 在 `我的词卡` 中编辑中文提示和备注，保存后刷新页面，重新打开仍存在。
6. 搜索 `suis`，结果显示 `être`，并标明词形匹配。
7. 搜索 `fiare`，没有精确匹配时显示相近拼写建议。
8. 点击左下角 `图的语言`，展开后能看到来源名、非商业来源提醒和本地保存提醒。
9. 点击 `本地数据`，弹窗显示隐私、导出、来源许可说明，以及我的词网、我的词卡两类边界。
10. 点击 `生成导出 JSON`，只读文本框中出现 JSON，包含 `personal`、`draftCards`。

## 损坏数据验收

在浏览器 DevTools Console 中执行：

```js
localStorage.setItem("wordcloud.personal.v2", JSON.stringify({ nodes: {}, edges: [] }));
localStorage.setItem("wordcloud.draft_cards.v1", JSON.stringify({ drafts: {} }));
location.reload();
```

重新打开 `本地数据` 并生成导出 JSON：

- 页面不崩溃。
- 弹窗中显示可理解的本地数据提示。
- 导出 JSON 的 `errors` 数组包含对应说明。

验收后可清理本地测试数据：

```js
localStorage.removeItem("wordcloud.personal.v2");
localStorage.removeItem("wordcloud.draft_cards.v1");
location.reload();
```

## 移动端验收

在浏览器 DevTools 里切换到 390px 左右宽度：

1. 顶部操作区仍可点击，不遮挡搜索框。
2. 搜索结果不超出屏幕。
3. 中心词卡从底部弹出，关闭按钮可点，正文可滚动。
4. `我的词卡`、`本地数据` 两个弹窗宽度适配屏幕，文本不溢出。
5. `我的词卡` 的列表和编辑区上下排列，保存后刷新仍恢复。
6. `本地数据` 弹窗里的隐私、导出、来源许可说明在窄屏下逐行显示，不横向溢出。

## 命令验收

```bash
pnpm check
pnpm smoke:browser
pnpm release:package
WORDCLOUD_STATIC_ROOT=dist pnpm smoke:browser
```

## 部署后验收

把 `http://localhost:8123/index.html` 换成线上 URL，重复桌面验收第 1、2、8、9、10 步和移动端验收第 1、4、6 步。完成后刷新页面一次，确认 Service Worker 没有继续展示旧资源。

## Playwright 决策

当前阶段暂不引入 Playwright。原因：

- 项目还没有浏览器自动化环境。
- 当前目标是固定手动验收路径和静态运行时检查，不需要新增运行时能力。
- 引入 `@playwright/test` 需要新增 devDependency，并通常需要下载浏览器二进制；这会增加安装时间、磁盘占用和首次运行复杂度。
- 现阶段仍要求不引入新依赖，因此先用 `pnpm smoke:browser` 覆盖静态 shell 和验收入口，用本文件覆盖真实浏览器步骤。

适合引入 Playwright 的时机：

- 准备上线前需要防回归。
- 需要在 CI 中自动跑首页、搜索、词卡、刷新恢复和本地数据导出。
- 能接受浏览器下载和测试耗时。
