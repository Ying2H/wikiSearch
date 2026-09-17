# 初期运行说明

## Git 与虚拟环境

仓库使用本地 Git `main` 分支，`.venv/`、`data/`、缓存和构建产物已加入忽略规则。首次接手时：

```powershell
git config user.name "你的姓名"
git config user.email "你的邮箱"
.\scripts\bootstrap.ps1
```

Linux 服务器使用：

```bash
git config user.name "work"
git config user.email "work@local"
chmod +x scripts/bootstrap.sh
./scripts/bootstrap.sh
```

当前发布流程使用服务器上的 GitHub deploy key 自动推送 `gh-pages`；可在服务器上用同一 bootstrap 脚本从干净 checkout 重建环境。`requirements.txt` 当前为空依赖（仅标准库），Node 侧已在 `package.json`/`package-lock.json` 中锁定 Orama 和 esbuild。

抓取 worker 只处理 SQLite 中已入队的页面；成功时把渲染 HTML、FTML 和标准化记录写入缓存，源码或页面请求失败时保留任务并按退避时间重试。当前 worker 尚未作为常驻服务或系统定时任务安装。

首次全量初始化可使用（目标站当前约需 10–15 分钟）：

```powershell
.\.venv\Scripts\python.exe scripts/sync_once.py --db data/target.sqlite3 --cache-dir data/target-cache --scan-pages 2 --worker-limit 177 --snapshot-dir data/target-snapshot --min-interval 2 --progress
```

后续只处理已有队列时加 `--skip-scan`。HTTP 200 但无 Wikidot page ID 的页面会进入 `quarantined`，对应 job 进入 `blocked`，不会无限重试，也不会作为 active 页面进入快照。

## Orama 构建

先完成一次同步并确保 `data/cache/**/record.json` 是一致快照，再执行：

```powershell
npm ci
npm run build:index -- --records data/build-input --output data/publish/orama
```

Orama 构建失败时，暂存输出会被清理，既有输出目录不会被替换。空正文页面会写入快照排除清单而不进入搜索索引；本次目标站初始化最终索引了 174 条记录，排除了 2 条空正文页面。

构建后组合静态入口和索引资源：

```powershell
.\.venv\Scripts\python.exe scripts/assemble_site.py --orama-dir data/publish/orama --manifest data/target-snapshot-v3/manifest.json --output-dir data/target-site
```

本地 HTTP 验收应至少检查 `/`、`/orama/search.js`、`/orama/search-index.json` 和 `/build.json` 均返回 200。正式托管前仍需浏览器验证中文查询、结果跳转、iframe 高度和旧索引回滚。

推荐的单轮流程是先生成 SQLite active 页面的快照，再构建索引：

```powershell
.\.venv\Scripts\python.exe scripts/sync_once.py --scan-pages 1 --worker-limit 10 --snapshot-dir data/build-input
npm run build:index -- --records data/build-input --output data/publish/orama
```

快照会拒绝 observed version 与 fetched version 不一致、缓存文件缺失或内容哈希不匹配的页面；此时不应继续发布新索引。

若只修改了索引提取或过滤逻辑，可使用已有缓存重新导出快照，不需要重新请求目标站：

```powershell
.\.venv\Scripts\python.exe scripts/export_snapshot.py --db data/target.sqlite3 --cache-dir data/target-cache --site-id wymbot.wikidot.com --output-dir data/build-input
```

## 只读探测

在项目根目录执行：

```powershell
python scripts/probe_site.py --base-url http://wymbot.wikidot.com --manifest-path /pagelist --max-pages 2 --min-interval 0
```

加入 `--check-amc` 会额外发送一次 `list/ListPagesModule` 请求，用于确认 AMC 能力。生产环境应恢复至少 2 秒的站点级请求间隔，并遵循站点返回的 `Retry-After`。

## 离线测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s . -t . -v
```

请求层、解析层和状态层分开；解析函数不隐藏网络请求。目标站探测失败时，先使用 `tests/fixtures/` 完成离线开发，不要把 fixture 结果当作现场能力。

## 安全边界

- 一期只访问公开页面，不保存登录凭据，不调用编辑/保存/删除接口。
- 静态索引发布前必须校验 URL 仍属于配置的站点白名单。
- 任何页面返回 HTTP 200 但缺少 `WIKIREQUEST.info.pageId` 时，按软错误处理，不能作为删除证据。
- 抓取失败、超时、解析失败和权限异常都不能批量 tombstone 页面。
