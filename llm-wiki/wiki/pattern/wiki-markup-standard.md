---
id: pattern/wiki-markup-standard
page_type: pattern
domain: wiki
layer: architecture
tags:
- markdown
- knowledge-base
- validation
- maintenance
- domain/wiki
version: 2
created: '2026-05-06'
updated: '2026-05-06'
sources:
- raw/SKILL.md
---
# Wiki Markup Standard

## Summary
Стандарт разметки wiki-страниц для совместимости с Obsidian и plain Markdown. Определяет правила блоков кода, callouts, wikilinks, таблиц и frontmatter.

## How It Works

**Блоки кода** — всегда с явным языком (I-WIKI-MARKUP-2), голый ` ``` ` запрещён:

```text
```python    # Python код, типы, dataclass
```yaml      # конфиг, frontmatter примеры
```json      # JSON структуры
```bash      # shell команды, CLI вызовы
```sql       # запросы
```toml      # pyproject.toml и аналоги
```text      # вывод команд, plain text примеры
```

**Callouts** (I-WIKI-MARKUP-1) — только в `derived/synthesis/`, в `wiki/idea|pattern|tool/` запрещены:

```markdown
> [!NOTE] Заголовок
> [!WARNING] Важно
> [!TIP] Совет
```

**Wikilinks** (I-WIKI-MARKUP-3) — синтаксис `\[\[page-id\]\]`; используется только для реальных страниц. Для описания синтаксиса в тексте — экранировать или заключать в backticks.

**Таблицы** — стандартный GFM, выравнивание только левое (`:---`).

**Frontmatter wiki-страниц:**

```yaml
---
id: pattern/page-name       # CLI auto
page_type: pattern          # idea | pattern | tool
domain: wiki                # из wiki_config.domains
layer: architecture         # из wiki_config.layers
tags: [pipeline, write-path, ingestion, domain/wiki]
version: 1                  # CLI auto
created: 2026-05-01         # CLI auto
updated: 2026-05-01         # CLI auto
sources:
  - raw/filename.md
---
```

## When To Use
Проверять при каждом создании или редактировании wiki-страницы. `wiki lint` проверяет FM и markup автоматически.

## Trade-offs
- Нарушение I-WIKI-MARKUP-2 (голый ` ``` `) → lint ERROR блокирует commit
- Callouts в knowledge pages → lint ERROR (не для synthesis/)
- Wikilink на несуществующую страницу → broken link в lint

## See Also
- [[wiki-taxonomy]]
- [[wiki-evolve]]
