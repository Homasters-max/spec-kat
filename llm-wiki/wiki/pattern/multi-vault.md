---
id: pattern/multi-vault
page_type: pattern
domain: wiki
layer: architecture
tags:
- knowledge-base
- pipeline
- cli
- automation
version: 3
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/guide.md
---
# Multi-Vault

## Summary
Паттерн управления несколькими независимыми wiki-vault'ами через глобальный реестр (`~/.wiki/vaults.yaml`) и команды [[wiki-cli]] `register`, `use`, `vaults`. Каждый vault изолирован: свои страницы, glossary, ingest_log, `domains`/`layers`.

## How It Works
Глобальный реестр хранится в `~/.wiki/vaults.yaml`. Активный vault — в `~/.wiki/active`.

**Логика разрешения vault (приоритет по убыванию):**

1. `WIKI_VAULT` env — явный override на один вызов
2. `~/.wiki/active` → lookup в `~/.wiki/vaults.yaml`
3. Ошибка: `No active vault. Run: wiki use <name>  or  export WIKI_VAULT=/path/to/vault`

Хардкодированного fallback нет — vault всегда нужно сконфигурировать явно.

**Команды:**

```bash
# Зарегистрировать vault
wiki register llm-wiki /root/project/obsidian-vault/llm-wiki -d "LLM Wiki knowledge base"
wiki register work     /home/user/work-wiki                  -d "Work project notes"

# Список vault'ов (активный помечен ▶)
wiki vaults

# Переключить активный vault
wiki use work

# Создать vault и сразу зарегистрировать
wiki init --vault /home/user/new-project --name new-project --domain llm

# Временно обратиться к другому vault без переключения
WIKI_VAULT=/root/project/obsidian-vault/llm-wiki wiki search "context packet"
```

Повторный вызов `wiki register` с тем же именем обновляет путь.

После `wiki use work` все последующие команды (`ingest`, `search`, `lint` и т.д.) работают с vault `work` без `--vault` флага.

## When To Use
- Несколько проектов с разными тематиками знаний (личная KB, рабочие заметки, SDD-процесс).
- Изоляция `domains`/`layers` между проектами — каждый vault имеет свой `wiki_config.yaml`.
- Временное переключение: `WIKI_VAULT=/tmp/other-wiki wiki search "test"` без изменения `~/.wiki/active`.

## Trade-offs
- **+** Полная изоляция: разные glossary, ingest_log, конфигурации.
- **+** `wiki use` меняет активный vault глобально; `WIKI_VAULT` env переопределяет только для одного вызова.
- **-** `WIKI_VAULT` env-переменная перекрывает реестр — может вызвать путаницу если задана в shell profile.
- Хардкодированного fallback нет — при отсутствии реестра команда завершается с ошибкой.

## See Also
- [[wiki-cli]]
- [[git-as-ssot]]
- [[ingest-log]]
