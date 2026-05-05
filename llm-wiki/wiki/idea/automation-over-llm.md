---
id: idea/automation-over-llm
page_type: idea
domain: wiki
layer: concept
tags:
- automation
- llm
- ssot
- pipeline
- domain/wiki
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/TASKS.md
---
# Automation Over LLM

## Summary
Архитектурный принцип [[wiki-cli]]: детерминированный код делает всё механическое, LLM — только смысловое. Разделение обязанностей между CLI (предсказуемо, быстро, без токенов) и LLM (понимание, извлечение, синтез).

## How It Works

**CLI выполняет:**
- Хэширование файлов, обнаружение изменений
- Разбивку на chunks, поиск по BM25-индексу
- Валидацию JSON-схем
- Применение unified diff, создание файлов
- Ведение логов, rebuild derived/

**LLM выполняет:**
- Извлечение сущностей и отношений из текста
- Выбор структуры страниц (create / diff / rewrite)
- Синтез ответов из нескольких страниц
- Разрешение смысловых конфликтов

**Граница** — [[context-packet]] (CLI → LLM) и [[extraction-result]] (LLM → CLI).

## When To Use
При проектировании любого нового шага pipeline: сначала задать вопрос "может ли это сделать детерминированный код?". Если да — не привлекать LLM.

## Trade-offs
- Требует явного проектирования seam'ов (ContextPacket, ExtractionResult)
- CLI-код нужно поддерживать, но он предсказуем и тестируем

## See Also
- [[wiki-cli]]
- [[context-packet]]
- [[extraction-result]]
- [[git-as-ssot]]
