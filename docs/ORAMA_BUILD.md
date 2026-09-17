# Orama 构建说明

本项目使用 Orama 在浏览器内执行静态全文搜索。服务器只负责抓取 Wikidot、生成一致性快照和构建静态资源；GitHub Pages 只托管 HTML、JavaScript 和 JSON，不提供搜索 API。

## 构建依赖

Node.js 要求 `>=20`，依赖版本锁定在 `package.json` 和 `package-lock.json`：

- `@orama/orama`：内存倒排索引和 BM25 搜索；
- `@orama/tokenizers`：中文 Mandarin tokenizer；
- `esbuild`：将浏览器搜索脚本打包为单文件。

中文 tokenizer 使用 `Intl.Segmenter("zh-CN", { granularity: "word" })`，并额外统一大小写。构建端和浏览器端必须使用相同的 tokenizer 配置；如果浏览器不支持该 API，前端会降级为精确短语搜索。

## 构建

正式构建应使用 `scripts/sync_once.py --snapshot-dir` 生成的快照，而不是直接使用可能包含空正文或不同版本记录的长期缓存：

```powershell
npm ci
npm run build:index -- --records data/build-input --output data/publish/orama
```

构建器会：

1. 按稳定路径读取并校验 `record.json`；
2. 将标题、页面名、分类、页面类型和正文写入 Orama；
3. 序列化为 `search-index.json`；
4. 使用 esbuild 生成浏览器端 `search.js`；
5. 先写入带进程标识的暂存目录，成功后原子替换输出目录。

组合为可托管目录：

```powershell
.\.venv\Scripts\python.exe scripts/assemble_site.py `
  --orama-dir data/publish/orama `
  --manifest data/build-input/manifest.json `
  --output-dir data/publish/site
```

最终目录包含：

```text
site/
├── index.html
├── orama/
│   ├── search-index.json
│   └── search.js
└── build.json
```

## 搜索策略

Orama 负责分词搜索和排序；前端对标题、页面名和正文执行精确连续短语检查，并将精确命中排在前面。这里不使用逐字符倒排索引，以免短查询产生大量噪声。单个汉字查询会提示用户继续输入。

索引中只包含公开页面。索引内容会随静态站一起发布，不能用来保护私有页面。

## 验收

至少验证：

- `正常`、`搜索`、`测试`、`这是一个` 等中文词组；
- 英文、数字、冒号、连字符和中英混合页面名；
- 手机输入法组合输入和粘贴；
- 结果链接在 iframe 外部新窗口打开；
- iframe 高度随结果数量变化；
- 索引加载失败、版本不匹配和旧索引回滚。
