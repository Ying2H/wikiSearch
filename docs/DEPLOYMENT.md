# 服务器抓取与 GitHub Pages 部署

本项目采用“服务器抓取和构建，GitHub Pages 托管静态站点”的部署方式：

```text
公开 Wikidot 站点
        ↓ 定时读取清单和页面
生产服务器 /root/code/wymboTSearch/
        ↓ 生成 Orama 静态索引
GitHub 仓库 gh-pages 分支
        ↓
GitHub Pages
```

搜索页地址：`https://ying2h.github.io/wikiSearch/`

## GitHub Pages 设置

在 `Ying2H/wikiSearch` 的 GitHub 设置中选择：

1. Settings → Pages；
2. Source 选择 **Deploy from a branch**；
3. Branch 选择 `gh-pages`；
4. 目录选择 `/ (root)`。

搜索页使用相对资源路径，因此可部署在仓库项目页路径 `/wikiSearch/` 下。

## 服务器要求

- Python 3.10 或更高版本；
- Node.js 20 或更高版本；
- npm、Git 和 `flock`；
- 能够访问目标 Wikidot 站点和 GitHub；
- 服务器上的项目目录为 `/root/code/wymboTSearch/`。

## 首次安装

将仓库放置到服务器目录后执行：

```bash
cd /root/code/wymboTSearch
chmod +x scripts/*.sh deploy/install-systemd.sh
./scripts/bootstrap.sh
```

`bootstrap.sh` 会创建 Python 虚拟环境并根据锁定清单安装 Python 和 Node 依赖。

## GitHub 写入授权

服务器需要能够读取仓库并向 `gh-pages` 分支推送。推荐使用只针对该仓库的 SSH deploy key：

1. 在服务器生成独立 SSH 密钥；
2. 将公钥添加到仓库 Settings → Deploy keys；
3. 开启 **Allow write access**；
4. 将仓库远端设置为：

   ```bash
   git remote set-url origin git@github.com:Ying2H/wikiSearch.git
   ```

发布脚本默认使用 `/root/.ssh/wymbot_github_pages_ed25519`。如果密钥路径不同，在运行发布命令前设置：

```bash
export GIT_SSH_COMMAND='ssh -i /path/to/deploy_key -o IdentitiesOnly=yes'
```

不要将私钥、访问令牌或其他认证信息提交到仓库。

## 手动部署

更新服务器代码并执行一次完整抓取、构建和发布：

```bash
cd /root/code/wymboTSearch
GIT_SSH_COMMAND='ssh -i /root/.ssh/wymbot_github_pages_ed25519 -o IdentitiesOnly=yes' \
  git pull --ff-only origin main
npm ci
./scripts/run_pipeline.sh --publish
```

流程包括：

1. 扫描 Wikidot 页面清单；
2. 抓取需要更新的 HTML 和 FTML；
3. 排空依赖任务并生成一致性快照；
4. 构建 Orama JSON 索引和浏览器脚本；
5. 装配静态站点；
6. 将站点推送到 `gh-pages`。

没有语料或构建输入变化时，流程会跳过索引构建和 GitHub Pages 推送。

只构建已有快照而不发布：

```bash
npm run build:index -- --records data/build-input --output data/publish/orama
./.venv/bin/python scripts/assemble_site.py \
  --orama-dir data/publish/orama \
  --manifest data/build-input/manifest.json \
  --output-dir data/publish/site
```

## 安装和启动自动同步

安装 systemd 单元并立即启用定时器：

```bash
cd /root/code/wymboTSearch
sudo ./deploy/install-systemd.sh
```

查看定时器和服务：

```bash
systemctl list-timers wymbot-search-sync.timer --all
systemctl status wymbot-search-sync.timer --no-pager
systemctl status wymbot-search-sync.service --no-pager
journalctl -u wymbot-search-sync.service -n 100 --no-pager
```

默认配置是：

- 系统启动约 5 分钟后执行首轮；
- 每次服务激活后约 10 分钟再次执行；
- `/pagelist` 通常每 10 分钟确认一次；
- 直接包含 `ListPages` 的页面 TTL 为 1800 秒，即约 30 分钟；
- 间接动态页面 TTL 为 1800 秒；
- 其他动态页面和无法确定类型的页面 TTL 为 3600 秒，即约 60 分钟；
- 站点请求之间默认间隔 2 秒。

## 回滚

如果新索引构建或发布失败，发布脚本不会替换上一份成功的静态站点。GitHub Pages 仍然提供上一版本。

检查服务器上的发布历史：

```bash
git -C /root/code/wymboTSearch/data/github-pages log --oneline --decorate -10
```

必要时可在 GitHub 仓库的 `gh-pages` 分支恢复上一份发布提交。回滚代码后重新执行一次 `./scripts/run_pipeline.sh --publish`，以保证代码、索引和入口文件版本一致。

## 维护注意事项

- `data/` 包含 SQLite、缓存和构建产物，不应推送到 GitHub；
- 定时器与服务使用 `data/pipeline.lock` 避免同步任务重叠；
- 生产同步使用只读 Wikidot 请求，不修改目标站点；
- GitHub Pages 静态索引仅适用于公开内容；
- 更新 systemd 文件后必须执行 `systemctl daemon-reload`，再重启定时器。
