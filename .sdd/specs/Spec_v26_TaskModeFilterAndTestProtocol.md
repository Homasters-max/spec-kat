# Spec_v26_TaskModeFilterAndTestProtocol — Task Mode Filter Fix & Human Test Protocol

Status: DRAFT
Baseline: Spec_v25_ExplicitDBAccess.md

---

## 0. Goal

Phase 25 ввела два режима validate-invariants (task / system) через IMP-001 (T-2511).
Однако реализация содержит баг: фильтр в task mode убирает только ключ `"test"`,
пропуская `"test_full"` → `pytest tests/ -q` → полный suite запускается в task mode.

Дополнительно: отсутствует явный документ, определяющий зону ответственности по тестированию:
какие проверки выполняет агент автоматически, а какие — человек вручную.

Нарушенные принципы:

```
I-RRL-2: determinism — task gate зависит от DuckDB lock (test_full → D-state)
SEM-5:   fail fast   — вместо skip запускается полный suite, блокирующий агента
```

Данная спецификация вводит инвариант I-TASK-MODE-1 и закрывает IMP-003.

---

## 1. Диагностика дефектов

### D-1 — Фильтр task mode слишком узкий

`src/sdd/commands/validate_invariants.py:128`:

```python
# Баг (T-2511, Phase 25):
build_commands = {k: v for k, v in build_commands.items() if k != "test"}
```

Конфиг `.sdd/config/project_profile.yaml` содержит:

```yaml
test:      pytest tests/unit/ tests/integration/ -q   ← filtered ✓
test_full: pytest tests/ -q                           ← NOT filtered ✗ BUG
```

`test_full` запускается в task mode. Его returncode игнорируется acceptance check
(строка 464 проверяет `evt.name == "test"`, не `"test_full"`).
Результат: зря тратится время + D-state риск + вывод нигде не используется.

### D-2 — Тест не покрывает test_full

`tests/unit/commands/test_validate_invariants.py:407`:
`test_task_mode_skips_test_command` использует mock-конфиг из 3 команд
(`lint`, `typecheck`, `test`) — `test_full` не включён → баг не детектируется тестом.

### D-3 — Отсутствует документация протокола тестирования

`.sdd/docs/human-guide-phase-cycle.md` описывает цикл фазы, но не содержит раздела
о разделении тестов между агентом и человеком. Без явного протокола человек не знает,
что именно нужно прогнать перед закрытием фазы и почему `validate-invariants --task`
не запускает pytest.

---

## 2. Scope

### In-Scope

| ID | Файл | Изменение |
|----|------|-----------|
| BC-26-1 | `src/sdd/commands/validate_invariants.py:128` | Фильтр: `"pytest" not in v` |
| BC-26-2 | `CLAUDE.md §INV` | Добавить I-TASK-MODE-1 |
| BC-26-3 | `tests/unit/commands/test_validate_invariants.py` | Новый тест: test_full exclusion |
| BC-26-4 | `.sdd/docs/human-guide-phase-cycle.md` | Раздел "Протокол тестирования" |
| BC-26-5 | `.sdd/specs_draft/SDD_Improvements.md` | IMP-003 статус IMPLEMENTED |

### Out of Scope

- Пропуск `mypy` для non-src задач (отдельный IMP)
- Connection pooling или индексация DuckDB
- Изменения в логике acceptance check

---

## 3. Invariants

| ID | Statement |
|----|-----------|
| I-TASK-MODE-1 | В task mode из build_commands исключаются все команды, содержащие `"pytest"` в значении |

---

## 4. Interface Changes

### BC-26-1 — validate_invariants.py

```python
# До (баг, Phase 25 T-2511):
if command.validation_mode == "task":
    build_commands = {k: v for k, v in build_commands.items() if k != "test"}

# После (fix, I-TASK-MODE-1):
if command.validation_mode == "task":
    build_commands = {k: v for k, v in build_commands.items() if "pytest" not in v}
```

**Обоснование Option B** (`"pytest" not in v`) vs Option A (`not k.startswith("test")`):

- Option B устойчив к любым будущим именам ключей, запускающих pytest
- `acceptance` содержит "pytest" → тоже фильтруется; **безопасно**: `acceptance`
  уже исключается через `continue` в цикле (строка 142) и обрабатывается отдельно
  (строки 455-468), читая из оригинального `config`, а не из `build_commands`

### BC-26-3 — Новый тест

Добавить в класс `TestValidationModes`:

```python
@patch("sdd.commands.validate_invariants.load_config")
@patch("sdd.commands.validate_invariants.subprocess.Popen")
def test_task_mode_skips_all_pytest_commands(self, mock_popen, mock_load, handler):
    """IMP-003: task mode skips ALL commands containing 'pytest', not just 'test' key."""
    mock_load.return_value = _fake_config("lint", "typecheck", "test", "test_full")
    mock_popen.return_value = _popen_mock()
    cmd = ValidateInvariantsCommand(
        command_id=str(uuid.uuid4()),
        command_type="ValidateInvariants",
        payload={},
        phase_id=26,
        task_id="T-2601",
        config_path=".sdd/config/project_profile.yaml",
        cwd="/project",
        env_whitelist=(),
        timeout_secs=30,
        task_outputs=(),
        validation_mode="task",
    )
    with patch.object(handler, "_check_idempotent", return_value=False):
        handler.handle(cmd)
    executed = [call.args[0] for call in mock_popen.call_args_list]
    # IMP-003: test_full must also be excluded (not just "test")
    assert not any("test_full" in c for c in executed), \
        "test_full must not run in task mode (IMP-003)"
    assert not any("run-test" in c for c in executed), \
        "test must not run in task mode"
    assert any("run-lint" in c for c in executed), "lint must still run"
    assert any("run-typecheck" in c for c in executed), "typecheck must still run"
```

### BC-26-4 — Раздел в human-guide-phase-cycle.md

Добавить после раздела "## Быстрая шпаргалка: команды человека":

```markdown
## Протокол тестирования: агент vs человек

### Что запускает агент автоматически (task mode)

| Команда | Что | Когда |
|---------|-----|-------|
| `ruff check src/` | Линтинг исходников | Всегда |
| `mypy src/sdd/` | Статический typecheck | Всегда |
| `ruff check <outputs>` | Acceptance lint | Если в Outputs есть `.py` файлы |

**pytest НЕ запускается** в task mode — ни unit, ни integration (I-TASK-MODE-1).

### Что запускаешь ты вручную

Запускай тесты перед тем как давать финальное добро на завершение фазы (шаг 10):

```bash
# Unit — быстро (~30с), после каждых 3-4 задач или после рефакторинга
pytest tests/unit/ -q

# Unit + Integration — перед закрытием фазы
pytest tests/unit/ tests/integration/ -q

# Full suite — только перед PhaseComplete (финальная проверка)
pytest tests/ -q
```

### Когда system mode (явный запрос агенту)

```bash
sdd validate-invariants --system --phase N
```

Запускает все команды включая pytest. Используй только когда хочешь явно проверить
систему целиком (не в рамках task validation).

### Почему такое разделение

| Причина | Описание |
|---------|----------|
| D-state риск | `pytest tests/` открывает production DuckDB; если заблокирован — pytest зависает в D-state |
| Детерминизм | I-RRL-2: task gate не должен зависеть от состояния DB |
| Скорость | Task validation должна быть < 60с; full suite ~2-3 мин |
```

---

## 5. Files to Change

| Файл | BC | Изменение |
|------|----|-----------|
| `src/sdd/commands/validate_invariants.py` | BC-26-1 | 1 строка: `"pytest" not in v` |
| `CLAUDE.md §INV` | BC-26-2 | Добавить I-TASK-MODE-1 |
| `tests/unit/commands/test_validate_invariants.py` | BC-26-3 | 1 новый тест |
| `.sdd/docs/human-guide-phase-cycle.md` | BC-26-4 | Новый раздел ~35 строк |
| `.sdd/specs_draft/SDD_Improvements.md` | BC-26-5 | IMP-003 статус IMPLEMENTED |

---

## 6. Tests

### Unit

```
tests/unit/commands/test_validate_invariants.py::TestValidationModes::test_task_mode_skips_all_pytest_commands
```

### Verification

```bash
# Все unit тесты проходят
pytest tests/unit/commands/test_validate_invariants.py -q

# Команда завершается быстро — нет pytest в task mode
time sdd validate-invariants --phase 26 --task T-2601 2>&1

# test_full не эмитируется в task mode
sdd query-events --phase 26 | grep test_full  # пусто

# Протокол тестирования задокументирован
grep -n "Протокол тестирования" .sdd/docs/human-guide-phase-cycle.md
```

---

## 7. DoD

- [ ] BC-26-1: `test_full` и другие pytest-команды не запускаются в task mode
- [ ] BC-26-2: I-TASK-MODE-1 добавлен в CLAUDE.md §INV
- [ ] BC-26-3: новый тест `test_task_mode_skips_all_pytest_commands` проходит
- [ ] BC-26-4: раздел "Протокол тестирования" присутствует в human-guide
- [ ] BC-26-5: IMP-003 помечен IMPLEMENTED в SDD_Improvements.md
