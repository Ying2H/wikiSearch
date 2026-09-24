import { create, load, search as oramaSearch } from "@orama/orama";
import { createSearchTokenizer } from "../builder/search-tokenizer.js";

const INDEX_URL = "./orama/search-index.json";
const SCHEMA_VERSION = 2;
const TOKENIZER_ID = "@orama/tokenizers/mandarin+lowercase-v1";
const SEARCH_PROPERTIES = ["title", "fullname", "category", "page_type", "content"];
const SEARCHABLE_FIELDS = ["title", "fullname", "category", "content"];
const HAN_RE = /[\u3400-\u9fff\uf900-\ufaff]/u;
const MIN_HEIGHT = 240;
const ALLOWED_PARENT_ORIGINS = new Set([
  "https://wymbot.wikidot.com",
]);

const state = {
  database: null,
  payload: null,
  allDocumentsPromise: null,
  requestId: 0,
  timer: null,
  composing: false,
  lastHeight: 0,
  heightScheduled: false,
};

const searchInput = document.getElementById("search-input");
const clearButton = document.getElementById("clear-button");
const status = document.getElementById("search-status");
const resultsRoot = document.getElementById("search-results");

function parentOrigin() {
  try {
    const origin = new URL(document.referrer).origin;
    return ALLOWED_PARENT_ORIGINS.has(origin) ? origin : "*";
  } catch {
    return "*";
  }
}

function sendHeight() {
  if (window.parent === window) return;
  const height = Math.max(
    MIN_HEIGHT,
    document.documentElement.scrollHeight,
    document.body.scrollHeight,
  );
  if (height === state.lastHeight) return;
  state.lastHeight = height;
  window.parent.postMessage({ type: "wymbot-search-height", height }, parentOrigin());
}

function scheduleHeight() {
  if (state.heightScheduled) return;
  state.heightScheduled = true;
  const callback = () => {
    state.heightScheduled = false;
    sendHeight();
  };
  if (typeof window.requestAnimationFrame === "function") window.requestAnimationFrame(callback);
  else window.setTimeout(callback, 0);
}

function setStatus(message) {
  status.textContent = message;
  scheduleHeight();
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function normalizeText(value) {
  return String(value ?? "")
    .normalize("NFKC")
    .replace(/[\u200b-\u200d\ufeff]/gu, "")
    .replace(/\s+/gu, " ")
    .trim()
    .toLowerCase();
}

function createFallbackTokenizer() {
  const normalizeToken = (_property, token) => String(token ?? "").toLowerCase();
  return {
    language: "mandarin",
    stemmerSkipProperties: new Set(),
    tokenizeSkipProperties: new Set(),
    stopWords: [],
    allowDuplicates: false,
    normalizeToken,
    normalizationCache: new Map(),
    tokenize(input) {
      return String(input ?? "")
        .toLowerCase()
        .split(/[\s\p{P}\p{S}]+/gu)
        .filter(Boolean);
    },
  };
}

function containsHan(value) {
  return HAN_RE.test(value);
}

function isSingleHanQuery(value) {
  const compact = String(value).trim();
  return Array.from(compact).length === 1 && HAN_RE.test(compact);
}

function queryTerms(query) {
  const value = String(query ?? "").trim();
  if (!value) return [];
  const terms = [value];
  if (typeof Intl?.Segmenter === "function") {
    const segmenter = new Intl.Segmenter("zh-CN", { granularity: "word" });
    for (const segment of segmenter.segment(value)) {
      if (segment.isWordLike) terms.push(segment.segment);
    }
  } else {
    terms.push(...value.split(/\s+/u));
  }
  return [...new Set(terms.filter(Boolean))].sort((a, b) => b.length - a.length);
}

function highlightText(text, query) {
  const source = String(text ?? "");
  const lower = source.toLowerCase();
  const ranges = [];
  for (const term of queryTerms(query)) {
    const needle = term.toLowerCase();
    if (!needle) continue;
    let start = 0;
    while (start < lower.length) {
      const index = lower.indexOf(needle, start);
      if (index < 0) break;
      ranges.push({ start: index, end: index + term.length });
      start = index + Math.max(term.length, 1);
    }
  }
  ranges.sort((left, right) => left.start - right.start || right.end - left.end);
  const merged = [];
  for (const range of ranges) {
    const previous = merged[merged.length - 1];
    if (!previous || range.start > previous.end) merged.push({ ...range });
    else previous.end = Math.max(previous.end, range.end);
  }
  let output = "";
  let cursor = 0;
  for (const range of merged) {
    output += escapeHtml(source.slice(cursor, range.start));
    output += `<mark>${escapeHtml(source.slice(range.start, range.end))}</mark>`;
    cursor = range.end;
  }
  return output + escapeHtml(source.slice(cursor));
}

function isExactPhrase(document, normalizedQuery, fields = SEARCHABLE_FIELDS) {
  if (!normalizedQuery) return false;
  return fields.some((field) => normalizeText(document[field]).includes(normalizedQuery));
}

function getSnippet(document, query, fields = SEARCHABLE_FIELDS) {
  const source = fields.map((field) => document[field] ?? "").join(" ")
    .replace(/\s+/gu, " ")
    .trim();
  if (!source) return "";
  const lower = source.toLowerCase();
  const terms = queryTerms(query);
  let matchAt = -1;
  for (const term of terms) {
    const index = lower.indexOf(term.toLowerCase());
    if (index >= 0 && (matchAt < 0 || index < matchAt)) matchAt = index;
  }
  const center = matchAt < 0 ? 0 : matchAt;
  const start = Math.max(0, center - 90);
  const end = Math.min(source.length, Math.max(start + 220, center + 130));
  const prefix = start > 0 ? "…" : "";
  const suffix = end < source.length ? "…" : "";
  return `${prefix}${highlightText(source.slice(start, end), query)}${suffix}`;
}

function safeUrl(rawUrl) {
  try {
    const url = new URL(rawUrl, window.location.href);
    if (url.protocol !== "http:" && url.protocol !== "https:") return "#";
    return url.href;
  } catch {
    return "#";
  }
}

async function loadDatabase() {
  const response = await fetch(INDEX_URL, { cache: "no-cache" });
  if (!response.ok) throw new Error(`搜索索引加载失败（HTTP ${response.status}）`);
  const payload = await response.json();
  if (
    payload?.format !== "wymbot-orama" ||
    payload?.schema_version !== SCHEMA_VERSION ||
    payload?.tokenizer !== TOKENIZER_ID ||
    !payload.database
  ) {
    throw new Error("搜索索引版本不匹配");
  }
  let tokenizer;
  if (typeof Intl?.Segmenter === "function") {
    const { createTokenizer } = await import("@orama/tokenizers/mandarin");
    tokenizer = createSearchTokenizer(createTokenizer);
  } else {
    tokenizer = createFallbackTokenizer();
    state.tokenizerFallback = true;
  }
  const database = create({
    schema: {
      id: "string",
      title: "string",
      fullname: "string",
      category: "string",
      page_type: "string",
      content: "string",
      url: "string",
    },
    components: {
      tokenizer,
    },
  });
  load(database, payload.database);
  state.payload = payload;
  state.database = database;
  return database;
}

async function allDocuments() {
  if (!state.allDocumentsPromise) {
    state.allDocumentsPromise = Promise.resolve(oramaSearch(state.database, {
      term: "",
      limit: Math.max(10000, Number(state.payload?.records ?? 0)),
    })).then((result) => result.hits.map((hit) => hit.document));
  }
  return state.allDocumentsPromise;
}

function mergeHits(primaryHits, fallbackDocuments) {
  const hitsByUrl = new Map(primaryHits.map((hit) => [hit.document.url, hit]));
  for (const document of fallbackDocuments) {
    if (!hitsByUrl.has(document.url)) {
      hitsByUrl.set(document.url, { id: `contains:${document.url}`, score: 0, document });
    }
  }
  return [...hitsByUrl.values()];
}

async function runSearch(rawQuery) {
  const query = String(rawQuery ?? "").trim();
  const requestId = ++state.requestId;
  clearButton.disabled = !query;
  resultsRoot.replaceChildren();
  if (!query) {
    setStatus("输入关键词开始搜索");
    return;
  }
  const singleHanQuery = isSingleHanQuery(query);
  const searchableFields = singleHanQuery ? ["title", "fullname"] : SEARCHABLE_FIELDS;
  const searchProperties = singleHanQuery ? ["title", "fullname"] : SEARCH_PROPERTIES;

  setStatus(singleHanQuery ? "正在标题和页面名中搜索…" : "搜索中…");
  try {
    const database = await state.databasePromise;
    if (requestId !== state.requestId) return;
    if (!database) return;
    const normalizedQuery = normalizeText(query);
    const result = await oramaSearch(database, {
      term: query,
      properties: searchProperties,
      threshold: 0,
      tolerance: 0,
      limit: 50,
      boost: { title: 4, fullname: 3, category: 1.5 },
    });
    let hits = result.hits;
    if (containsHan(query) && !hits.some((hit) => isExactPhrase(hit.document, normalizedQuery, searchableFields))) {
      const documents = await allDocuments();
      const exactDocuments = documents.filter((document) => isExactPhrase(document, normalizedQuery, searchableFields));
      hits = mergeHits(hits, exactDocuments);
    }
    hits.sort((left, right) => {
      const exactDelta = Number(isExactPhrase(right.document, normalizedQuery, searchableFields)) - Number(isExactPhrase(left.document, normalizedQuery, searchableFields));
      return exactDelta || right.score - left.score;
    });
    if (requestId !== state.requestId) return;
    renderResults(hits.slice(0, 20), query, searchableFields);
    setStatus(hits.length ? `找到 ${hits.length} 个结果` : "没有找到结果");
  } catch (error) {
    if (requestId !== state.requestId) return;
    setStatus(error instanceof Error ? error.message : "搜索失败");
  }
}

function renderResults(hits, query, searchableFields = SEARCHABLE_FIELDS) {
  resultsRoot.replaceChildren();
  for (const hit of hits) {
    const document = hit.document;
    const item = documentElement("li", "search-result");
    const link = documentElement("a", "result-link");
    const title = document.title || document.fullname || document.url;
    link.href = safeUrl(document.url);
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.innerHTML = highlightText(title, query);
    item.append(link);

    if (document.fullname && document.fullname !== title) {
      const name = documentElement("span", "result-name");
      name.textContent = document.fullname;
      item.append(name);
    }

    const snippet = getSnippet(document, query, searchableFields);
    if (snippet) {
      const paragraph = documentElement("p", "result-snippet");
      paragraph.innerHTML = snippet;
      item.append(paragraph);
    }
    resultsRoot.append(item);
  }
  scheduleHeight();
}

function documentElement(tagName, className) {
  const element = document.createElement(tagName);
  element.className = className;
  return element;
}

function scheduleInputSearch() {
  window.clearTimeout(state.timer);
  state.timer = window.setTimeout(() => runSearch(searchInput.value), 220);
}

searchInput.addEventListener("compositionstart", () => {
  state.composing = true;
});
searchInput.addEventListener("compositionend", () => {
  state.composing = false;
  scheduleInputSearch();
});
searchInput.addEventListener("input", () => {
  if (!state.composing) scheduleInputSearch();
});
searchInput.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    searchInput.value = "";
    scheduleInputSearch();
  }
});
clearButton.addEventListener("click", () => {
  searchInput.value = "";
  searchInput.focus();
  runSearch("");
});

if (typeof ResizeObserver === "function") {
  new ResizeObserver(scheduleHeight).observe(document.documentElement);
}
new MutationObserver(scheduleHeight).observe(document.body, { childList: true, subtree: true });
window.addEventListener("load", scheduleHeight);
window.addEventListener("message", (event) => {
  if (event.source === window.parent && event.data?.type === "wymbot-search-request-height") scheduleHeight();
});

state.databasePromise = loadDatabase()
  .then(() => {
    setStatus(state.tokenizerFallback ? "当前浏览器使用精确短语搜索" : "输入关键词开始搜索");
    scheduleHeight();
    return state.database;
  })
  .catch((error) => {
    setStatus(error instanceof Error ? error.message : "搜索索引加载失败");
    return null;
  });
