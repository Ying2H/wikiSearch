from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class PublishError(RuntimeError):
    """静态站装配输入无效或切换失败。"""


@dataclass(frozen=True)
class AssembledSite:
    output_dir: Path
    record_count: int | None
    corpus_generation: int | None
    manifest_hash: str | None


def _swap_directory(staged: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    backup = output.parent / f"{output.name}.previous-{uuid.uuid4().hex}"
    moved_previous = False
    try:
        if output.exists():
            output.rename(backup)
            moved_previous = True
        staged.rename(output)
        if moved_previous:
            shutil.rmtree(backup)
    except Exception:
        if moved_previous and not output.exists() and backup.exists():
            backup.rename(output)
        raise


def assemble_site(
    *,
    web_dir: str | Path,
    pagefind_dir: str | Path,
    output_dir: str | Path,
    manifest_path: str | Path | None = None,
) -> AssembledSite:
    web = Path(web_dir)
    pagefind = Path(pagefind_dir)
    output = Path(output_dir)
    index = web / "index.html"
    required_assets = [pagefind / name for name in ("pagefind.js", "pagefind-ui.js", "pagefind-ui.css")]
    if not index.is_file():
        raise PublishError(f"missing static entrypoint: {index}")
    missing = [str(path) for path in required_assets if not path.is_file()]
    if missing:
        raise PublishError(f"missing Pagefind assets: {', '.join(missing)}")

    metadata: dict[str, Any] = {
        "entrypoint_hash": hashlib.sha256(index.read_bytes()).hexdigest(),
        "pagefind_assets": len(list(pagefind.rglob("*"))),
    }
    if manifest_path is not None:
        manifest = Path(manifest_path)
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PublishError(f"invalid snapshot manifest: {manifest}: {exc}") from exc
        metadata.update(
            {
                "site_id": payload.get("site_id"),
                "corpus_generation": payload.get("corpus_generation"),
                "record_count": payload.get("count"),
                "excluded_count": len(payload.get("excluded", [])),
                "manifest_hash": payload.get("manifest_hash"),
            }
        )

    staged = output.parent / f"{output.name}.staged-{uuid.uuid4().hex}"
    try:
        staged.mkdir(parents=True, exist_ok=False)
        for entry in web.iterdir():
            destination = staged / entry.name
            if entry.is_dir():
                shutil.copytree(entry, destination)
            else:
                shutil.copy2(entry, destination)
        shutil.copytree(pagefind, staged / "pagefind")
        (staged / "build.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _swap_directory(staged, output)
    except Exception:
        if staged.exists():
            shutil.rmtree(staged)
        raise
    return AssembledSite(
        output_dir=output,
        record_count=metadata.get("record_count"),
        corpus_generation=metadata.get("corpus_generation"),
        manifest_hash=metadata.get("manifest_hash"),
    )
