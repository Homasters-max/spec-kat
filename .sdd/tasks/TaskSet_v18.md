# TaskSet_v18 — Phase 18: Spatial Index (SI)

Spec: specs/Spec_v18_SpatialIndex.md
Plan: plans/Plan_v18.md

---

T-1801: Add Navigation Invariants to CLAUDE.md §INV

Status:               DONE
Spec ref:             Spec_v18 §2 — Navigation Protocol (BC-18-NAV); §6 I-NAV-1..9
Invariants:           I-NAV-1, I-NAV-2, I-NAV-3, I-NAV-4, I-NAV-5, I-NAV-6,
                      I-NAV-7, I-NAV-8, I-NAV-9, I-CONTEXT-1, I-GIT-OPTIONAL,
                      I-NAV-SESSION-1, I-SESSION-2
spec_refs:            [Spec_v18 §2, Spec_v18 §6 I-NAV-1..9]
produces_invariants:  [I-NAV-1, I-NAV-2, I-NAV-3, I-NAV-4, I-NAV-5, I-NAV-6,
                       I-NAV-7, I-NAV-8, I-NAV-9, I-CONTEXT-1, I-GIT-OPTIONAL,
                       I-NAV-SESSION-1, I-SESSION-2]
requires_invariants:  []
Inputs:               CLAUDE.md (existing §INV section)
Outputs:              CLAUDE.md (§INV extended with I-NAV-1..9, I-CONTEXT-1,
                      I-GIT-OPTIONAL, I-NAV-SESSION-1, I-SESSION-2)
Acceptance:           CLAUDE.md §INV содержит все 13 инвариантов (I-NAV-1..9,
                      I-CONTEXT-1, I-GIT-OPTIONAL, I-NAV-SESSION-1, I-SESSION-2)
                      с точными формулировками из Spec_v18 §6
Depends on:           —

---

T-1802: Create .sdd/config/glossary.yaml

Status:               DONE
Spec ref:             Spec_v18 §3 BC-18-0 — TERM-узлы; §6 I-DDD-0, I-TERM-2
Invariants:           I-DDD-0, I-TERM-2
spec_refs:            [Spec_v18 §3 BC-18-0, Spec_v18 §6 I-DDD-0]
produces_invariants:  [I-DDD-0]
requires_invariants:  []
Inputs:               CLAUDE.md §TOOLS (список команд для links), Spec_v18 §3 glossary schema
Outputs:              .sdd/config/glossary.yaml (≥8 TERM-записей)
Acceptance:           .sdd/config/glossary.yaml существует; содержит ≥8 записей;
                      каждая запись имеет непустые поля id, label, definition, links;
                      links ссылаются на существующие node_id форматов
                      COMMAND:*, EVENT:*, INVARIANT:*
Depends on:           —

---

T-1803: Implement SpatialNode + SpatialEdge Dataclasses

Status:               DONE
Spec ref:             Spec_v18 §3 BC-18-0 — SpatialNode, SpatialEdge; §5 Types;
                      §6 I-SUMMARY-1, I-SUMMARY-2, I-SIGNATURE-1, I-DDD-1
Invariants:           I-SUMMARY-1, I-SUMMARY-2, I-SIGNATURE-1, I-DDD-1
spec_refs:            [Spec_v18 §3 BC-18-0, Spec_v18 §5, Spec_v18 §6 I-SUMMARY-1/2]
produces_invariants:  [I-SUMMARY-1, I-SUMMARY-2, I-SIGNATURE-1, I-DDD-1]
requires_invariants:  [I-DDD-0]
Inputs:               .sdd/config/glossary.yaml (schema reference для TERM-полей),
                      Spec_v18 §3 BC-18-0 (dataclass definitions)
Outputs:              src/sdd/spatial/__init__.py,
                      src/sdd/spatial/nodes.py,
                      tests/unit/spatial/__init__.py,
                      tests/unit/spatial/test_nodes.py
Acceptance:           pytest tests/unit/spatial/test_nodes.py PASS;
                      SpatialNode frozen; SpatialEdge frozen;
                      TERM-поля (definition="", aliases=(), links=()) как defaults;
                      no class TermNode anywhere in src/sdd/; I-SUMMARY-1 проверен;
                      I-SIGNATURE-1 проверен
Depends on:           T-1802

---

T-1804: Implement SpatialIndex + IndexBuilder

Status:               DONE
Spec ref:             Spec_v18 §3 BC-18-1 — SpatialIndex, IndexBuilder; §5 JSON schema;
                      §6 I-SI-1, I-SI-4, I-SI-5, I-DDD-0, I-DDD-1, I-TERM-1, I-TERM-2,
                      I-TERM-COVERAGE-1, I-SUMMARY-1, I-SUMMARY-2, I-SIGNATURE-1
Invariants:           I-SI-1, I-SI-4, I-SI-5, I-DDD-0, I-DDD-1,
                      I-TERM-1, I-TERM-2, I-TERM-COVERAGE-1,
                      I-SUMMARY-1, I-SUMMARY-2, I-SIGNATURE-1
spec_refs:            [Spec_v18 §3 BC-18-1, Spec_v18 §5, Spec_v18 §6 I-SI-1/4/5]
produces_invariants:  [I-SI-1, I-SI-4, I-SI-5, I-DDD-0, I-DDD-1, I-TERM-1, I-TERM-2,
                       I-TERM-COVERAGE-1]
requires_invariants:  [I-SUMMARY-1, I-SUMMARY-2, I-SIGNATURE-1, I-DDD-1]
Inputs:               src/sdd/spatial/nodes.py,
                      .sdd/config/glossary.yaml,
                      src/sdd/infra/paths.py (existing, for spatial_index_file ref)
Outputs:              src/sdd/spatial/index.py,
                      tests/unit/spatial/test_index.py
Acceptance:           pytest tests/unit/spatial/test_index.py PASS;
                      build_index() строит 8 видов узлов (FILE/COMMAND/GUARD/REDUCER/
                      EVENT/TASK/INVARIANT/TERM); I-SI-1 уникальность node_id;
                      I-SI-4: два последовательных build дают идентичные node_ids;
                      I-DDD-0: TERM только из glossary.yaml;
                      meta содержит term_link_violations и term_coverage_gaps;
                      I-SUMMARY-2 fallback никогда не пустой
Depends on:           T-1803

---

T-1805: Implement Staleness Module

Status:               DONE
Spec ref:             Spec_v18 §3 BC-18-2 — staleness.py; §6 I-GIT-OPTIONAL, I-SI-5
Invariants:           I-GIT-OPTIONAL, I-SI-5
spec_refs:            [Spec_v18 §3 BC-18-2, Spec_v18 §6 I-GIT-OPTIONAL]
produces_invariants:  [I-GIT-OPTIONAL, I-SI-5]
requires_invariants:  [I-SI-5]
Inputs:               src/sdd/spatial/index.py (SpatialIndex dataclass, git_tree_hash field)
Outputs:              src/sdd/spatial/staleness.py,
                      tests/unit/spatial/test_staleness.py
Acceptance:           pytest tests/unit/spatial/test_staleness.py PASS;
                      current_git_hash() использует git ls-files -s (fast path);
                      is_stale() = False при недоступном git (I-GIT-OPTIONAL);
                      staleness_report() возвращает dict с ключами stale/index_tree/
                      head_tree/reason; I-SI-5: несовпадение git_hash → stale=True
Depends on:           T-1804

---

T-1806: Implement NavigationIntent + resolve_action + _FULL_CONSTRAINTS

Status:               DONE
Spec ref:             Spec_v18 §3 NavigationIntent, resolve_action, INTENT_CEILING,
                      _FULL_CONSTRAINTS; §6 I-NAV-7, I-NAV-8
Invariants:           I-NAV-7, I-NAV-8
spec_refs:            [Spec_v18 §3 BC-18-3 NavigationIntent, Spec_v18 §6 I-NAV-7/8]
produces_invariants:  [I-NAV-7, I-NAV-8]
requires_invariants:  [I-NAV-1, I-NAV-3, I-NAV-5, I-NAV-6]
Inputs:               Spec_v18 §3 (INTENT_CEILING dict, _FULL_CONSTRAINTS list,
                      resolve_action signature, DenialTrace, AllowedOperations)
Outputs:              src/sdd/spatial/navigator.py (новый файл: NavigationIntent,
                      DenialTrace, AllowedOperations, INTENT_CEILING, MODE_ORDER,
                      _modes_up_to(), _FULL_CONSTRAINTS, resolve_action()),
                      tests/unit/spatial/test_navigation_policy.py
Acceptance:           pytest tests/unit/spatial/test_navigation_policy.py PASS;
                      INTENT_CEILING содержит 5 типов (explore/locate/analyze/
                      code_write/code_modify — без "modify");
                      resolve_action() не содержит if-chain для FULL решений
                      (только _FULL_CONSTRAINTS registry loop);
                      DenialTrace.violated — конкретный список инвариантов (BUG-3);
                      intent=explore + FULL → violated=["I-NAV-8"] reason="intent_ceiling_exceeded";
                      FULL без intent → violated=["I-NAV-7"] reason="code_intent_required"
Depends on:           T-1803

---

T-1807: Implement NavigationSession + Persistence + fcntl.flock

Status:               DONE
Spec ref:             Spec_v18 §2 NavigationSession; §3 BC-18-3 session API;
                      §6 I-NAV-1, I-NAV-3, I-NAV-5, I-NAV-6, I-NAV-9,
                      I-NAV-SESSION-1, I-SESSION-2
Invariants:           I-NAV-1, I-NAV-3, I-NAV-5, I-NAV-6, I-NAV-9,
                      I-NAV-SESSION-1, I-SESSION-2
spec_refs:            [Spec_v18 §2 NavigationSession, Spec_v18 §6 I-NAV-SESSION-1]
produces_invariants:  [I-NAV-SESSION-1, I-SESSION-2]
requires_invariants:  [I-NAV-7, I-NAV-8]
Inputs:               src/sdd/spatial/navigator.py (NavigationIntent, DenialTrace),
                      Spec_v18 §2 (nav_session.json schema, lock API)
Outputs:              src/sdd/spatial/navigator.py (добавить: NavigationSession,
                      _session_lock(), load_session(), save_session(), clear_session()),
                      tests/unit/spatial/test_navigation_session.py
Acceptance:           pytest tests/unit/spatial/test_navigation_session.py PASS;
                      load_session() при отсутствии файла → fresh session (не ошибка);
                      load_session() при невалидном JSON → fresh session + warning;
                      save_session() записывает атомарно (tmp + os.replace);
                      next_step() инкрементирует step_id, сбрасывает term_searched/intent;
                      can_load_full() = False если нет SUMMARY/SIGNATURE в loaded_modes;
                      can_load_full_step() = False при count>=1 или без code_write/modify intent;
                      _session_lock() использует fcntl.flock (I-SESSION-2);
                      lock timeout 5s → nav_invariant_violation reason="session_lock_timeout"
Depends on:           T-1806

---

T-1808: Implement Navigator Class + Fuzzy Search

Status:               DONE
Spec ref:             Spec_v18 §3 BC-18-3 — Navigator class, resolve(), search(),
                      not_found_response(); §6 I-SI-2, I-SI-3, I-FUZZY-1, I-SEARCH-2
Invariants:           I-SI-2, I-SI-3, I-FUZZY-1, I-SEARCH-2
spec_refs:            [Spec_v18 §3 BC-18-3 Navigator, Spec_v18 §6 I-SI-2/3]
produces_invariants:  [I-SI-2, I-SI-3, I-FUZZY-1, I-SEARCH-2]
requires_invariants:  [I-NAV-SESSION-1, I-NAV-7, I-NAV-8]
Inputs:               src/sdd/spatial/navigator.py (NavigationIntent, NavigationSession,
                      resolve_action, DenialTrace),
                      src/sdd/spatial/index.py (SpatialIndex)
Outputs:              src/sdd/spatial/navigator.py (добавить: Navigator class,
                      kind_priority dict, search_key() helper),
                      tests/unit/spatial/test_navigator.py
Acceptance:           pytest tests/unit/spatial/test_navigator.py PASS;
                      resolve() возвращает POINTER/SUMMARY/SIGNATURE/FULL корректно;
                      not_found_response() всегда must_not_guess=true, did_you_mean всегда присутствует;
                      fuzzy match по search key (basename/suffix/aliases), threshold≤2 (I-FUZZY-1);
                      sort: (distance, kind_priority, node_id lex) — детерминирован (I-SI-2);
                      TERM aliases включены в поиск; TERM первым при равном distance (I-FUZZY-1);
                      search() pipeline: collect→sort→limit→render (I-SEARCH-2);
                      I-SI-3: нет open() после load_index при cache hit;
                      session=None → инварианты не проверяются (legacy/тесты)
Depends on:           T-1807, T-1804

---

T-1809: Implement nav_get.py + paths.py Extensions + test_nav_get.py

Status:               DONE
Spec ref:             Spec_v18 §3 BC-18-4 nav_get.py, BC-18-6 paths.py;
                      §6 I-SI-3, I-NAV-SESSION-1, I-SESSION-2, I-GIT-OPTIONAL
Invariants:           I-SI-3, I-NAV-SESSION-1, I-SESSION-2
spec_refs:            [Spec_v18 §3 BC-18-4, Spec_v18 §3 BC-18-6]
produces_invariants:  [I-SI-3]
requires_invariants:  [I-NAV-SESSION-1, I-SESSION-2, I-GIT-OPTIONAL]
Inputs:               src/sdd/spatial/navigator.py (Navigator, load_session, save_session),
                      src/sdd/spatial/staleness.py (is_stale),
                      src/sdd/spatial/index.py (load_index),
                      src/sdd/infra/paths.py (existing)
Outputs:              src/sdd/spatial/commands/__init__.py,
                      src/sdd/spatial/commands/nav_get.py,
                      src/sdd/infra/paths.py (добавить spatial_index_file,
                      nav_session_file, nav_session_lock_file),
                      tests/unit/commands/__init__.py,
                      tests/unit/commands/test_nav_get.py
Acceptance:           pytest tests/unit/commands/test_nav_get.py PASS;
                      exit 0 при найденном node; exit 1 при not_found;
                      git_tree_hash присутствует в каждом успешном ответе;
                      stale_warning=true при stale index (WEAK-2 fix);
                      session load/save per call (I-NAV-SESSION-1);
                      --intent флаг передаётся в resolve(); I-SI-3: нет open() после load_index
Depends on:           T-1808, T-1805

---

T-1810: Implement nav_search.py + test_nav_search.py

Status:               DONE
Spec ref:             Spec_v18 §3 BC-18-4 nav_search.py;
                      §6 I-SEARCH-2, I-FUZZY-1, I-NAV-4
Invariants:           I-SEARCH-2, I-FUZZY-1, I-NAV-4
spec_refs:            [Spec_v18 §3 BC-18-4 nav_search.py, Spec_v18 §6 I-SEARCH-2]
produces_invariants:  [I-SEARCH-2, I-FUZZY-1]
requires_invariants:  [I-NAV-4]
Inputs:               src/sdd/spatial/navigator.py (Navigator.search),
                      src/sdd/spatial/index.py (load_index),
                      src/sdd/infra/paths.py (spatial_index_file),
                      src/sdd/spatial/commands/__init__.py
Outputs:              src/sdd/spatial/commands/nav_search.py,
                      tests/unit/commands/test_nav_search.py
Acceptance:           pytest tests/unit/commands/test_nav_search.py PASS;
                      TERM-узлы присутствуют в результатах; aliases match работает;
                      namespace priority: TERM > COMMAND > TASK > FILE при равном score;
                      --kind фильтрует по kind; --limit ограничивает ПОСЛЕ sort (I-SEARCH-2);
                      I-FUZZY-1: alias fuzzy match включает TERM aliases
Depends on:           T-1809

---

T-1811: Implement nav_rebuild.py + test_nav_rebuild.py

Status:               DONE
Spec ref:             Spec_v18 §3 BC-18-4 nav_rebuild.py;
                      §6 I-SI-1, I-SI-4, I-TERM-1, I-TERM-2, I-TERM-COVERAGE-1
Invariants:           I-SI-1, I-SI-4, I-TERM-1, I-TERM-2, I-TERM-COVERAGE-1
spec_refs:            [Spec_v18 §3 BC-18-4 nav_rebuild.py, Spec_v18 §6 I-SI-4]
produces_invariants:  [I-SI-4, I-TERM-1, I-TERM-2, I-TERM-COVERAGE-1]
requires_invariants:  [I-SI-1]
Inputs:               src/sdd/spatial/index.py (IndexBuilder, build_index, save_index),
                      src/sdd/spatial/staleness.py (current_git_hash),
                      src/sdd/infra/paths.py (spatial_index_file),
                      src/sdd/spatial/commands/__init__.py
Outputs:              src/sdd/spatial/commands/nav_rebuild.py,
                      tests/unit/commands/test_nav_rebuild.py
Acceptance:           pytest tests/unit/commands/test_nav_rebuild.py PASS;
                      --dry-run не пишет файл; exit 0 при успехе;
                      I-SI-4: diff обнаруживается при rename → exit 1 с diff в output;
                      warning в output при COMMAND без TERM-покрытия (I-TERM-COVERAGE-1);
                      meta.term_link_violations в output при невалидных links (I-TERM-2);
                      output JSON содержит nodes_written, terms_written, built_at, git_tree_hash
Depends on:           T-1809

---

T-1812: Implement nav_session.py + CLI Wiring (4 commands)

Status:               DONE
Spec ref:             Spec_v18 §3 BC-18-4 nav_session.py, BC-18-6 cli.py;
                      §6 I-NAV-SESSION-1, I-SESSION-2, I-NAV-6, I-NAV-9
Invariants:           I-NAV-6, I-NAV-9, I-NAV-SESSION-1, I-SESSION-2
spec_refs:            [Spec_v18 §3 BC-18-4 nav_session.py, Spec_v18 §3 BC-18-6]
produces_invariants:  [I-NAV-6, I-NAV-9]
requires_invariants:  [I-NAV-SESSION-1, I-SESSION-2]
Inputs:               src/sdd/spatial/navigator.py (load_session, save_session,
                      clear_session, NavigationSession),
                      src/sdd/infra/paths.py (nav_session_file, nav_session_lock_file),
                      src/sdd/cli.py (existing REGISTRY),
                      src/sdd/spatial/commands/{nav_get,nav_search,nav_rebuild}.py
Outputs:              src/sdd/spatial/commands/nav_session.py,
                      src/sdd/cli.py (4 команды добавлены в REGISTRY:
                      nav-get, nav-search, nav-rebuild, nav-session),
                      tests/unit/commands/test_nav_session.py
Acceptance:           pytest tests/unit/commands/test_nav_session.py PASS;
                      sdd nav-session next → step_id инкрементирован в session file;
                      sdd nav-session clear → nav_session.json удалён;
                      sdd nav-session show → JSON текущего состояния;
                      load missing = fresh session + нет ошибки (I-NAV-SESSION-1);
                      invalid JSON = fresh session + warning в stderr;
                      atomic save mock проверен (tmp + os.replace);
                      concurrent write safety mock (I-SESSION-2);
                      lock timeout mock → nav_invariant_violation reason="session_lock_timeout";
                      sdd nav-get / sdd nav-search / sdd nav-rebuild / sdd nav-session
                      доступны через sdd CLI (cli.py REGISTRY)
Depends on:           T-1810, T-1811

---

T-1813: Integration Test nav-rebuild on Real Project Root

Status:               DONE
Spec ref:             Spec_v18 §3 BC-18-5 integration; §7 M6 Pre/Post;
                      §9 Verification Stabilization Criteria
Invariants:           I-SI-1, I-SI-4, I-DDD-0, I-GIT-OPTIONAL
spec_refs:            [Spec_v18 §3 BC-18-5, Spec_v18 §9]
produces_invariants:  [I-SI-1, I-SI-4]
requires_invariants:  [I-DDD-0, I-GIT-OPTIONAL]
Inputs:               src/sdd/spatial/commands/nav_rebuild.py,
                      src/sdd/ (реальный project root),
                      .sdd/config/glossary.yaml
Outputs:              tests/integration/test_nav_rebuild_integration.py
Acceptance:           pytest tests/integration/test_nav_rebuild_integration.py PASS;
                      sdd nav-rebuild exit 0 на реальном project root;
                      nodes_written > 100; terms_written ≥ 8;
                      I-SI-1: дублей node_id нет;
                      I-SI-4: два последовательных rebuild → идентичные node_ids;
                      git_tree_hash присутствует в spatial_index.json;
                      no class TermNode in src/sdd/ (BUG-4 regression guard)
Depends on:           T-1812

---

<!-- Granularity: 13 tasks (TG-2: 10–30). Each independently implementable and testable (TG-1). -->
<!-- All Plan_v18 milestones covered: M0→T-1801/T-1802; M1→T-1803; M2→T-1804;
     M3→T-1805; M4→T-1806/T-1807/T-1808; M5→T-1809/T-1810/T-1811/T-1812; M6→T-1813 (SDD-3). -->
