# 在 Wikidot 页面中嵌入搜索页

线上搜索页地址：

```text
https://ying2h.github.io/wikiSearch/
```

搜索页会通过 `window.postMessage` 把内容高度通知父窗口；父窗口代码校验消息来源后更新 iframe 高度，并限制在 280–20000 像素之间。这样搜索结果增多、收起或展开时，iframe 会跟着改变高度。

搜索结果链接已设置为新标签页/窗口打开，不会在 Wikidot 内嵌 iframe 中导航。

## 推荐方式：使用 `[[html]]` 块

Wikidot 的 HTML 块会在 iframe 中运行 HTML/JavaScript，普通页面正文不能直接执行任意脚本；官方文档也说明可使用 `[[html]] … [[/html]]`，而 `[[iframe]]` 支持 `height`、`width`、`scrolling`、`style` 等属性。[Wikidot HTML Blocks](https://www.wikidot.com/doc-wiki-syntax:html-blocks) · [Wikidot Embedding code](https://www.wikidot.com/doc-wiki-syntax:embedding-code)

在目标 Wikidot 页面的源码中粘贴下面的完整代码：

```wikidot
[[html]]
<div style="width:100%;margin:0;padding:0;">
  <iframe
    id="wymbot-search-frame"
    src="https://ying2h.github.io/wikiSearch/"
    title="Wikidot 搜索"
    loading="lazy"
    referrerpolicy="strict-origin-when-cross-origin"
    frameborder="0"
    scrolling="no"
    style="display:block;width:100%;height:320px;min-height:280px;border:0;overflow:hidden;"
  ></iframe>
</div>
<script>
(() => {
  const frame = document.getElementById("wymbot-search-frame");
  const allowedOrigin = "https://ying2h.github.io";
  const minHeight = 280;
  const maxHeight = 20000;

  window.addEventListener("message", (event) => {
    if (event.source !== frame.contentWindow || event.origin !== allowedOrigin) return;
    if (event.data?.type !== "wymbot-search-height") return;
    const height = Number(event.data.height);
    if (!Number.isFinite(height)) return;
    frame.style.height = `${Math.max(minHeight, Math.min(maxHeight, Math.ceil(height)))}px`;
  });

  frame.addEventListener("load", () => {
    frame.contentWindow.postMessage(
      { type: "wymbot-search-request-height" },
      allowedOrigin
    );
  });
})();
</script>
[[/html]]
```

保存并查看页面。首次加载使用 320px 兜底高度，搜索页加载完成后会自动调整；搜索结果变化时也会重新调整。

## 直接使用 `[[iframe]]` 的固定高度版本

如果站点策略不允许运行 HTML 块中的脚本，可先使用固定高度版本。它不能跨域自适应，只能通过增大 `height` 或允许滚动来避免截断：

```wikidot
[[iframe https://ying2h.github.io/wikiSearch/ frameborder="0" width="100%" height="720" scrolling="yes" style="border:0;display:block;"]]
```

## 检查清单

1. 必须使用带结尾 `/` 的 GitHub Pages 地址。
2. 自适应版本中不要删除 `message` 监听器或 `event.origin` 校验。
3. 如果预览中看不到脚本效果，保存后打开正式页面再检查；Wikidot 对 HTML/脚本块的预览和渲染存在差异。
4. 如果浏览器控制台报告混合内容，确保 Wikidot 页面和 iframe 均使用 HTTPS。
