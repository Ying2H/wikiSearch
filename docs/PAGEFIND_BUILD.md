# Pagefind 构建说明

本阶段采用 Pagefind Node API 的 `createIndex()` + `addCustomRecord()` + `writeFiles()` 路线。依赖版本锁定为 1.5.2，Node 要求 `>=20`。

worker 产生的每个页面记录位于：

```text
data/cache/<site>/<page-key>/record.json
```

正式构建前，优先使用 `scripts/sync_once.py --snapshot-dir ...` 生成快照目录；快照目录中的 `records/**/record.json` 只包含 active、版本一致且哈希校验通过的页面。

执行构建：

```powershell
npm ci
npm run build:index -- --records data/cache --output data/publish/pagefind
```

构建器会：

1. 按稳定路径顺序读取 `record.json`；
2. 校验 URL、正文、语言、metadata、filters 和 sort 的类型；
3. 将每条记录加入 Pagefind；
4. 写入带进程标识的暂存目录；
5. 成功后通过同卷目录切换替换输出目录，失败时保留旧输出。

中文记录使用 `language: "zh"`。Pagefind 的 extended 发行版对中文分词提供专门支持；标题权重、标签过滤和删除后旧词消失仍需在真实语料上做浏览器验收。

目标站首次全量结果：active 176 页，174 页有可索引正文，2 页因空正文进入 `manifest.json` 的 `excluded` 列表；软 404 页面不属于 active 快照。

目标站的本地静态装配目录为 `data/target-site`（该目录被 `.gitignore` 忽略），包含 `index.html`、`pagefind/` 和 `build.json`。本轮 HTTP 检查中入口、UI JS/CSS、语言元数据文件和构建元数据均可返回 200；尚未进行真实浏览器交互验收。

参考：[Pagefind Node API](https://pagefind.app/docs/node-api/)、[多语言搜索](https://pagefind.app/docs/multilingual/)。
