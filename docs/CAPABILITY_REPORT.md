# 目标站能力探测报告

探测日期：2026-09-17（Asia/Shanghai）
目标：`http://wymbot.wikidot.com/pagelist`
性质：只读探测；没有登录、编辑、上传、删除或发布操作。

## 已通过的现场能力

| 能力 | 结果 | 证据/边界 |
| --- | --- | --- |
| HTML 清单访问 | 通过 | `/pagelist` 返回 HTTP 200，页面标题为 `Pagelist - RanDomWiki`；页面内 `pageId=1469092585`。 |
| 清单字段 | 通过 | 每行使用 `.search-manifest-row`，含 `.search-fullname`、`.search-title`、`.search-updated`、`.search-revisions`；时间元素含 `time_<unix>` 机器值。 |
| 显式分页 | 通过 | 第 1 页为 100 条，第 2 页为 77 条，共 177 条；链接实际为 `/pagelist/p/2`，不是猜测出来的分页地址。 |
| 空标题容错 | 通过 | 第 2 页的 `nav:top`、`start` 的标题字段为空，记录仍需保留。 |
| 页面内部 ID | 通过 | 例如 `egg:xzdc-9` 的渲染页面返回 `pageId=1469302104`。 |
| ViewSourceModule | 通过 | 对 `page_id=1469302104` 的只读 AMC 请求返回 `status=ok` 和 `.page-source`；源码可能是 YAML/data-form，而不是普通文章 FTML。 |
| `pagelist` 源码 | 通过 | `page_id=1469092585` 的源码与清单模板一致，使用 `ListPages category="*" order="updated_at desc" perPage="100" separate="no"`。 |
| AMC ListPages | 初步通过 | `/ajax-module-connector.php` 的 token + `list/ListPagesModule` 请求返回 `status=ok`；`perPage=5` 返回 `page 1 of 36`。模块体中的原始 HTML 会被 HTML 转义，适配器必须只解码一次后再解析。 |

本轮用临时 SQLite 跑完整两页扫描：`pages_read=2`、`entries_seen=177`、`coverage_complete=true`、`watermark=1785547798`，清单请求数为 2；扫描预算限制为 1 页时，结果保持 `coverage_complete=false` 且不产生水位。

## 现场观察到的限制

- HTML 响应头同时出现 `Cache-Control: no-store`、`Pragma: no-cache`、`ETag` 和 `X-Wikidot-Static-Cache: MISS`。一期不把 ETag/Last-Modified 当作模块输出的新鲜度证明。
- 当前目标 URL 使用 HTTP；本环境对 HTTPS 的 TLS 探测失败，这不能单独证明站点不支持 HTTPS。发布时应由托管环境重新验证并优先使用 HTTPS。
- `egg:xzdc-9` 的渲染页面主体含 `[[content]]` 生成结果，源码包含 YAML 字段；数据表单、模板和 CSS 页面不能简单按“普通文章”处理。
- 当前分类器会将这类 YAML-like 数据表单源码保守标记为 `unknown`，默认进入 TTL 刷新，而不会错误地当作 static。
- 页脚版本号与清单 `revisions` 没有在本轮全部页面上建立等价关系，代码不做加减一推断。

## 尚未验证，必须保留为未完成

- 新增页面、正文修改、标签修改、改名、删除、投票、评论和附件分别是否更新 `updated_at` / `revisions`；
- ListPages 清单输出成员变化、时间条件变化以及分页扫描期间并发编辑的延迟；
- include 的多层/循环/参数化依赖，以及 live template 对渲染结果的影响；
- 软 404、权限撤销、登录页替代和限流页面的识别；
- 完整 AMC 分页扫描、请求预算、缓存刷新延迟和日常调度；
- 正文容器对所有页面类型的提取质量；
- Pagefind extended 中文分词、标题权重、标签过滤、删除后旧词消失和发布回滚。

## 当前代码状态

已实现并有离线测试：HTML/AMC 清单解析、源码解析、页面 ID 提取适配器、只读请求计数/限速、正文提取、动态初筛、SQLite 观察版本与去重队列、带租约/重试的抓取 worker、原子缓存、include 依赖传播和动态 TTL 入队。目标站单页面 worker 已实测成功（渲染 1 请求 + 源码 1 请求）。
Pagefind 构建器和静态搜索页骨架已实现，并已用两条中文 fixture 构建验证；尚未实现：后台 scheduler、完整重叠水位/全量核对、从 SQLite 一致快照导出全量记录，以及目标站全量语料的浏览器验收和正式发布。
