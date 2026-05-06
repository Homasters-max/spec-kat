---
id: pattern/wiki-open-questions
page_type: pattern
domain: wiki
layer: architecture
tags:
- open-questions
- maintenance
- curation
- llm
- domain/wiki
version: 2
created: '2026-05-06'
updated: '2026-05-06'
sources:
- raw/SKILL.md
---
# Wiki Open Questions

## Summary
Протокол встраивания открытых архитектурных вопросов прямо в wiki-страницы в виде inline-блоков `## Open Questions` и `## Decisions`. Не требует отдельного документа — вопросы живут рядом с контекстом.

## How It Works

Два стандартных блока размещаются в **конце страницы** (перед `## See Also` или в самом конце):

```text
## Open Questions

- [ ] (P0) Как гарантируется total order EventLog?
- [ ] (P1) Нужен ли snapshotting для replay оптимизации?

## Decisions

- [x] (P0) EventLog = append-only, total order через event_index → \[\[eventstore-guard\]\]
```

**Приоритеты:**
- `(P0)` — ломает систему; ДОЛЖЕН быть закрыт до релиза
- `(P1)` — ломает фичи
- `(P2)` — оптимизация, nice-to-have

**Три правила:**
1. Вопрос НЕ удаляется — переносится в Decisions
2. Решённый вопрос: убрать из Open Questions → добавить в Decisions (приоритет + утверждение + wikilink на связанную страницу)
3. Все P0 ДОЛЖНЫ быть закрыты перед релизом

**Workflow — добавление вопроса:**

```bash
wiki show <page_id>
# создать runtime/tmp/<id>.diff.md — добавить строку в ## Open Questions
wiki apply-drafts
```

**Workflow — решение вопроса:**

```bash
# создать runtime/tmp/<id>.diff.md:
# 1. удалить строку из ## Open Questions
# 2. добавить в ## Decisions: - [x] (PN) <утверждение> → \[\[wikilink\]\]
wiki apply-drafts
# если P0 — обновить derived/open-questions.md через wiki-curate
```

## When To Use

Фильтр добавления — вопрос добавляется только если влияет на:
- **determinism** — воспроизводимость поведения
- **correctness** — правильность результата
- **production** — runtime, безопасность, данные

Перед изменением любого компонента: проверить `## Open Questions` на странице. Если есть P0 — сначала решить или задокументировать причину откладывания.

## Trade-offs
- Вопрос НИКОГДА не удаляется — только переносится в Decisions (история решений сохраняется)
- Формат Decisions: утверждение + wikilink обязателен; просто ссылка недостаточна
- Блоки размещаются строго в конце страницы (I-WIKI-OQ-0) — нарушение ломает lint
- `derived/open-questions.md` обновляется через [[wiki-curate]] при закрытии P0 или >5 изменениях

## See Also
- [[wiki-curate]]
- [[wiki-evolve]]
