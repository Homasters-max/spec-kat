from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from pydantic import BaseModel

if TYPE_CHECKING:
    from models import GlossaryProposal


class WikiConfig(BaseModel):
    domain: str
    llm_model: str
    small_page_threshold: int
    vault_root: Path


def load_config(vault_root: Path) -> WikiConfig:
    path = vault_root / ".wiki" / "config" / "wiki_config.yaml"
    data = yaml.safe_load(path.read_text())
    return WikiConfig(**data)


def load_glossary(vault_root: Path) -> list[dict]:
    path = vault_root / ".wiki" / "config" / "glossary.yaml"
    return yaml.safe_load(path.read_text()) or []


def save_glossary_pending(vault_root: Path, proposals: list[GlossaryProposal]) -> None:
    path = vault_root / ".wiki" / "config" / "glossary_pending.yaml"
    existing: list[dict] = []
    if path.exists():
        existing = yaml.safe_load(path.read_text()) or []
    new_entries = [p.model_dump() for p in proposals]
    path.write_text(yaml.dump(existing + new_entries, allow_unicode=True))
