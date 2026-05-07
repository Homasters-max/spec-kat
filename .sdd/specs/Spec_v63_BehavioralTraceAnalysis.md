# Spec_v63 — Behavioral Trace Analysis (L-TRACE Phase 2)

Status: Draft
Baseline: Spec_v62_ExecutionTraceLayer.md

---

## 0. Goal

Phase 62 создал L-TRACE: append-only лог действий агента в `trace.jsonl`.
Проблема: trace.jsonl содержит только структурные факты (тип события, путь, команда).
Нет результатов: exit_code, output, полных ответов инструментов, reasoning LLM.

Без этого невозможно ответить "агент сделал глупость?" без ручного разбора.
Без полных данных нет материала для файн-тюнинга.

Phase 63 закрывает это тремя компонентами:

1. **COMMAND Output Enrichment** — обогатить COMMAND payload через hook (exit_code, output_snippet)
2. **ConversationParser** — парсер `~/.claude/projects/<project>/sessionId.jsonl`,
   извлекает полные пары `tool_use ↔ tool_result` и текст LLM
3. **Behavioral Detection Rules** — 5 поведенческих паттернов в `sdd trace-summary`

**Ключевое открытие:** conversation transcript содержит ВСЕ данные сессии:
- полные входы инструментов (не обрезанные до 300 chars)
- полные выходы инструментов (stdout, содержимое файлов)
- exit codes для Bash (через parsing tool_result)
- LLM reasoning (thinking blocks)
- тексты сообщений ассистента и пользователя

**Роли:**
- `trace.jsonl` = **INDEX**: порядок событий, таймстемпы, структурные нарушения, `transcript_ref` указатели
- `transcript` = **SOURCE OF TRUTH**: все данные (полные input/output, exit_code, reasoning)

### Known Constraint (OI-63-1)

PostToolUse hook НЕ получает `tool_response` в текущей среде.
ConversationParser решает это: exit_code и output берём из транскрипта, не из хука.

---

## 1. Scope

### In-Scope

- BC-63-C1: COMMAND payload — `exit_code`, `category`, `output_len`, `output_snippet`
- BC-63-C2: `write_output_file()` в writer.py
- BC-63-C3: `output_ref` в COMMAND payload
- BC-63-P1: `ConversationParser` — модуль `src/sdd/transcript/parser.py`
- BC-63-P2: Session anchoring — `transcript_path` + `transcript_offset` в `current_session.json`
- BC-63-P3: `sdd enrich-trace T-NNN` — команда обогащения trace.jsonl данными из транскрипта
- BC-63-B1: `detect_behavioral_violations(events)` в summary.py
- BC-63-B2: 6 правил: COMMAND_FAILURE_IGNORED, BLIND_WRITE, THRASHING, LOOP_DETECTED, EXPLAIN_NOT_USED, FALSE_SUCCESS
- BC-63-B3: `TraceSummary` — поля `command_failures`, `behavioral_violations`
- BC-63-T1: тесты для всех новых компонентов

### Out-of-Scope

- ML / scoring / clustering поведений — Phase 64+
- Real-time блокировки на основе паттернов — Phase 64+
- THOUGHT/DECISION events — Phase 64+
- Межсессионная аналитика — Phase 64+
- Подключение `sdd-hook-log` как активного хука — отдельная задача
- Визуализация / dashboard — будущее

---

## 2. Architecture

### L-TRACE + Transcript: два слоя

```
~/.claude/projects/<project>/<sessionId>.jsonl   ← ConversationTranscript (источник истины для in/out)
.sdd/reports/T-NNN/trace.jsonl                   ← ExecutionTrace (структурный индекс)
.sdd/reports/T-NNN/summary.json                  ← анализ нарушений
.sdd/reports/T-NNN/cmd_outputs/<ts_ms>.txt       ← полный вывод команд (из транскрипта)
```

### Transcript record schema (Claude Code формат)

Каждая запись в JSONL содержит:
```json
{
  "uuid": "80e6369c-...",           // уникальный ID записи
  "parentUuid": "3c9f79a9-...",     // родительская запись в дереве диалога
  "type": "user" | "assistant",
  "sessionId": "a8a9355b-...",      // = имя файла (без .jsonl)
  "timestamp": "2026-04-30T20:58:09.127Z",
  "cwd": "/root/project",
  "message": {
    "role": "user" | "assistant",
    "content": [...]                // блоки: text, thinking, tool_use, tool_result
  },
  "sourceToolAssistantUUID": "...", // (только user records) UUID ассистента-источника tool_use
  "toolUseResult": "..."            // (только user records) краткий статус
}
```

### Linking strategy: transcript ↔ trace.jsonl

```
tool_use (assistant record)
    .id  →  tool_use_id
            ↓
tool_result (user record, sourceToolAssistantUUID = assistant.uuid)
    .content[].type == "tool_result"
    .content[].tool_use_id == tool_use.id
    .content[].content[].text  ← полный вывод

Связь с trace.jsonl COMMAND event — детерминированная:
    tool_result.tool_use_id == trace.payload.transcript_ref.tool_use_id

    Fallback (если tool_use_id не был записан в hook):
        abs(parse(transcript.timestamp) - trace.ts) < 2.0
```

**Правило хука:** при записи COMMAND event хук ДОЛЖЕН включать `tool_use_id` из stdin (если доступен).
Fuzzy match по тексту команды (`command[:300]`) — ЗАПРЕЩЁН: недетерминирован при одинаковых командах и быстрой последовательности.

### Session anchoring (BC-63-P2)

При `sdd record-session --type IMPLEMENT --phase N --task T-NNN`:
1. Определить project dir: `cwd` → `~/.claude/projects/<project_key>/`
2. Найти активный transcript: самый свежий `.jsonl` по mtime
3. Записать в `current_session.json`:
   ```json
   {
     "session_id": "...",
     "task_id": "T-NNN",
     "transcript_path": "~/.claude/projects/-root-project/a8a9355b-....jsonl",
     "transcript_offset": 12345
   }
   ```
4. `transcript_offset` = размер файла в байтах на момент старта сессии

Парсер читает транскрипт начиная с `transcript_offset` → видит только записи текущей сессии.

### COMMAND payload (итоговая схема)

```json
{
  "command": "sdd complete T-6208 2>&1",
  "category": "SDD",
  "exit_code": 0,
  "output_len": 847,
  "output_snippet": "Trace summary for T-6208: 25 events...",
  "output_ref": ".sdd/reports/T-6208/cmd_outputs/1777580676123.txt",
  "transcript_ref": {
    "assistant_uuid": "80e6369c-...",
    "tool_use_id": "toolu_01Abc..."
  }
}
```

`transcript_ref` записывается хуком при создании COMMAND event.
Если `tool_use_id` недоступен в hook stdin — `transcript_ref: null` (fallback через timestamp).

Источник `exit_code` и `output` (заполняется при `enrich-trace`):
1. **Приоритет 1**: `hook.tool_response.exit_code` (если доступен — OI-63-1)
2. **Приоритет 2**: `ConversationParser` — из tool_result, найденного по `transcript_ref.tool_use_id`
3. **Fallback**: timestamp match (если `transcript_ref` = null); `exit_code=null` если ни один не сработал

### Storage layout

```
.sdd/reports/T-NNN/
    trace.jsonl           ← raw L-TRACE события (immutable после записи хуком)
    trace_enriched.jsonl  ← обогащённая копия (создаётся enrich-trace, не перезаписывает raw)
    summary.json          ← violations (scope + behavioral)
    cmd_outputs/          ← полные выводы команд
        <ts_ms>.txt
```

`trace.jsonl` MUST NOT изменяться после записи хуком.
`enrich-trace` ВСЕГДА пишет в `trace_enriched.jsonl`.

---

## 3. Domain Events

Новых SDD domain events не вводится.
ConversationTranscript — внешний артефакт Claude Code, не проходит через PostgreSQL EventStore.

> **Note:** EventStore = PostgreSQL (env: SDD_DATABASE_URL). DuckDB удалён из проекта полностью.
> Любые ссылки на DuckDB в документации — артефакт Phase 55 и ниже, не актуальны.

---

## 4. New Invariants

| ID | Statement | Hard/Soft |
|----|-----------|-----------|
| I-TRACE-CMD-1 | COMMAND payload MUST содержать `category`, `exit_code`, `output_len`, `output_snippet` | hard |
| I-TRACE-CMD-2 | `exit_code` MAY быть `null` (при отсутствии hook + transcript данных) | hard (допустимо) |
| I-TRANSCRIPT-1 | `transcript_path` в `current_session.json` MUST указывать на реально существующий файл | soft |
| I-TRANSCRIPT-2 | Парсер MUST читать транскрипт начиная с `transcript_offset` (не с начала файла) | hard |
| I-TRANSCRIPT-3 | Парсинг транскрипта — read-only; MUST NOT модифицировать Claude Code файлы | hard |
| I-BEHAV-WINDOW-1 | Behavioral rules: lookahead/lookback N=5 (фиксировано) | hard |
| I-BEHAV-NONBLOCK-1 | `behavioral_violations` Phase 63 — INFORMATIONAL ONLY | hard |
| I-BEHAV-EXPLAIN-1 | EXPLAIN_NOT_USED не применяется к GRAPH_CALL среди последних 5 событий | hard |
| I-BEHAV-FALSE-SUCCESS-1 | FALSE_SUCCESS срабатывает если exit_code == 0 AND ("FAILED" in output OR "ERROR" in output); `output` берётся из `output_snippet` или полного `cmd_outputs/*.txt` | hard |
| I-TRACE-RAW-1 | `trace.jsonl` MUST NOT модифицироваться после записи хуком; `enrich-trace` пишет ТОЛЬКО в `trace_enriched.jsonl` | hard |
| I-TRACE-REF-1 | COMMAND event MUST содержать `transcript_ref: {assistant_uuid, tool_use_id}` или `transcript_ref: null`; fuzzy match по тексту команды запрещён | hard |
| I-DB-EVENTSTORE-1 | EventStore = PostgreSQL. DuckDB не используется | hard |

### Preserved (Phase 62)

| ID | Statement |
|----|-----------|
| I-TRACE-COMPLETE-1 | FILE_WRITE MUST иметь предшествующий GRAPH_CALL в той же сессии |
| I-TRACE-SCOPE-1 | (soft) FILE_WRITE/FILE_READ вне allowed_files → SCOPE_VIOLATION |
| I-TRACE-ORDER-1 | Events отсортированы по ts |
| I-HOOK-2 | hook всегда exit 0 |

---

## 5. Types & Interfaces

### TranscriptRecord (парсер)

```python
@dataclass
class ToolPair:
    """Связанная пара tool_use + tool_result из транскрипта."""
    tool_use_id: str
    tool_name: str               # "Bash", "Read", "Edit", "Write", ...
    tool_input: dict             # полный input (не обрезан)
    tool_output: str             # полный output из tool_result
    timestamp: str               # ISO 8601 из transcript record
    assistant_uuid: str
    user_uuid: str
```

```python
@dataclass
class TranscriptSession:
    """Результат парсинга одной SDD-сессии из транскрипта."""
    session_id: str              # SDD session_id из current_session.json
    transcript_path: str
    tool_pairs: list[ToolPair]   # все tool_use↔tool_result пары
    assistant_texts: list[str]   # тексты ответов ассистента
    # thinking_blocks — отложено до Phase 64 (объём + шум, не нужен для Phase 63 целей)
```

### ConversationParser API

```python
# src/sdd/transcript/parser.py

def parse_session(
    transcript_path: str,
    start_offset: int = 0,
) -> TranscriptSession:
    """Читает JSONL с start_offset, возвращает TranscriptSession."""

def find_tool_result(
    session: TranscriptSession,
    tool_use_id: str | None = None,
    ts: float | None = None,
) -> ToolPair | None:
    """
    Ищет ToolPair детерминированно:
    1. по tool_use_id (точная связка через transcript_ref)
    2. fallback: по timestamp (abs(ts - pair.ts) < 2.0) если tool_use_id=None
    Fuzzy match по тексту команды запрещён.
    """

def project_dir_from_cwd(cwd: str) -> Path:
    """'/root/project' → ~/.claude/projects/-root-project/"""

def latest_transcript(project_dir: Path) -> Path | None:
    """Возвращает самый свежий .jsonl файл по mtime."""
```

### TraceSummary (итоговый)

```python
@dataclass
class TraceSummary:
    task_id: str
    session_id: str
    total_events: int
    graph_calls: int
    file_reads: int
    file_writes: int
    commands: int
    violations: list[str]                                      # Phase 62
    command_failures: int = 0                                  # Phase 63
    behavioral_violations: list[str] = field(default_factory=list)  # Phase 63
```

---

## 6. CLI Interface

### Новая команда: `sdd enrich-trace T-NNN`

```
sdd enrich-trace T-NNN
    1. Читает current_session.json → transcript_path, transcript_offset
    2. parse_session(transcript_path, offset) → TranscriptSession
    3. Читает trace.jsonl (raw, без изменений)
    4. Для каждого COMMAND event:
       find_tool_result(session,
           tool_use_id=event.payload.transcript_ref.tool_use_id,  ← приоритет
           ts=event.ts)                                            ← fallback
       если найден: добавляет exit_code, output_snippet, output_ref в копию события
       вызывает write_output_file() → cmd_outputs/<ts_ms>.txt
    5. Записывает trace_enriched.jsonl (НЕ модифицирует trace.jsonl)
    Output: "Enriched N/M COMMAND events from transcript"
    exit 0 всегда (I-HOOK-2 аналог)
```

### Изменение `sdd complete T-NNN`

```
sdd complete T-NNN
    1. sdd enrich-trace T-NNN        ← NEW (Phase 63): обогащение из транскрипта
    2. sdd trace-summary T-NNN       ← Phase 62 + behavioral rules
    3. ... (прочие шаги как в Phase 62)
```

### Изменение `sdd record-session`

```
sdd record-session --type IMPLEMENT --phase N --task T-NNN
    ... (Phase 62 steps)
    + anchor_transcript(current_session.json)  ← NEW (Phase 63, BC-63-P2)
```

### Существующая команда `sdd trace-summary T-NNN`

```
    detect_violations()           ← Phase 62
    detect_behavioral_violations() ← Phase 63 (работает лучше после enrich-trace)
    output добавляет:
        Commands by category: SDD=12, TEST=1, GIT=0, SYSTEM=0
        Command failures (exit_code ≠ 0): N
        Behavioral violations: [...]

    Behavioral rules (6):
        COMMAND_FAILURE_IGNORED  — exit_code ≠ 0, следующее событие не GRAPH_CALL
        BLIND_WRITE              — FILE_WRITE без предшествующего GRAPH_CALL (I-TRACE-COMPLETE-1)
        THRASHING                — одинаковый файл изменён ≥3 раз подряд в окне N=5
        LOOP_DETECTED            — одинаковая команда повторена ≥3 раз подряд в окне N=5
        EXPLAIN_NOT_USED         — FILE_WRITE без GRAPH_CALL в последних 5 событиях
        FALSE_SUCCESS            — exit_code == 0, но output содержит "FAILED" или "ERROR"
                                   (ловит pytest --exit-zero, warnings-as-errors и т.п.)
```

---

## 7. Use Cases

### UC-63-1: Полный анализ IMPLEMENT-сессии

**Actor:** LLM (post-implementation)
**Trigger:** `sdd complete T-NNN`
**Pre:** `current_session.json` содержит `transcript_path` и `transcript_offset`
**Steps:**
1. `enrich-trace`: parse_session → find_tool_result per COMMAND (по tool_use_id) → создать trace_enriched.jsonl
2. `trace-summary`: читает trace_enriched.jsonl; detect_violations + detect_behavioral_violations → summary.json
3. Вывод: N команд, M нарушений, K behavioral violations
**Post:** `summary.json` содержит полные данные для анализа; `trace.jsonl` — нетронут; `trace_enriched.jsonl` + `cmd_outputs/*.txt` заполнены

### UC-63-2: Извлечение данных для файн-тюнинга

**Actor:** External data pipeline (после фазы)
**Trigger:** запрос данных по T-NNN
**Pre:** `enrich-trace` выполнен
**Steps:**
1. Читать `trace.jsonl` → структурный порядок событий (INDEX)
2. Читать `trace_enriched.jsonl` → обогащённые exit_code, output
3. Читать `cmd_outputs/*.txt` → полные выводы команд
4. Через `ConversationParser` + `transcript_ref.tool_use_id` → прямой доступ к tool_pairs, `assistant_texts`
**Post:** полный dataset in/out для сессии T-NNN; `thinking_blocks` — Phase 64

---

## 8. Integration

| Компонент | Направление | Назначение |
|-----------|-------------|------------|
| `sdd.transcript.parser` | ← `~/.claude/projects/` | read-only, I-TRANSCRIPT-3 |
| `sdd.commands.complete` | → `sdd.transcript.parser` | enrich-trace перед summary |
| `sdd.commands.record_session` | → `sdd.transcript.parser` | anchor при старте сессии |
| `sdd.tracing.writer` | ← `sdd.commands.enrich_trace` | write_output_file |
| PostgreSQL EventStore | не затронут | L-TRACE изолирован |

---

## 9. Verification

### BC-63-V1: Верификация ConversationParser

```bash
# После IMPLEMENT T-NNN запустить:
sdd enrich-trace T-NNN
# Проверить:
python3 -c "
import json
for line in open('.sdd/reports/T-NNN/trace.jsonl'):
    e = json.loads(line)
    if e['type'] == 'COMMAND' and e['payload'].get('exit_code') is not None:
        print('OK: exit_code =', e['payload']['exit_code'])
        print('   output_len =', e['payload']['output_len'])
        break
"
# Ожидаемо: exit_code=0 (не None), output_len>0
```

### Unit Tests

```bash
python3 -m pytest tests/unit/tracing/ tests/unit/transcript/ -v
```

| # | Test | Invariant |
|---|------|-----------|
| 1 | `test_parse_session_extracts_tool_pairs` | I-TRANSCRIPT-2 |
| 2 | `test_find_tool_result_by_command` | linking strategy |
| 3 | `test_project_dir_from_cwd` | BC-63-P2 |
| 4 | `test_latest_transcript_returns_newest` | BC-63-P2 |
| 5 | `test_enrich_trace_updates_exit_code` | I-TRACE-CMD-1 |
| 6 | `test_detect_command_failure_ignored` | COMMAND_FAILURE_IGNORED |
| 7 | `test_detect_blind_write` | BLIND_WRITE |
| 8 | `test_detect_thrashing` | THRASHING |
| 9 | `test_detect_loop` | LOOP_DETECTED |
| 10 | `test_explain_not_used` | I-BEHAV-EXPLAIN-1 |
| 11 | `test_detect_false_success` | I-BEHAV-FALSE-SUCCESS-1 |
| 12 | `test_find_tool_result_by_tool_use_id` | I-TRACE-REF-1 |
| 13 | `test_enrich_trace_writes_enriched_not_raw` | I-TRACE-RAW-1 |

---

## 10. Open Issues

| ID | Issue | Impact | Решение |
|----|-------|--------|---------|
| OI-63-1 | `tool_response` не доставляется в PostToolUse hook | COMMAND_FAILURE_IGNORED без hook данных | **РЕШЕНО**: ConversationParser (BC-63-P1) |
| OI-63-2 | `sdd-hook-log` не подключён в settings.local.json | ToolUseCompleted не пишется в EventStore | вне scope Phase 63 |

---

## 11. Preconditions

- Phase 62 COMPLETE
- `~/.claude/projects/<project>/` содержит JSONL transcript файлы
- EventStore = PostgreSQL; DuckDB не используется

---

## 12. Out of Scope

| Item | Phase |
|------|-------|
| ML / scoring / clustering | 64+ |
| Real-time блокировки | 64+ |
| THOUGHT/DECISION events | 64+ |
| Межсессионная аналитика | 64+ |
| Подключение sdd-hook-log | отдельная задача |
| Визуализация / dashboard | будущее |
