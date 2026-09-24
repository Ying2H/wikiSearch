# 目标站能力与采集边界

目标站点：`https://wymbot.wikidot.com`

清单页面：`https://wymbot.wikidot.com/pagelist`
观测时间：2026-09-17（Asia/Shanghai）

本文记录目标站点可供同步系统使用的公开读取能力、响应特征和采集边界。所有接口均以只读方式访问。

## 页面清单

| 项目 | 观测结果 | 采集约束 |
| --- | --- | --- |
| 清单页面 | `/pagelist` 返回 HTTP 200，页面标题为 `Pagelist - RanDomWiki` | 页面内容应按 DOM 结构解析 |
| 页面字段 | 每行包含 `.search-fullname`、`.search-title`、`.search-updated` 和 `.search-revisions` | 标题允许为空，不能因空标题丢弃页面 |
| 时间字段 | 时间元素包含 `time_<unix>` 形式的机器可读值 | 以远端 Unix 时间作为版本水位 |
| 分页 | 第 1 页 100 条，第 2 页 77 条，共 177 条 | 使用页面实际提供的分页链接 |
| 页面标识 | 渲染页面中可读取 `WIKIREQUEST.info.pageId` | 不能以 URL 或页面名代替内部 ID |

观测到的第二页包含 `nav:top` 和 `start` 等空标题页面。清单读取必须保留其 `fullname` 和版本信息。

## 页面内容和源码

### 渲染 HTML

普通页面可以通过公开 URL 读取渲染后的 HTML。正文提取应排除导航、页脚、脚本、样式、编辑控件和评分控件，保留折叠内容、标签页内容以及正文中的文本模块。

### FTML 源码

公开页面的内部 ID 可用于只读 `ViewSourceModule` 请求。请求返回 `status=ok` 和 `.page-source` 内容；源码可能是普通 FTML，也可能是 YAML 或 Data Form，不能统一按文章正文解析。

### AMC ListPages

目标站的 `/ajax-module-connector.php` 支持带 token 的 `list/ListPagesModule` 请求。使用 `perPage=5` 的观测请求返回 `page 1 of 36`。

AMC 返回的模块 HTML 可能经过 HTML 实体转义。解析前只能解码一次，然后交给 DOM 解析器，不能按分隔符拆行或拼接未经转义的 JSON。

`/pagelist` 使用的模块模板为：

```text
[[module ListPages category="*" order="updated_at desc" perPage="100" separate="no"]]
[[div class="search-manifest-row"]]
[[span class="search-fullname"]]%%fullname%%[[/span]]
[[span class="search-title"]]%%title%%[[/span]]
[[span class="search-updated"]]%%updated_at%%[[/span]]
[[span class="search-revisions"]]%%revisions%%[[/span]]
[[/div]]
[[/module]]
```

## 响应和缓存特征

观测到的 HTML 响应同时包含 `Cache-Control: no-store`、`Pragma: no-cache`、`ETag` 和 `X-Wikidot-Static-Cache: MISS`。同步系统不把 ETag 或 `Last-Modified` 单独视为 ListPages 模块输出的新鲜度证明。

目标站清单使用 HTTP 地址。生产访问优先使用 HTTPS；如果 HTTPS 访问失败，应将其记录为连接能力问题，不应将响应失败解释为页面删除。

HTTP 200 仍可能对应软 404、权限页面、登录页面或限流页面。只有取得有效 Wikidot 页面标识并通过正文校验后，响应才可进入内容缓存。

## 动态内容边界

以下内容可能在页面自身修订号不变时改变渲染结果：

- `ListPages` 的成员、排序或时间条件变化；
- `include` 或 live template 引入的页面变化；
- 评论、论坛、评分、随机数、日期和外部数据模块；
- 参数化 include、未识别模块或源码读取失败。

同步器对直接 ListPages 页面、间接动态页面、其他动态页面和无法分类的页面分别使用 TTL 刷新。源码读取失败或分类不确定时采用保守刷新策略，不将其归类为静态页面。

## 版本和删除判断

清单中的 `updated_at`、`revisions`、页面脚本底部版本号和真实内容变化不保证一一对应。系统分别保存观察版本、抓取版本和源码版本，不能通过对版本号加减一推断页面状态。

最近更新清单中暂时缺少某个页面不代表页面已删除。只有完整清单核对、有效不存在证据和二次确认同时成立时，页面才可以从待发布语料中移除。

## 内容范围

静态搜索索引只发布公开页面的标准渲染正文、标题、页面名和必要的分类字段，不执行页面脚本，不生成用户、URL 参数、随机结果或权限上下文的所有变体。

以下内容不属于默认索引范围：

- 登录后才能读取的内容；
- 附件文件和 OCR 文本；
- 页面脚本运行后才出现的 Ajax 内容；
- 投票、评论和实时统计数据；
- 无法验证来源或 URL 的外部内容。

## 参考

- [Wikidot ListPages 排序说明](https://blog.wikidot.com/design:4)
- [wikidot.py 页面访问实现](https://github.com/ukwhatn/wikidot.py/blob/main/src/wikidot/module/page.py)
- [Wikidot XML-RPC API](https://www.wikidot.com/doc:api)
