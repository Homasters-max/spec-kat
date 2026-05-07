Сейчас у тебя нет “полного трейсинга”, у тебя есть только частичные сигналы (graph_calls, tests, отчёты) → поэтому и кажется, что агент “действует произвольно”.
Нужно ввести тотальный детерминированный execution trace — один источник правды для ВСЕХ действий.

Ниже — минимальная, но production-подходящая схема без усложнений.

🔴 Главная идея

👉 Ввести Execution Trace Log (ETL):

Любое действие агента = Event
Все события → append-only лог
Один запуск IMPLEMENT = один trace

Папка:

/root/project/.sdd/reports/T-XXX/
  ├── trace.jsonl          # ВСЕ события
  ├── summary.json         # агрегат
  ├── timeline.txt         # человекочитаемый порядок
1. 🎯 Что логировать (полный охват)

Логируешь ВСЁ, что влияет на поведение:

A. Graph calls
resolve / explain / trace
входные аргументы
результат (node_ids, edges count)
B. File I/O (критично!)
read file
write file
path + причина (откуда взяли)
C. Команды / CLI
sdd команды
bash команды
exit code
D. RAG / Context (если есть)
query
какие документы вернулись
E. Решения агента (очень важно)
“почему выбрал этот файл”
“почему делает write”

👉 иначе ты видишь действия, но не причину

2. 📦 Формат события (единый)
{
  "event_id": "uuid",
  "ts": 1714470000.123,
  "session_id": "eval-s1",
  "task_id": "T-5603",

  "type": "FILE_READ | FILE_WRITE | GRAPH_CALL | CLI | DECISION",

  "payload": {
    "path": "src/sdd/...",
    "command": "sdd explain ...",
    "args": {...},
    "result": {...}
  },

  "meta": {
    "step": "IMPLEMENT:4.5-B",
    "allowed": true,
    "reason": "from explain output"
  }
}

👉 ключевое:

type — строгий enum
meta.allowed — сразу видно нарушения
step — привязка к протоколу
3. ⚙️ Где внедрять (без боли)
3.1 Обёртка над ВСЕМ

Создаёшь:

class ExecutionTracer:
    def log(event: dict): ...

И используешь как единую точку входа.

3.2 Обязательные hook points

Перехватываешь:

1. Graph CLI
resolve.run → tracer.log(...)
explain.run → tracer.log(...)
trace.run → tracer.log(...)
2. File operations

👉 САМЫЙ ВАЖНЫЙ пункт

Заворачиваешь:

open(...)
Path.read_text(...)
Path.write_text(...)

в:

traced_read(path)
traced_write(path)
3. sdd write
sdd write → tracer.log(type="WRITE_ATTEMPT")
4. Agent decisions

Перед действием:

tracer.log({
  "type": "DECISION",
  "payload": {
    "action": "write_file",
    "target": "...",
    "reason": "based on explain FILE:X"
  }
})
4. 🧠 Ключевая фишка (обязательно)
👉 Связь с graph (иначе бесполезно)

Добавляешь:

meta = {
  "allowed": path in allowed_files,
  "source": "graph | task_input | fallback | unknown"
}
5. 🔍 Авто-детект проблем

После выполнения строишь summary:

{
  "total_events": 42,
  "graph_calls": 3,
  "file_reads": 10,
  "file_writes": 1,

  "violations": [
    "read outside allowed_files",
    "write without trace",
    "decision without graph evidence"
  ]
}
6. 🧪 Минимальные проверки (сразу найдут баги)

Добавь автоматические флаги:

if type == FILE_READ and not allowed:
    violation("SCOPE_VIOLATION")

if type == FILE_WRITE and not trace_called:
    violation("WRITE_WITHOUT_TRACE")

if type == DECISION and no graph reference:
    violation("UNGROUNDED_DECISION")
7. 📊 timeline (очень помогает)

Генерируешь:

[00.001] RESOLVE "eval target"
[00.050] EXPLAIN FILE:...
[00.120] READ src/...
[00.200] TRACE FILE:...
[00.300] WRITE src/...

👉 сразу видно:

пропущенные шаги
лишние действия
порядок
8. ⚠️ Частые реальные проблемы (ты их почти точно найдёшь)

После внедрения всплывёт:

❗ чтение файлов до explain
❗ лишние explain/trace (шум)
❗ write не из trace_path
❗ fallback используется слишком часто
❗ решения без graph обоснования
9. 🚀 Минимальный план внедрения
ExecutionTracer (jsonl writer)
Обёртка file I/O
Логирование graph CLI
Логирование write
summary + violations

👉 этого уже достаточно, чтобы вскрыть 90% проблем

💡 Итог

Тебе не хватает не тестов, а:

❗ полного детерминированного execution trace

После этого:

исчезает “кажется работает странно”
появляется: “вот точка, где агент нарушил протокол”