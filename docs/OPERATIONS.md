# 运行与定时任务说明

本文说明同步服务、Orama 构建和 systemd 定时任务的日常操作。生产目录为 `/root/code/wymboTSearch/`。

## 定时任务组成

项目使用两个 systemd 单元：

- `wymbot-search-sync.timer`：负责按周期激活服务；
- `wymbot-search-sync.service`：以一次性任务执行抓取、构建和 GitHub Pages 发布。

服务不是常驻进程。每次服务完成后退出，下一次由 timer 再次激活。

## 启动、暂停和停止

启动定时任务：

```bash
sudo systemctl start wymbot-search-sync.timer
```

暂停当前定时任务，但保留开机启用状态：

```bash
sudo systemctl stop wymbot-search-sync.timer
sudo systemctl stop wymbot-search-sync.service
```

永久停用并立即停止：

```bash
sudo systemctl disable --now wymbot-search-sync.timer
```

重新设置为开机自动启动：

```bash
sudo systemctl enable --now wymbot-search-sync.timer
```

查看是否运行：

```bash
systemctl is-active wymbot-search-sync.timer
systemctl is-enabled wymbot-search-sync.timer
systemctl status wymbot-search-sync.timer --no-pager
```

## 修改清单扫描频率

默认 timer 文件为：

```text
deploy/systemd/wymbot-search-sync.timer
```

其中：

```ini
OnBootSec=5min
OnUnitActiveSec=10min
```

- `OnBootSec` 控制系统启动后的首次执行延迟；
- `OnUnitActiveSec` 控制服务激活后的下一次执行间隔。

例如改为每 30 分钟检查一次：

```ini
OnBootSec=5min
OnUnitActiveSec=30min
```

修改仓库中的 timer 文件后，在服务器执行：

```bash
cd /root/code/wymboTSearch
GIT_SSH_COMMAND='ssh -i /root/.ssh/wymbot_github_pages_ed25519 -o IdentitiesOnly=yes' \
  git pull --ff-only origin main
sudo ./deploy/install-systemd.sh
```

安装脚本会复制 systemd 文件、执行 `daemon-reload` 并启用 timer。

如果只想临时调整服务器，不修改仓库文件，可以直接编辑：

```bash
sudoedit /etc/systemd/system/wymbot-search-sync.timer
sudo systemctl daemon-reload
sudo systemctl restart wymbot-search-sync.timer
systemctl list-timers wymbot-search-sync.timer --all
```

直接编辑 `/etc/systemd/system/` 的修改可能会在下次运行安装脚本时被仓库版本覆盖；长期修改应同步更新 `deploy/systemd/`。

## 修改动态页面刷新频率

动态页面 TTL 位于：

```text
deploy/systemd/wymbot-search-sync.service
```

默认值：

```ini
Environment=LISTPAGES_TTL=1800
Environment=TRANSITIVE_TTL=1800
Environment=OTHER_DYNAMIC_TTL=3600
Environment=UNKNOWN_TTL=3600
```

单位为秒：

- `LISTPAGES_TTL`：直接包含 `ListPages` 的页面；
- `TRANSITIVE_TTL`：通过 include 间接包含动态内容的页面；
- `OTHER_DYNAMIC_TTL`：其他已识别动态页面；
- `UNKNOWN_TTL`：源码无法可靠分类的页面。

例如将直接 ListPages 页面改为 15 分钟：

```ini
Environment=LISTPAGES_TTL=900
```

更新 service 文件后执行：

```bash
sudo systemctl daemon-reload
sudo systemctl restart wymbot-search-sync.timer
```

TTL 只影响动态页面重新抓取的时间，不改变 timer 激活服务的总频率。

## 手动执行一轮

执行抓取、构建和发布：

```bash
cd /root/code/wymboTSearch
./scripts/run_pipeline.sh --publish
```

只抓取并在本地构建，不推送 GitHub Pages：

```bash
./scripts/run_pipeline.sh --no-publish
```

通过 systemd 手动启动服务前，建议先暂停 timer，避免两个服务同时激活：

```bash
sudo systemctl stop wymbot-search-sync.timer
sudo systemctl start wymbot-search-sync.service
sudo systemctl start wymbot-search-sync.timer
```

同步脚本内部还使用 `data/pipeline.lock` 防止重复运行。

## 日志和故障定位

查看最近日志：

```bash
journalctl -u wymbot-search-sync.service -n 100 --no-pager
```

实时查看日志：

```bash
journalctl -u wymbot-search-sync.service -f
```

查看 timer 最近和下一次执行：

```bash
systemctl list-timers wymbot-search-sync.timer --all
```

构建失败时，暂存目录会被清理，上一份成功的 `data/publish/site` 不会被替换，也不会推送新的 `gh-pages` 提交。

## 数据和索引目录

```text
data/target.sqlite3       SQLite 状态数据库
data/target-cache/        页面 HTML、FTML 和标准化记录缓存
data/build-input/         一致性快照
data/publish/orama/       Orama 索引和浏览器脚本
data/publish/site/        待发布静态站点
data/github-pages/        gh-pages 本地工作树
```

`data/` 已被 Git 忽略，不应手动提交。删除缓存或 SQLite 前应先确认备份和重新抓取成本。

## 本地离线测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s . -t . -v
npm ci
npm run build:index -- --records data/build-input --output data/publish/orama
```

Orama 索引和静态装配细节见 [Orama 构建说明](ORAMA_BUILD.md)。

## 安全边界

- 同步器只读取公开 Wikidot 页面；
- 不保存 Wikidot 登录凭据，不调用编辑、保存、删除或上传接口；
- GitHub Pages 上的索引不能保护私有内容；
- HTTP 200 但缺少有效 Wikidot 页面标识的响应不能直接视为有效页面或删除证据；
- 发布前应校验索引 URL 属于目标站点。
