# Wikidot + Pagefind 搜索：开发执行说明

状态：设计完成，尚未实现、尚未对目标站实测。核实日期：2026-09-17。

## 1. 目标与决策

为任意可公开访问的 Wikidot 站点提供独立静态搜索页，搜索结果跳回原站。高频检查一个轻量 ListPages 清单，普通页面只在发现变化后抓取；动态页面独立定时刷新。不要把每天遍历全部正文作为正常更新机制。

一期采用用户提出的路线 2：FTML 用于检测动态功能，包含 ListPages 的页面按 TTL 刷新；同时记录简单的静态 include 关系，解决间接包含动态模块的漏检。完整 FTML 解释器、ListPages 查询依赖图属于后续优化，不作为一期前置条件。

核心区分：

- 页面自身修订变化，是重新抓取的充分理由，不是渲染变化的必要条件。
- 清单高频轮询主要减少远程请求；Pagefind 从本地已缓存语料重建。远程增量抓取不等于 Pagefind 磁盘索引可原地增量更新。
- 发布的是匿名访问者可见的正文快照；不执行任意页面脚本，不追求用户、URL 参数、随机结果的所有变体。
- 抓取、持久化、索引构建、发布分开调度；无语料变化时不构建、不发布。

## 2. 已核实依据与待验证事项

已核实文档或上游实现：

1. Wikidot 官方说明支持 ListPages 按 `updated_at`、`revisions` 排序。[S1]
2. wikidot.py 实现使用 ListPages 返回 `fullname`、`updated_at`、`revisions` 等字段；其高级列表函数会自动获取后续分页。低请求模式不能直接调用一个无界的全量列表函数。[S2]
3. 同一实现通过 `viewsource/ViewSourceModule` 和 `page_id` 读取源码，从 `div.page-source` 提取文本；页面 ID 可以从页面响应中取得。[S2]
4. 官方 XML-RPC `pages.get_one` 文档提供 `content` 和渲染 `html`；数据表单页面的 content 可能是 YAML。[S3]
5. Pagefind 支持自定义记录、标签过滤和排序；可生成静态文件。中文需要支持分词的 extended 版本。[S4][S5]

以上是文档/源码依据，不代表目标站当前一定支持。实施 agent 必须先完成 P0 探测，记录实际日期、库版本、脱敏响应和请求数。

尚不能直接假定：

- `revisions` 计数等于页脚 revision 序号或历史 revision ID；分别存储，实测差异，不能硬编码加减一。
- 改标签、改名、上传附件、投票、评论一定更新 `updated_at` 或增加修订次数。
- 清单页自身 revision、HTTP Last-Modified、ETag 能代表模块输出的新鲜度。
- `category="*"` 一定包含所有隐藏页面/模板；需要明确 pagetype、分类范围与索引排除规则。
- HTTP 200 就是有效页面；Wikidot 错误、权限、限流页面可能仍是 200。
- 服务端 ListPages 缓存会在每次 GET 时重新计算。

## 3. 系统结构与实施边界

建议 Python 负责 HTTP、DOM 解析和 SQLite 状态，Node.js 负责 Pagefind 构建与静态界面；可采用 wikidot.py，但所有访问必须经过可计数、限速的适配层。锁定依赖版本并审计惰性属性是否触发额外网络请求。

```text
ListPages 清单 ──> 持久化发现队列 ──> HTML + 按需 FTML ──> 本地语料
动态 TTL 队列 ────────────────────> HTML 刷新 ──────────┘
低频全量元数据清单 ──> 补漏、删除/改名核对 ───────────────┘
本地语料一致性快照 ──> Pagefind 新索引 ──> 验证 ──> 原子发布
```

仅生成本地程序、配置示例和站内安装代码；站点 URL、写入站点和实际托管目标尚未提供。不要猜测目标站、自动创建 Wikidot 页面或部署到未经指定的账号。缺少站点时可完成离线 fixtures 和本地搜索演示，现场接入单独记录为未完成。

一期不包含论坛、附件内容、OCR、评分历史和实时投票统计。搜索记录保留 title、正文、原 URL、分类、标签、站点更新时间；作者先标明“页面创建者”，不要等同作品作者。

## 4. ListPages 轻量清单

优先支持两种 provider，暴露相同的按页读取接口：

- `html_manifest`：访问站长创建的单个辅助页面；正常周期只读第一页，必要时才读后续页。
- `amc_manifest`：只读调用 ListPages 模块，按需分页；不用在站内新增页面，但需先验证 AMC 的会话与参数要求。

辅助页面候选源码如下，必须经过 P0 验证后才标记为可直接安装。此处不预设未经确认的 page ID 变量。

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

实施要求：

- 清单不输出全文、摘要、评分或嵌套模块，降低服务端工作量和响应大小。
- 不设置会永久截断历史记录的总 `limit=100`；`perPage` 控制单批大小，实际分页行为现场确认。
- 解析 DOM 字段，不用按竖线拆行或拼接未经转义的 JSON；标题可包含标点、Unicode 和特殊字符。
- 从时间元素的机器可读值解析 UTC 秒；只看到本地化日期文字时报告能力降级。
- 根据实际 pager/适配器分页，不猜 `/p/2` 或模块实例编号。不能跟随无限查询参数链接。
- 清单页自身、导航、搜索页不进入语料；但可能影响其他正文的模板保留在依赖监控中。
- 若首页返回大量记录，频率与页大小都需可配置；“一个 URL”不代表一次请求能列完所有更新。

## 5. 普通页面增量算法

### 5.1 状态及版本

按 `(site_id, page_id)` 建立最终身份，未获得 ID 前用 fullname 临时键。保存 `observed_version=(updated_at, revisions_count)`、`fetched_version`、`source_version`，三者不混用。任何不相等均需重新评估，包括计数降低。新页面直接排队；fullname 改变需更新 URL 并移除旧记录。

`observed_version` 只表示清单发现，不表示抓取成功；只有 HTML/元数据校验成功才能提交 `fetched_version`。源码失败不会把分类重置为 static，改为 unknown 并安排重试。清单变更和抓取任务入队必须同一事务提交，防止水位推进后丢任务。

### 5.2 轮询和翻页

1. 默认每 120 秒读一次清单第一页，加 ±10% 抖动；这是项目初始配置，不是 Wikidot 官方允许频率。
2. 每行与本地观察版本比较，变更任务合并为该页面最新目标版本。
3. 使用上次成功覆盖水位减重叠窗口（默认 15 分钟）作为扫描边界；不能看到第一条已知页面就停止。
4. 持续翻页，直到整批时间严格早于边界，或确实到达末页。同一时间戳的记录全部处理，不能按秒级水位跳过相同时间戳。
5. 分页不是事务快照：去重，并在多页扫描结束后复读第一页检查前沿变化；必要时补扫。持续编辑或达到本轮页数预算时，标记 coverage incomplete，持久化补扫任务且不推进覆盖水位。
6. 水位采用已完整覆盖的远端时间，并在下轮继续重叠；不得简单赋值本机当前时间。旧水位不变时重复扫描是允许的，预算耗尽不是扫描成功。
7. 停机后按旧水位补扫，不只看最新 100 条；停机很久时转完整元数据核对。

时间有序扫描无法绝对保证任意并发修改下零遗漏；重叠、前沿复查和低频清单核对提供最终一致性。不能在文档或 UI 承诺事务日志级完整性。

### 5.3 抓取与竞争

- 普通变化一般读 HTML 和 FTML；优先从 HTML 获取 page ID，避免额外 ID 请求。
- 仅动态 TTL 到期且自身版本未变时读 HTML，复用已缓存 FTML；读取到新修订迹象时再抓源码。
- 抓取期间若清单目标版本再次改变，保留 dirty 状态继续排队。能读取页面版本时与目标核对；无法核对则保守复核元数据，不把不同时间的 HTML 和 FTML 声称为一致快照。
- 用规范化后的索引记录哈希判断是否需要构建，不能只比较原始 HTML（评分控件、随机 ID、时间文字会造成噪声）。
- 首次全站 HTML/FTML 抓取必不可少，必须断点续传、单站限速。

## 6. FTML 获取与动态分类

FTML 指 Wikidot wiki 源码，HTML 指展开模块后的渲染结果。源码用于分类，HTML 用于索引；不要把模块语法本身作为正文替代。

源码读取优先适配已核实的只读 ViewSource 路径。AMC 请求的 token、cookie、编码和错误处理复用客户端实现，禁止使用打开编辑会话或保存页面的接口获取源码。XML-RPC 作为可选替代，先验证站点 API 权限及可用性。[S2][S3]

保留原始源码用于诊断；另生成扫描版本，正确处理响应 HTML 实体，避免二次解码损坏源码。用保守 tokenizer 检测不区分大小写、换行和空白变化的 module/include 指令。代码块和注释中的示例尽量剔除；不确定时多分类为动态，不能因解析失败漏刷。

| 类别 | 判据 | 刷新策略 |
| --- | --- | --- |
| static | 源码已取得且无动态特征、无未解析依赖 | 自身修订触发，外加滚动抽检 |
| dynamic-listpages | 直接包含 ListPages | 独立 TTL，默认 30 分钟 |
| dynamic-transitive | include/有效模板间接引入动态内容 | TTL，默认 30 分钟，并接受依赖变化触发 |
| dynamic-other | 其他列表、评论、评分、随机、日期或外部数据影响正文 | 可配置 TTL，默认 60 分钟 |
| unknown | 源码失败、未知指令、参数化 include、模板未解析 | 默认 60 分钟，不允许归为 static |

一期最小 include 支持：

1. 记录同站字面量 include 的有向边，边指向被包含页面；跨站目标不自动扩展抓取范围。
2. 当被包含页面变化时，标记依赖它的正文页 dirty；刷新依赖图并传播动态属性。
3. 处理多层、循环、失效目标，使用 visited 集合和深度/节点预算。超出预算的相关页面进入 unknown。
4. 维护反向依赖队列，即使模板自身不进搜索索引，也不能在发现阶段直接丢弃。
5. 类别 live template 可能不写在每页源码里；P0 核实有效模板机制。无法建立模板到分类页面的关系时，对相关分类启用 unknown TTL，不能只扫描显式 include。

纯 CSS 模板若确认只影响外观，可不刷新正文；包含文本或动态模块的模板不能如此处理。不要因整站导航包含 ListPages 就把全站都归为动态：分类的依赖范围应对应实际索引的正文。

## 7. 两种路线比较与动态刷新细节

完整依赖图要解释 ListPages 选择器、排序、limit、模块模板和上下文。依赖不仅是当前列出的页面，还包括未来新建的符合条件页面、标签迁入/迁出、删除、评分导致排序变化，以及随时间变化的选择条件。因此只记录当前输出链接，会漏掉新成员；只按自身 revisions 触发，也会漏掉投票和时间变化。

一期不复刻上述查询语义。对已标记动态的页面，即使版本完全相同仍按 TTL GET 渲染 HTML。后续可按 category/tag 建立粗粒度事件订阅以提前刷新，但不能取消 TTL 兜底。

调度规则：

- `next_dynamic_fetch_at` 与自身更新水位独立，重启后仍保留。
- TTL 到期只发一次任务；和编辑触发合并，使用最早 due time。
- 成功读取有效渲染内容后重排 TTL；失败用退避，记录 stale 年龄，不能当作成功刷新。
- 重要中心页可设 5 分钟，普通动态页 15 分钟；长时间未变化可渐退至 60 分钟，但必须允许配置最大陈旧时间。
- `304` 仅在验证缓存校验器确实覆盖模块输出后使用；否则动态页不依赖它判断未变化。服务端缓存导致结果滞后时记录实测缓存延迟，不高频随机参数强行绕缓存。
- 仅索引规范 URL 的默认渲染结果。分页列表只索引默认首屏；被列出的文章自身仍独立索引。随机和按用户呈现页面可排除或明确标记为快照。
- 排行/目录页可能充满其他文章标题，降低其结果权重或提供“排除目录页”过滤，避免压过原文。

## 8. 低频核对：不是每天全正文遍历

默认每日读取完整轻量元数据清单，分页获取，不读取每页正文。比较全部 fullname、版本与已知身份，弥补时间排序或改名事件遗漏。可选同步全站标签/评分元数据，但应明确这些字段的新鲜度不同于正文。

删除处理：最近更新第一页缺席绝不代表删除。完整清单成功后才将缺席页设为 suspect；二次完整核对仍缺席并取得有效的不存在证据，才 tombstone 并重建索引。遇到单页明确权限撤销，先从待发布语料隔离；全站登录页/权限异常则暂停同步并告警，不做批量删除。超时、5xx、解析失败均不能作为删除证据。软 404 必须识别。

同一 ID 改名：迁移规范 URL、依赖边和任务键，索引中只留新 URL；相同 fullname 被删除重建但 ID 不同视为新页面。ID 缺失时保留不确定状态，不能猜测合并。

额外配置低速滚动正文抽检（例如每 30 天覆盖一次可配置范围），用于发现未知动态机制；这是最终一致性兜底，不是每日更新主路径。禁用时明确 unknown 分类漏检风险。

## 9. 请求预算与新鲜度

估算每日请求量：

```text
Q ≈ 86400 / poll_seconds
    + catchup_manifest_requests
    + changed_pages × (html_requests + source_requests)
    + Σ(dynamic_page: 86400 / ttl_seconds)
    + ceil(total_pages / manifest_page_size)
    + audit_requests + retry_requests + identity_requests
```

示例：5000 页、每日 30 个不同页面需同步、20 个动态页面，轮询 120 秒、TTL 900 秒、清单每页 100 行：基础约 `720 + 60 + 1920 + 50 = 2750` 请求/日，未计补扫、探测、抽检、重试。动态页 200 个时仅 TTL 就约 19200 请求/日，因此必须展示分项统计并支持按页面重要性设置 TTL。多个修订合并后只抓最新状态。

默认单站并发 1、请求起始间隔至少 2 秒，所有清单/源码/HTML/核对共享限速器；遵循实际站点限制和 Retry-After。设置请求超时、指数退避、熔断及日预算。预算耗尽必须报告延迟，不能悄悄把 TTL 当成已完成。

新鲜度预算是轮询/TTL + Wikidot 缓存延迟 + 排队 + 构建 + 发布。健康且无积压时，编辑页面目标 5 分钟左右、普通动态页目标 20 分钟左右；这些是待实测的工程目标，不是保证。监控首次发现到上线时间及动态刷新逾期时间。

## 10. 正文提取与 Pagefind 构建

HTML 仅提取正文容器，去除导航、页脚、脚本、样式、编辑控件及不需要的评分 UI；折叠正文和 tab 内文章文字保留。iframe 内容和点击后 Ajax 加载内容一期不抓取，输出能力限制；需要时仅对明确白名单页面单独实现，不运行任意脚本。

规范化规则版本化，保留段落边界和合理空白，防止中文断句粘连。对模板提取规则变化，从本地 HTML 缓存重新处理，不重新请求全部页面。

构建器从 SQLite 一致性快照导出全部 active 记录，调用 Pagefind `addCustomRecord`，字段契约：[S4]

```json
{
  "url": "https://YOUR-SITE.wikidot.com/category:page",
  "content": "规范化正文",
  "language": "zh",
  "meta": {"title": "文章标题", "category": "category"},
  "filters": {"tags": ["示例标签"], "page_type": ["article"]},
  "sort": {"updated": "1789600000"}
}
```

标题参与检索必须做实际查询验收，必要时使用带标题的索引内容或虚拟 HTML；不要仅凭 metadata 存在推断检索权重。固定 extended 分词能力，测试简体、繁体、中英混合、编号和标点；一期不承诺简繁自动互转。

- 所有记录生成稳定排序的 manifest_hash，包含正文及所有检索/显示字段；hash 不变跳过构建。
- 默认变化后合并等待 60 秒，持续变化时最多等待 180 秒再启动；只允许一个构建任务。
- 构建期间发生新变化，下一轮处理；不能把新变更 generation 标成已发布。
- 创建全新索引输出目录，不在旧输出中覆盖增删；删除记录通过全量本地重建生效。
- Pagefind 每个 API 的 errors 都检查；失败保留上一成功版本。
- 记录 corpus generation、构建 ID、配置版本和更新时间。

## 11. 发布与 Wikidot 接入

使用独立静态搜索页，首选从 Wikidot 顶栏/侧栏链接过去。iframe 作为可选接入，需要现场验证尺寸、浏览器策略与结果链接跳出行为。站内原搜索框替换方法留给主题适配，不假定能注入全站 JavaScript。

索引和前端按不可变构建目录成套发布，验证通过后才切换入口；保留上一版本用于回滚。前端入口短缓存/重新验证，带版本的索引资源长缓存。旧标签页可能继续引用旧块文件，保留旧构建一段时间，避免混合版本和 404。具体原子切换机制由选定托管环境实现。

UI 显示最近索引构建时间和同步异常提示；不要把构建时间说成每页内容的更新时间。渲染标题/摘要时转义并只允许可信高亮标记，校验结果 URL 的站点白名单。

静态索引不是权限系统：一期只发布公开语料。若未来支持私有站，整个搜索页和所有索引资源都必须受同等认证保护；只给 UI 加登录不够。

## 12. 持久化与模块接口

SQLite 最小逻辑实体（可拆表，以下为字段职责，不要求单张宽表）：

- pages：site、page_id、fullname、canonical_url、observed/fetched/source 版本、title/tags/category、status、last_seen_inventory。
- content：HTML/FTML 缓存路径、source_hash、normalized_record_hash、extractor_version、fetched_at。
- classification：dynamic_class、reasons、classifier_version、next_dynamic_fetch_at、last_dynamic_success。
- dependencies：from_page、to_target、kind、resolved、last_checked；未收录模板也可作为节点。
- jobs：page_key、reason 集合、target_version、due_at、attempts、lease_until；唯一键合并去重，租约到期可恢复。
- scans：watermark、overlap、coverage_complete、inventory_id、scan_started/finished、分页失败状态。
- builds：corpus_generation、manifest_hash、build_id、status、published_at。

建议目录：

```text
config.example.yaml
src/crawler/{manifest,source,rendered,rate_limit}.py
src/sync/{scheduler,state,inventory,classifier,dependencies}.py
src/extract/content.py
builder/build.mjs
web/
tests/fixtures/
docs/PAGEFIND_DEVELOPMENT.md
docs/CAPABILITY_REPORT.md
docs/OPERATIONS.md
```

适配器提供 `read_manifest_page(cursor)`、`fetch_rendered(page)`、`fetch_source(page_id)`；返回请求计数、时间、错误类型及原始 fixture 引用。不要在解析函数中隐藏网络访问。配置支持 site URL、清单 provider、scope、TTL overrides、预算、刷新频率、存储目录和发布目标。

## 13. 分阶段任务与验收

### P0：现场能力探测（未给站点时先做离线准备）

- 保存清单第一页/后续页、普通正文、源码、软 404 的脱敏 fixture。
- 在获准的测试站验证新增、正文修改、标签修改、改名、删除、投票、include 更新、live template 更新、ListPages 新增成员及时间条件变化。
- 对照清单更新时间/计数、页脚 revision 和实际渲染结果，记录哪些事件不会修改自身版本。
- 测量清单与动态页缓存刷新延迟，验证中文时间解析、分页上限、ID 和 ViewSource 可访问性。
- 输出 CAPABILITY_REPORT，失败能力对应明确降级，不把官方旧文档当现场成功。

### P1：可恢复的增量同步

- 实现数据库、显式分页、版本比较、任务合并、重叠水位、限速和重试。
- 首次初始化完成后，静态站无变化的正常单周期只请求清单第一页（到期维护任务除外），不访问各正文/源码。
- 清单变化仅抓目标页；抓取失败、进程崩溃后恢复不丢更新。

### P2：动态页面刷新

- 完成 FTML 分类、字面量 include 反向依赖、模板/未知降级和 TTL。
- 验证 ListPages 宿主页自身未修订时，成员新增/更新导致的正文变化能在 TTL 后被捕获。
- 验证间接 include 动态模块、多层 include、循环、参数化 include 和源码读取失败。
- 验证 TTL 不重复拉取未变化源码，依赖变化与 TTL 任务合并。

### P3：搜索与本地发布

- 从缓存构建 Pagefind，生成中文搜索页与站内接入示例。
- 对文章标题、正文中文词组、中英编号、标签过滤和原 URL 跳转做浏览器验收。
- 内容删除后旧词不可搜索；构建失败不影响旧版本；无语料变化不构建。
- 记录 5000 条模拟语料的构建时间/资源使用，确认所选频率可承受；不以模拟值替代真实站指标。

### P4：补漏与运行说明

- 全量元数据核对、删除确认、改名合并、滚动抽检、监控、备份和回滚。
- OPERATIONS 写明运行/恢复命令、配置项、请求预算、动态快照限制、缺少目标站/托管配置时的后续步骤。

必须自动测试的高风险场景：同秒超过一页更新；停机期间更新超过首页容量；分页过程中前部插入更新；中间分页失败不推进水位；队列事务后崩溃；HTML 与源码跨修订；计数回退；相同 slug 不同 ID；假 200 错误页；权限异常不批量删除；include 动态传播；动态内容 hash 不变不构建；构建中再次变化不丢代次；旧客户端仍可读旧索引块。

交付必须区分“离线测试通过”“目标站探测通过”“已经发布”。不得将未提供站点、未进行的实际模块实验标记为完成。

## 14. 资料

- [S1 Wikidot 官方 ListPages 排序说明](https://blog.wikidot.com/design:4)
- [S2 wikidot.py 页面访问实现：列表、ID 与 ViewSource](https://github.com/ukwhatn/wikidot.py/blob/main/src/wikidot/module/page.py)（实施时锁定 commit，main 可变）
- [S3 Wikidot 官方 XML-RPC API](https://www.wikidot.com/doc:api)
- [S4 Pagefind Node.js 索引 API](https://pagefind.app/docs/node-api/)
- [S5 Pagefind 多语言及中文分词](https://pagefind.app/docs/multilingual/)
- [S6 Pagefind 开源仓库](https://github.com/Pagefind/pagefind)

本文中的频率、架构、算法、数据库设计和验收条件为本项目方案，不是上述上游项目提供的性能或一致性保证。
