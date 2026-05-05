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
version: 1
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
1. `--vault <path>` или `WIKI_VAULT` env — явный override на одну команду
2. `~/.wiki/active` → lookup в `~/.wiki/vaults.yaml`
3. Хардкод `/root/project/obsidian-vault`

**Команды:**

```bash
# Зарегистрировать vault
wiki register personal /root/project/obsidian-vault -d "Personal knowledge base"
wiki register work     /home/user/work-wiki          -d "Work project notes"

# Список vault'ов (активный помечен ▶)
wiki vaults

# Переключить активный vault
wiki use work

# Создать vault и сразу зарегистрировать
wiki init --vault /home/user/new-project --name new-project --domain llm

# Временно обратиться к другому vault без переключения
wiki --vault /root/project/obsidian-vault search "context packet"
```

Повторный вызов `wiki register` с тем же именем обновляет путь.

После `wiki use work` все последующие команды (`ingest`, `search`, `lint` и т.д.) работают с vault `work` без `--vault` флага.

## When To Use
- Несколько проектов с разными тематиками знаний (личная KB, рабочие заметки, SDD-процесс).
- Изоляция `domains`/`layers` между проектами — каждый vault имеет свой `wiki_config.yaml`.
- Временное переключение: `WIKI_VAULT=/tmp/other-wiki wiki search "test"` без изменения `~/.wiki/active`.

## Trade-offs
- **+** Полная изоляция: разные glossary, ingest_log, конфигурации.
- **+** `wiki use` меняет активный vault глобально; `--vault` переопределяет только для одной команды.
- **-** `WIKI_VAULT` env-переменная перекрывает реестр — может вызвать путаницу если задана в shell profile.
- При отсутствии реестра fallback на хардкод `/root/project/obsidian-vault`.

## See Also
- [[wiki-cli]]
- [[git-as-ssot]]
- [[ingest-log]]
