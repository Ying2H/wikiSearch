# Wikidot Orama Search

面向公开 Wikidot 站点的增量抓取、内容同步和静态全文搜索系统。服务器定期读取目标站点的页面清单和页面内容，生成 Orama 搜索索引，并将完整静态站点发布到 GitHub Pages。

## 功能

- 解析 Wikidot HTML 清单和 AMC `ListPages` 响应；
- 读取页面渲染 HTML 和只读 FTML 源码；
- 使用 SQLite 保存页面版本、抓取任务、缓存状态和依赖关系；
- 支持增量抓取、任务租约、失败重试和动态页面 TTL 刷新；
- 从一致性快照生成 Orama JSON 倒排索引；
- 使用中文 Mandarin tokenizer，浏览器端完成搜索、排序和高亮；
- 支持 GitHub Pages 静态托管以及 Wikidot iframe 嵌入；
- 搜索结果链接在 iframe 外部的新窗口中打开。

## 系统结构

```text
Wikidot 清单
    ↓
SQLite 版本状态与任务队列
    ↓
HTML / FTML 缓存
    ↓
一致性快照
    ↓
Orama 索引 + 静态搜索页
    ↓
GitHub Pages
```

抓取服务器不提供在线搜索 API。搜索页、索引和前端脚本均为静态资源；索引中只包含公开页面内容。

## 本地使用

Windows：

```powershell
.\scripts\bootstrap.ps1
.\.venv\Scripts\python.exe -m unittest discover -s . -t . -v
```

Linux：

```bash
./scripts/bootstrap.sh
./.venv/bin/python -m unittest discover -s . -t . -v
```

只读探测目标站点：

```bash
python scripts/probe_site.py \
  --base-url http://wymbot.wikidot.com \
  --manifest-path /pagelist \
  --max-pages 2 \
  --min-interval 2
```

## 构建静态搜索站点

先生成一致性快照，再构建 Orama 索引和浏览器脚本：

```bash
npm ci
npm run build:index \
  -- --records data/build-input \
  --output data/publish/orama
```

组合为可托管目录：

```bash
./.venv/bin/python scripts/assemble_site.py \
  --orama-dir data/publish/orama \
  --manifest data/build-input/manifest.json \
  --output-dir data/publish/site
```

构建细节见 [Orama 构建说明](docs/ORAMA_BUILD.md)。

## 部署

生产部署流程、GitHub Pages 配置和服务器更新方式见 [服务器抓取与 GitHub Pages 部署](docs/DEPLOYMENT.md)。

systemd 定时任务的启动、暂停、频率调整和日志查看见 [运行与定时任务说明](docs/OPERATIONS.md)。

Wikidot iframe 嵌入代码见 [Wikidot iframe 接入](docs/WIKIDOT_IFRAME.md)。

目标站点的接口行为和采集边界见 [目标站能力报告](docs/CAPABILITY_REPORT.md)。系统设计和一致性约束见 [搜索系统设计](docs/SEARCH_DESIGN.md)。

## 目录

```text
builder/                 Orama 索引和浏览器脚本构建器
deploy/                  systemd 服务与定时器安装文件
scripts/                 同步、快照、构建、装配和发布入口
src/search_sync/         抓取、解析、状态管理和发布代码
tests/                   离线测试与 fixture
web/                     静态搜索页源文件
docs/                    部署、运行、搜索和目标站说明
```

## 安全边界

- 只读取公开 Wikidot 页面，不调用编辑、保存、删除或上传接口；
- GitHub Pages 上的静态索引不是权限系统；
- 生产发布前应确认索引中的 URL 属于目标站点；
- HTTP 200 不代表页面内容有效，软 404、登录页、权限页和限流响应需要单独识别；
- 抓取失败、超时或解析错误不能作为删除页面的依据。
