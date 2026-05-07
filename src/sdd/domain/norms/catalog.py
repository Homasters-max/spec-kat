"""NormEntry, NormCatalog, load_catalog — Spec_v3 §4.8, I-NRM-1..3."""

from __future__ import annotations

from dataclasses import dataclass, field

try:
    import yaml
    _safe_load = yaml.safe_load
except ImportError:  # stdlib fallback: JSON is a strict subset of YAML (I-LOGIC-COVER-3)
    import json as _json_mod
    _safe_load = _json_mod.load  # type: ignore[assignment]

from sdd.core.errors import MissingContext


@dataclass(frozen=True)
class NormEntry:
    norm_id:     str
    actor:       str   # "llm" | "human" | "any"
    action:      str
    result:      str   # "allowed" | "forbidden"
    description: str
    severity:    str   # "hard" | "soft" | "informational"


@dataclass(frozen=True)
class NormCatalog:
    entries: tuple[NormEntry, ...]
    strict:  bool = True  # default=DENY: any unlisted actor/action pair is forbidden (I-CMD-12)
    known_actions: frozenset[str] = field(default=frozenset(), init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "known_actions", frozenset(e.action for e in self.entries))

    def validate_actions(self, actions: frozenset[str]) -> None:
        """Raise ValueError if any action is not present in this catalog's known vocabulary.

        Call once at startup (after load_catalog) to catch action string drift between
        CommandSpec definitions and the norm catalog (I-NRM-VALIDATE-1).
        """
        unknown = actions - self.known_actions
        if unknown:
            raise ValueError(
                f"Action(s) not registered in norm catalog: {sorted(unknown)}"
            )

    def is_allowed(self, actor: str, action: str) -> bool:
        """Return False if any matching entry has result="forbidden".

        Matching: (entry.actor == actor OR entry.actor == "any") AND entry.action == action.

        Unknown action (no matching entry):
          strict=False: return True  — open-by-default (I-NRM-2)
          strict=True (default): return False — closed-by-default / DENY (I-CMD-12, I-NRM-3)
        """
        matching = [
            e for e in self.entries
            if (e.actor == actor or e.actor == "any") and e.action == action
        ]
        if any(e.result == "forbidden" for e in matching):
            return False
        if not matching:
            return not self.strict
        return True

    def get_norm(self, norm_id: str) -> NormEntry | None:
        """Look up first entry by norm_id. Returns None if not found."""
        for entry in self.entries:
            if entry.norm_id == norm_id:
                return entry
        return None


def load_catalog(path: str, strict: bool = True) -> NormCatalog:
    """Parse norm_catalog.yaml → NormCatalog(strict=strict).

    Default strict=True: any unlisted actor/action pair is DENY (I-CMD-12).
    Raises MissingContext if file absent.
    Deterministic: same file + same strict flag → structurally equal NormCatalog (I-NRM-1).
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = _safe_load(fh)
    except FileNotFoundError:
        raise MissingContext(f"Norm catalog not found: {path}")

    entries: list[NormEntry] = []
    for norm in data.get("norms", []):
        norm_id = norm.get("norm_id", "")
        actor = norm.get("actor", "any")
        description = norm.get("description", "")
        severity = norm.get("enforcement", "hard")

        for action in norm.get("forbidden_actions", []):
            entries.append(NormEntry(
                norm_id=norm_id,
                actor=actor,
                action=action,
                result="forbidden",
                description=description,
                severity=severity,
            ))
        for action in norm.get("allowed_actions", []):
            entries.append(NormEntry(
                norm_id=norm_id,
                actor=actor,
                action=action,
                result="allowed",
                description=description,
                severity=severity,
            ))

    return NormCatalog(entries=tuple(entries), strict=strict)
