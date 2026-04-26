---
name: improve-codebase-architecture
description: Find deepening opportunities in a codebase, informed by the domain language in .sdd/specs/SDD_Spec_v1.md and the decisions in .sdd/norms/norm_catalog.yaml. Use when the user wants to improve architecture, find refactoring opportunities, consolidate tightly-coupled modules, or make a codebase more testable and AI-navigable.
---

# Improve Codebase Architecture

Surface architectural friction and propose **deepening opportunities** — refactors that turn shallow modules into deep ones. The aim is testability and AI-navigability.

## Glossary

Use these terms exactly in every suggestion. Consistent language is the point — don't drift into "component," "service," "API," or "boundary." Full definitions in [LANGUAGE.md](LANGUAGE.md).

- **Module** — anything with an interface and an implementation (function, class, package, slice).
- **Interface** — everything a caller must know to use the module: types, invariants, error modes, ordering, config. Not just the type signature.
- **Implementation** — the code inside.
- **Depth** — leverage at the interface: a lot of behaviour behind a small interface. **Deep** = high leverage. **Shallow** = interface nearly as complex as the implementation.
- **Seam** — where an interface lives; a place behaviour can be altered without editing in place. (Use this, not "boundary.")
- **Adapter** — a concrete thing satisfying an interface at a seam.
- **Leverage** — what callers get from depth.
- **Locality** — what maintainers get from depth: change, bugs, knowledge concentrated in one place.

Key principles (see [LANGUAGE.md](LANGUAGE.md) for the full list):

- **Deletion test**: imagine deleting the module. If complexity vanishes, it was a pass-through. If complexity reappears across N callers, it was earning its keep.
- **The interface is the test surface.**
- **One adapter = hypothetical seam. Two adapters = real seam.**

This skill is _informed_ by the project's domain model — `.sdd/specs/SDD_Spec_v1.md` (formal vocabulary, source of truth) and `.sdd/norms/norm_catalog.yaml` (recorded decisions the skill should not re-litigate).

## Process

### 1. Explore

Read existing documentation first:

- `.sdd/specs/SDD_Spec_v1.md` — formal domain model and vocabulary (source of truth)
- `.sdd/config/glossary.yaml` — project glossary (editable)
- `.sdd/norms/norm_catalog.yaml` — SENAR norms (recorded decisions, do not modify directly)

Exploration constraints:
- Read `src/sdd/`, `tests/`, `.sdd/docs/`, `.sdd/plans/` directly via Explore agent.
- For current state: use `sdd show-state`, `sdd query-events`, `sdd validate-invariants` — do NOT read `.sdd/runtime/` or `.sdd/state/` directly.

Before organic exploration, run these SDD-specific signal collectors in order:

1. `sdd validate-invariants` — any failing invariant is an immediate deepening candidate (the invariant enforcement is missing at the code level).
2. Read `.sdd/norms/norm_catalog.yaml`. For each norm with `enforcement: hard`, check whether a corresponding guard exists in `src/sdd/guards/` or `src/sdd/commands/`. A hard norm with no code-level guard is a deepening candidate.
3. `sdd query-events --type ErrorEvent` — clusters of errors in one module indicate a shallow or brittle interface (real evidence, not inference).

Then use the Agent tool with `subagent_type=Explore` to walk the codebase. Don't follow rigid heuristics — explore organically and note where you experience friction:

- Where does understanding one concept require bouncing between many small modules?
- Where are modules **shallow** — interface nearly as complex as the implementation?
- Where have pure functions been extracted just for testability, but the real bugs hide in how they're called (no **locality**)?
- Where do tightly-coupled modules leak across their seams?
- Which parts of the codebase are untested, or hard to test through their current interface?

Apply the **deletion test** to anything you suspect is shallow: would deleting it concentrate complexity, or just move it? A "yes, concentrates" is the signal you want.

### 2. Present candidates

Present a numbered list of deepening opportunities. For each candidate:

- **Files** — which files/modules are involved
- **Invariant ref** _(optional)_ — `I-XXX` or `NORM-XXX` if found via `sdd validate-invariants` or norm analysis
- **Problem** — why the current architecture is causing friction
- **Solution** — plain English description of what would change
- **Benefits** — explained in terms of locality and leverage, and also in how tests would improve

**Use vocabulary from `.sdd/specs/SDD_Spec_v1.md` and `.sdd/config/glossary.yaml` for the domain, and [LANGUAGE.md](LANGUAGE.md) vocabulary for the architecture.**

**Norm conflicts**: if a candidate contradicts an existing norm in `.sdd/norms/norm_catalog.yaml`, only surface it when the friction is real enough to warrant revisiting the norm. Mark it clearly (e.g. _"contradicts NORM-SCOPE-003 — but worth reopening because…"_). Don't list every theoretical refactor a norm forbids.

Do NOT propose interfaces yet. Ask the user: "Which of these would you like to explore?"

### 3. Grilling loop

Once the user picks a candidate, drop into a grilling conversation. Walk the design tree with them — constraints, dependencies, the shape of the deepened module, what sits behind the seam, what tests survive.

Side effects happen inline as decisions crystallize:

- **Naming a deepened module after a concept not in `.sdd/config/glossary.yaml`?** Add the term to `.sdd/config/glossary.yaml` directly.
- **Sharpening a fuzzy term during the conversation?** Update `.sdd/config/glossary.yaml` right there.
- **User rejects the candidate with a load-bearing reason?** Offer to create a draft norm in `.sdd/specs_draft/` (free-form, marked "for DRAFT_SPEC session"), framed as: _"Want me to draft a norm so future architecture reviews don't re-suggest this?"_ Only offer when the reason would prevent future re-suggestion — skip ephemeral reasons ("not worth it right now") and self-evident ones. Do NOT write to `.sdd/norms/norm_catalog.yaml` directly (enforcement layer, requires DRAFT_SPEC session).
- **Want to explore alternative interfaces for the deepened module?** See [INTERFACE-DESIGN.md](INTERFACE-DESIGN.md).

At the end of the grilling loop, propose one of two next steps (do not create artifacts yourself):
- Significant architectural decision → "Run a `DRAFT_SPEC vN` session to formalize this"
- Small refactor within current phase → "Run an `IMPLEMENT T-NNN` session for the current phase"
