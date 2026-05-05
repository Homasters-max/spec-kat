---
id: pattern/sandbox-manager
page_type: pattern
domain: sdd
layer: architecture
tags:
- enforcement
- pipeline
- write-path
- automation
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
---
# SandboxManager

L1-компонент: per-task изоляция исполнения. Каждый TaskRun получает изолированную FS, deterministic seed, отключённую сеть.

## How It Works

```python
class SandboxManager:
    def create(self, task_id: str) -> SandboxHandle:
        # git worktree → isolated tmp dir
        # seed = hash(task_id + phase_id)
        # network = disabled
        return SandboxHandle(path=tmp_dir, seed=seed)

    def commit(self, handle: SandboxHandle) -> None:
        # merge worktree → main repo (if tests pass)
        # cleanup tmp dir

    def discard(self, handle: SandboxHandle) -> None:
        # delete tmp dir, no merge
```

**Что изолируется:**

- FS root: изолированный tmp dir (агент не видит файлы вне SandboxHandle.path)
- Random seed: фиксирован = детерминированные результаты тестов (M9)
- Network: отключена = агент не может делать внешние запросы

**Lifecycle:** один Sandbox per Task (GL-8). ScopeGuard проверяет write_scope внутри sandbox path, не в основном репозитории.

**Commit условие:** после `AuditEngine.calculate()` — если M9 > threshold → commit, иначе discard.

## When To Use

Создаётся Session Orchestrator'ом сразу после `AgentHandle.start()`. Все write-операции агента идут в sandbox.

## Trade-offs

- git worktree overhead на каждую задачу — приемлемо для correctness гарантий.
- При discard все изменения теряются — агент должен заново реализовывать если новая сессия.
- Network isolation может сломать задачи требующие внешних ресурсов — нужен whitelist.

## See Also

- [[scope-guard]]
- [[audit-engine]]
- [[session-orchestrator]]
- [[global-laws]]
- [[sdd-component-inventory]]
