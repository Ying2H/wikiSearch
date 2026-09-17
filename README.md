# Wikidot Pagefind Sync

这是面向公开 Wikidot 站点的增量同步与静态搜索基础设施。当前交付的是 P0 探测结果和 P1 的第一轮基础实现：

- 解析 `html_manifest` 与 Wikidot AMC 的 ListPages 响应，不依赖固定行格式；
- 读取页面渲染 HTML，提取 `WIKIREQUEST.info.pageId`；
- 通过只读 `ViewSourceModule` 获取 FTML 源码；
- 使用 SQLite 保存观察版本、抓取版本和去重任务；
- 通过租约 worker 抓取渲染 HTML/FTML，并原子写入本地缓存；
- 记录 include 依赖，传播依赖变更，并为动态页面安排 TTL 任务；
- 对 ListPages、include 与未知模块做保守的动态分类；
- 为正文提取和稳定记录哈希提供可离线测试的基础函数。
- 使用 Pagefind 1.5.2 从缓存记录生成中文静态搜索索引。

当前没有自动向 Wikidot 创建页面、修改站点或发布静态文件。目标站能力探测见 [docs/CAPABILITY_REPORT.md](docs/CAPABILITY_REPORT.md)，运行边界见 [docs/OPERATIONS.md](docs/OPERATIONS.md)。

## 本地环境与运行

```powershell
.\scripts\bootstrap.ps1
.\.venv\Scripts\python.exe -m unittest discover -s . -t . -v
.\.venv\Scripts\python.exe scripts/probe_site.py --base-url http://wymbot.wikidot.com --manifest-path /pagelist --max-pages 2 --min-interval 0
```

`probe_site.py` 是只读探测；生产同步器尚未接入后台调度和目标站全量正文抓取。

Pagefind 构建：

```powershell
npm ci
npm run build:index -- --records data/cache --output data/publish/pagefind
```

构建器读取 worker 生成的 `record.json`，逐条校验后调用 Pagefind `addCustomRecord`，先写入暂存目录，再切换到输出目录。示例搜索页在 [`web/index.html`](D:/Project/test/search/web/index.html)。

服务器上的单轮同步入口：

```powershell
.\.venv\Scripts\python.exe scripts/sync_once.py --scan-pages 1 --worker-limit 10 --snapshot-dir data/build-input
npm run build:index -- --records data/build-input --output data/publish/pagefind
```

已有缓存需要重新导出快照时，可跳过网络扫描：

```powershell
.\.venv\Scripts\python.exe scripts/export_snapshot.py --db data/target.sqlite3 --cache-dir data/target-cache --site-id wymbot.wikidot.com --output-dir data/target-snapshot
```

项目已经初始化本地 Git 的 `main` 分支，并配置了 Windows 下的换行和长路径支持；Git 用户名、邮箱和远端地址留给实际维护者设置。运行时 Python 依赖目前全部来自标准库，依赖清单保留在 `requirements.txt`、`requirements-dev.txt` 和 `pyproject.toml`，便于后续加入 Pagefind 构建链。
