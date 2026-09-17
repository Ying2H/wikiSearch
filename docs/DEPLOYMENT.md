# 服务器抓取与 GitHub Pages 部署

部署拓扑固定为：服务器在 `/root/code/wymboTSearch/` 保存 SQLite、缓存和构建产物，定时从公开 Wikidot 站点抓取；服务器把最终的静态目录推送到 GitHub 仓库的 `gh-pages` 分支；GitHub Pages 从该分支根目录托管搜索页。

## GitHub Pages 设置

在 `Ying2H/wikiSearch` 的 GitHub 设置中选择：

1. Settings → Pages；
2. Source 选择 **Deploy from a branch**；
3. Branch 选择 `gh-pages`，目录选择 `/ (root)`。

发布后地址通常为 `https://ying2h.github.io/wikiSearch/`。搜索页资源使用相对路径，能适配这个项目子路径。

## 服务器首次配置

服务器需要 Python 3.10+、Node.js 20+、npm、`flock` 和 Git。Ubuntu 自带的 Node 18 不满足项目声明的 Node 版本要求，应先安装 Node 20 或更高的受支持 LTS 版本。

进入项目目录后执行：

```bash
cd /root/code/wymboTSearch
git config user.name work
git config user.email work@local
chmod +x scripts/*.sh deploy/install-systemd.sh
./scripts/bootstrap.sh
```

## GitHub 写入授权

自动发布只需要这个仓库的写入权限。建议在服务器生成一把仅用于本仓库的独立 SSH deploy key，把 `.pub` 公钥添加到仓库 Settings → Deploy keys，并勾选 **Allow write access**；不要在聊天中粘贴私钥或个人 Token。然后在服务器执行：

```bash
git remote add origin git@github.com:Ying2H/wikiSearch.git
git push -u origin main
ssh -T -i /root/.ssh/wymbot_github_pages_ed25519 git@github.com
```

如果 `origin` 已存在，使用 `git remote set-url origin git@github.com:Ying2H/wikiSearch.git`。

## 首次构建和自动同步

先手动执行一次，确认抓取、索引和推送全部成功：

```bash
./scripts/run_pipeline.sh --publish
```

该流程依次执行清单扫描、增量抓取、内容一致性快照、Pagefind 构建、静态目录装配和 `gh-pages` 推送。旧静态目录在新构建失败时保留；没有内容变化时不创建新的 Pages 提交。

确认手动发布成功后安装 systemd 定时器：

```bash
./deploy/install-systemd.sh
systemctl list-timers wymbot-search-sync.timer
journalctl -u wymbot-search-sync.service -n 100 --no-pager
```

定时器开机后约 5 分钟首次运行，之后每轮完成后间隔 30 分钟。`data/pipeline.lock` 防止上一轮尚未结束时并发抓取。目标站请求间隔默认 2 秒，可通过 systemd unit 中的环境变量调整。

## 回滚与故障处理

服务器上的 `data/target-cache` 和 SQLite 不应提交到 GitHub。若新索引构建失败，发布脚本不会推送新 `gh-pages` 提交，GitHub Pages 继续使用上一版静态文件。需要回滚时，在 Pages 仓库历史中恢复上一条 `gh-pages` 提交即可。
