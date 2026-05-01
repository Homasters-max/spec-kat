# Glossary Discovery

## Summary
Механизм обнаружения новых сущностей без блокировки pipeline (I-WIKI-DISCOVERY-1). LLM предлагает новые сущности через `ExtractionResult.glossary_proposals`. В `glossary.yaml` они попадают только через явный `wiki sync-glossary` post-action — прямая запись из Stage 1 или Stage 2 запрещена.

## How It Works
1. LLM в Stage 1 видит [[extraction-result]].`entities` с `in_glossary: false` — кандидаты на discovery
2. LLM формирует `glossary_proposals` с `suggested_page`, `type`, `reason`
3. После evolve proposals сохраняются в `runtime/glossary_pending.yaml`
4. Пользователь запускает `wiki sync-glossary` — интерактивный review и добавление в `glossary.yaml`

## When To Use
Автоматически возникает при каждом [[wiki-evolve]] когда LLM обнаруживает неизвестные сущности. [[entity-registry]] не нужно обновлять до ingest — нет bottleneck.

## Trade-offs
- **+** Ingest не блокируется на sync glossary — новые сущности обрабатываются сразу
- **+** Явный review предотвращает засорение glossary
- **-** Пользователь должен помнить запускать `wiki sync-glossary`

## See Also
- [[entity-registry]]
- [[extraction-result]]
- [[wiki-evolve]]
