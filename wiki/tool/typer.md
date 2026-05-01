# Typer

## Summary
Python-библиотека для построения CLI приложений на основе type hints. Используется в [[llm-knowledge-base]] как CLI framework для всех `wiki` команд.

## How It Works
- Команды определяются как обычные Python функции с type-annotated параметрами
- Автоматически генерирует `--help`, парсинг аргументов, валидацию типов
- Поддерживает subcommands, env vars (`WIKI_VAULT`), Path-типы

## When To Use
Для построения CLI инструментов в [[skill-cli-architecture]] паттерне. Хорошо сочетается с pydantic для валидации данных.

## Trade-offs
- **+** Минимальный boilerplate — одна функция = одна команда
- **+** Автогенерация help из docstrings и type hints
- **-** Зависимость от Click (внутренняя); для очень сложных CLI может не хватать flexibility

## See Also
- [[skill-cli-architecture]]
- [[llm-knowledge-base]]
