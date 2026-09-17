from __future__ import annotations

import re

from search_sync.models import Classification


_INCLUDE_RE = re.compile(r"\[\[\s*include\s+([^\]|]+?)(?:\s*\|([^\]]+))?\]\]", re.IGNORECASE)
_MODULE_RE = re.compile(r"\[\[\s*module\s+([^\]]+?)\]\]", re.IGNORECASE | re.DOTALL)
_LISTPAGES_RE = re.compile(r"\blistpages?\b", re.IGNORECASE)
_OTHER_DYNAMIC_RE = re.compile(
    r"\b(?:comments?|forum|pagerate|random|recent(?:changes|posts)?|vote|votes|date|time)\b",
    re.IGNORECASE,
)
_KNOWN_STATIC_MODULES = {"css", "html", "js", "javascript"}
_UNRESOLVED_TOKEN_RE = re.compile(r"\[\[\s*content\s*\]\]", re.IGNORECASE)
_YAML_FIELD_RE = re.compile(r"(?m)^[A-Za-z][A-Za-z0-9_-]*\s*:\s")


def classify_source(source: str) -> Classification:
    """一期保守分类器：宁可增加 TTL 请求，也不把未知内容误判为 static。"""

    reasons: list[str] = []
    includes: list[str] = []
    parameterized: list[str] = []
    for match in _INCLUDE_RE.finditer(source):
        target = re.sub(r"\s+", " ", match.group(1)).strip()
        if not target:
            continue
        includes.append(target)
        if match.group(2):
            parameterized.append(target)
            reasons.append(f"parameterized-include:{target}")

    listpages = bool(_LISTPAGES_RE.search(source))
    other_dynamic = bool(_OTHER_DYNAMIC_RE.search(source))
    unresolved_token = bool(_UNRESOLVED_TOKEN_RE.search(source))
    if unresolved_token:
        reasons.append("unresolved-content-token")
    yaml_like = len(_YAML_FIELD_RE.findall(source)) >= 2 and "[[" not in source
    if yaml_like:
        reasons.append("yaml-like-data-form-source")
    unknown_module = False
    for match in _MODULE_RE.finditer(source):
        name = match.group(1).strip().split(None, 1)[0].lower() if match.group(1).strip() else ""
        if name and name not in _KNOWN_STATIC_MODULES and name != "listpages":
            unknown_module = True
            reasons.append(f"unknown-module:{name}")

    if listpages:
        reasons.insert(0, "direct-listpages")
        dynamic_class = "dynamic-listpages"
    elif other_dynamic:
        reasons.insert(0, "dynamic-module-or-time-token")
        dynamic_class = "dynamic-other"
    elif includes or parameterized:
        reasons.insert(0, "static-include-needs-dependency-check")
        dynamic_class = "dynamic-transitive"
    elif unknown_module or unresolved_token or yaml_like:
        dynamic_class = "unknown"
    else:
        dynamic_class = "static"

    if parameterized and dynamic_class != "unknown":
        dynamic_class = "unknown"
    return Classification(dynamic_class, tuple(dict.fromkeys(reasons)), tuple(includes), tuple(parameterized))
