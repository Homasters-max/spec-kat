# Plan_v63 — Phase 63: Behavioral Trace Analysis (L-TRACE Phase 2)

Status: DRAFT
Spec: specs/Spec_v63_BehavioralTraceAnalysis.md

---

## Logical Context

```
type: none
rationale: "Standard phase. Continues L-TRACE layer from Phase 62: adds COMMAND output enrichment, ConversationParser, and behavioral detection rules."
```

---

## Milestones

### M1: COMMAND Output Enrichment

```text
Spec:       §1 (BC-63-C1, BC-63-C2, BC-63-C3), §2 (COMMAND payload schema), §5 (Types)
BCs:        BC-63-C1, BC-63-C2, BC-63-C3
Invariants: I-TRACE-CMD-1, I-TRACE-CMD-2, I-TRACE-RAW-1
Depends:    — (Phase 62 COMPLETE)
Risks:      hook stdin format may not carry tool_use_id → COMMAND payload writes transcript_ref: null;
            enrich-trace fills values later (OI-63-1 resolution path)
```

Доставляет: расширенный COMMAND payload (`category`, `exit_code`, `output_len`, `output_snippet`, `output_ref`, `transcript_ref`) в hook writer. `write_output_file()` создаёт `cmd_outputs/<ts_ms>.txt`. `trace.jsonl` — read-only после записи (I-TRACE-RAW-1).

---

### M2: ConversationParser + Session Anchoring + enrich-trace

```text
Spec:       §2 (Linking strategy, Session anchoring, Storage layout), §5 (Types & Interfaces),
            §6 (sdd enrich-trace, sdd record-session changes)
BCs:        BC-63-P1, BC-63-P2, BC-63-P3
Invariants: I-TRANSCRIPT-1, I-TRANSCRIPT-2, I-TRANSCRIPT-3, I-TRACE-REF-1, I-TRACE-RAW-1, I-TRACE-CMD-1
Depends:    M1 (COMMAND payload schema зафиксирована, transcript_ref нужен для linking)
Risks:      transcript_offset точность — фиксируется как размер файла в байтах на старте сессии;
            fuzzy match по тексту команды запрещён (I-TRACE-REF-1);
            большой transcript → парсер читает только с offset, не с начала (I-TRANSCRIPT-2)
```

Доставляет: `src/sdd/transcript/parser.py` с `parse_session()`, `find_tool_result()`, `project_dir_from_cwd()`, `latest_transcript()`. Изменение `record-session` (anchor_transcript). Новая команда `sdd enrich-trace T-NNN` (пишет `trace_enriched.jsonl`, не трогает `trace.jsonl`).

---

### M3: Behavioral Detection Rules + complete integration

```text
Spec:       §6 (sdd trace-summary, sdd complete changes), §5 (TraceSummary), §2 (Behavioral rules)
BCs:        BC-63-B1, BC-63-B2, BC-63-B3
Invariants: I-BEHAV-WINDOW-1, I-BEHAV-NONBLOCK-1, I-BEHAV-EXPLAIN-1, I-BEHAV-FALSE-SUCCESS-1
Depends:    M1 (exit_code в payload), M2 (enrich-trace заполняет exit_code до вызова summary)
Risks:      FALSE_SUCCESS зависит от exit_code — без enrich-trace часть правил не сработает;
            behavioral_violations Phase 63 — INFORMATIONAL ONLY (I-BEHAV-NONBLOCK-1);
            EXPLAIN_NOT_USED: не применять к GRAPH_CALL в последних 5 событиях (I-BEHAV-EXPLAIN-1)
```

Доставляет: `detect_behavioral_violations(events)` в `summary.py`. 6 правил: COMMAND_FAILURE_IGNORED, BLIND_WRITE, THRASHING, LOOP_DETECTED, EXPLAIN_NOT_USED, FALSE_SUCCESS. `TraceSummary` расширен полями `command_failures` и `behavioral_violations`. `sdd complete T-NNN` вызывает `enrich-trace` перед `trace-summary`.

---

### M4: Unit Tests

```text
Spec:       §9 (Unit Tests, 13 тестов)
BCs:        BC-63-T1
Invariants: все новые invariants Phase 63 (I-TRACE-CMD-1, I-TRANSCRIPT-2, I-TRACE-REF-1,
            I-TRACE-RAW-1, I-BEHAV-WINDOW-1, I-BEHAV-EXPLAIN-1, I-BEHAV-FALSE-SUCCESS-1)
Depends:    M1, M2, M3 (все компоненты должны существовать)
Risks:      тесты должны использовать фиктивные transcript JSONL (не production ~/.claude/);
            I-DB-TEST-1 аналог: тесты не касаются real transcript файлов
```

Доставляет: 13 unit-тестов в `tests/unit/tracing/` и `tests/unit/transcript/` согласно таблице в Spec §9. Все тесты проходят `pytest` без errors.

---

## Risk Notes

- R-1: `tool_use_id` недоступен в hook stdin (OI-63-1) → `transcript_ref: null`; enrich-trace использует timestamp fallback; exit_code может оставаться null если оба метода не сработали (I-TRACE-CMD-2 допускает null)
- R-2: `trace.jsonl` immutability (I-TRACE-RAW-1) — enrich-trace MUST писать только в `trace_enriched.jsonl`; тест `test_enrich_trace_writes_enriched_not_raw` верифицирует это
- R-3: Большой transcript файл — парсер читает с `transcript_offset` в байтах, seek()-based; не загружает весь файл
- R-4: Behavioral rules — INFORMATIONAL ONLY в Phase 63 (I-BEHAV-NONBLOCK-1); блокировок нет; нарушения только в summary.json и выводе команд
- R-5: `sdd complete` изменяется — `enrich-trace` вызывается первым; если enrich падает (нет transcript) → команда продолжает (не блокирует завершение задачи)
