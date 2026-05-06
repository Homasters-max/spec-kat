---
id: pattern/wiki-snapshot-loader
page_type: pattern
domain: sdd
layer: architecture
tags:
- read-only
- ssot
- pipeline
- automation
- domain/sdd
version: 1
created: '2026-05-06'
updated: '2026-05-06'
sources:
- raw/Wiki Skill DocGraph Integration Plan.md
---
# WikiSnapshotLoader

Единственный компонент, разрешённый для чтения `/wiki/vN/` snapshot (Q18, I-WSL-2). Все остальные компоненты MUST NOT читать wiki-файлы напрямую.

## How It Works

**Интерфейс:**

```python
class WikiSnapshotLoader:
    def load_at(self, event_pos: int) -> WikiSnapshot:
        # I-WSL-1: raises SnapshotNotFound, no fallback

    def latest(self) -> WikiSnapshot:
        # lag ≤ 1 render-wiki iteration (I-WIKI-LAG-1)

    def current_pointer(self) -> tuple[int, str]:
        # returns (event_pos, snapshot_version)
```

**AgentLoop контракт (строгий порядок, Q18):**

```text
Step 1: EventLog.read(event_pos)            → получить event_pos
Step 2: WikiSnapshotLoader.load_at(event_pos) → получить wiki snapshot
Step 3: assert projection.event_pos == snapshot.event_pos  (I-SNAPSHOT-ALIGN-1)
```

`I-SNAPSHOT-ALIGN-1`: projection snapshot и wiki snapshot MUST быть на одном `event_pos`. Нарушение = RuntimeError.

**`SnapshotNotFound`:** выбрасывается если snapshot для `event_pos` не существует. Нет fallback — это намеренно (предотвращает чтение stale данных).

## When To Use

Вызывается [[context-kernel]] и [[wiki-semantic-extractor]] при построении контекстного пакета. Это единственный разрешённый путь к wiki snapshot — I-WSL-2 запрещает прямой доступ к `/wiki/vN/`.

## Trade-offs

- Строгий `SnapshotNotFound` без fallback гарантирует aligned snapshots, но требует что `render-wiki` успел сгенерировать snapshot для нужного `event_pos` до обращения.
- `lag ≤ 1 iteration` (I-WIKI-LAG-1) — acceptable для большинства use cases; при строгих требованиях к freshness — `load_at(event_pos)` вместо `latest()`.

## See Also

- [[render-wiki]]
- [[context-kernel]]
- [[wiki-semantic-extractor]]
- [[docgraph-dual-ssot]]
