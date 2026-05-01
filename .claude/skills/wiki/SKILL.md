---
name: wiki
description: Personal knowledge base management — evolve, query, or curate wiki pages.
  Use when user wants to add knowledge, answer questions from the wiki, or curate pages.
---

# Wiki Skill

Choose one of three protocols based on the user's intent:

| Intent | Protocol |
|--------|----------|
| Add or process new knowledge from raw files | **wiki-evolve** |
| Answer a question from the wiki | **wiki-query** |
| Clean up, merge, or restructure existing pages | **wiki-curate** |

---

## wiki-evolve protocol

Process a pending raw file through the full ingest → extract → apply pipeline.

```
Stage 0 (CLI):
  wiki ingest --pending --take 1   # из очереди pending (стандартный путь)
  wiki ingest <path>               # конкретный файл (когда пользователь передаёт путь явно)
  → prints ContextPacket path (runtime/cache/<sha256>.json)

Stage 1 (LLM):
  Read ContextPacket from the printed path (use Read tool with the full path).
  Analyse content_chunks (actual text), glossary_hints (known terms),
  and related_pages (existing wiki pages ranked by relevance).

  IMPORTANT: ensure runtime/tmp/ exists before writing:
    mkdir -p <vault>/runtime/tmp/

  Write runtime/tmp/extraction.json conforming to ExtractionResult schema.

  Example extraction.json:
  {
    "entities": [
      {"term": "rag-pipeline",  "type": "pattern", "confidence": 0.9,  "in_glossary": false},
      {"term": "vector-store",  "type": "tool",    "confidence": 0.85, "in_glossary": true},
      {"term": "retrieval-augmented-generation", "type": "idea", "confidence": 0.95, "in_glossary": false}
    ],
    "relations": [
      {"from_term": "rag-pipeline", "to_term": "vector-store",                    "type": "uses"},
      {"from_term": "rag-pipeline", "to_term": "retrieval-augmented-generation",  "type": "implements"}
    ],
    "conflicts": [
      {"page": "embedding-search", "note": "source prefers cosine; page says dot-product"}
    ],
    "glossary_proposals": [
      {"term": "RAG", "suggested_page": "rag-pipeline", "type": "pattern",
       "reason": "acronym used 5× without definition"}
    ]
  }

  page_id naming rules (MANDATORY):
    kebab-case: lowercase letters, digits, hyphens only
    NO dots  NO spaces  NO underscores
    ✓ "rag-pipeline"   ✗ "RAG_Pipeline"   ✗ "rag.pipeline"

  type guide:
    "idea"    → abstract concept, principle, mental model  ("separation-of-concerns")
    "pattern" → repeatable solution / recipe               ("rag-pipeline", "circuit-breaker")
    "tool"    → concrete technology, library, software     ("postgres", "chroma", "fastapi")

  confidence: include entities ≥ 0.7; omit vague mentions below that
  in_glossary: true ONLY if term appears in glossary_hints from ContextPacket

  → user runs: wiki validate-extraction
    exit non-zero → STOP, fix extraction.json and retry

Stage 2 (LLM):
  Read ExtractionResult from runtime/tmp/extraction.json.
  For each entity choose operation:

  OPERATION SELECTION:
    create  → page does not exist   (wiki show <page_id> returns "not found")
    diff    → page exists + small addition + page size > 1000 chars
    rewrite → page exists + structural change OR page size ≤ 1000 chars

  .create.md FORMAT  (key MUST be "page_type", NOT "type"):
    ---
    page_type: pattern
    tags: [rag, retrieval, llm]
    ---
    # RAG Pipeline

    ## Summary
    One-paragraph description.

    ## How It Works
    Steps or mechanics, referencing [[other-page-id]] with wikilinks.

    ## When To Use
    Conditions that make this the right choice.

    ## Trade-offs
    Costs, limitations, gotchas.

    ## See Also
    - [[related-page-id]]

  .diff.md FORMAT:
    ---
    base_sha256: <run: sha256sum wiki/<type>/<page_id>.md | awk '{print $1}'>
    ---
    <unified diff in standard patch format>

  .rewrite.md FORMAT:
    ---
    reason: structural_change    # or: small_page
    ---
    <full new page content — same structure as .create.md body>

  WIKILINKS: [[page_id]] — no spaces, no extension.
  Each entity in ExtractionResult should appear in at least one wikilink.

  → user runs: wiki apply-drafts
    conflict → STOP, resolve manually then retry

Post-action (CLI, run in order):
  wiki rebuild                        ← regenerate derived/index.md + graph.json
  wiki lint                           ← exit 1 if broken links / orphans / duplicates
  git commit                          ← commit raw file + wiki pages together
  wiki sync-glossary                  ← interactive review of glossary_pending.yaml
  wiki mark-ingested <sha256>         ← mark file done; sha256 printed by wiki ingest
```

---

## wiki-query protocol

Answer a question using wiki content. **READ-ONLY** (I-WIKI-QUERY-1) — no wiki writes allowed.

```
Stage 0 (CLI):
  wiki search <terms>   → ranked list of top_k page IDs + scores
  wiki show <page_id>   → full page content
  (repeat wiki show for as many pages as needed)

Stage 1 (LLM):
  Synthesise answer from retrieved pages.
  Output must include:
    - answer:             direct response to the user's question
    - citations:          list of page_ids used
    - insights:           new connections or gaps noticed
    - promote_suggestion: query_id to promote if this query reveals reusable knowledge

Post-action (optional, user decision):
  If the query reveals reusable knowledge worth ingesting later:

  Step 1 — record in query_log (prints query_id):
    wiki log-query --query "<the user's original question>"

  Step 2 — optionally attach context snapshot:
    wiki log-query --query "<question>" --snapshot /path/to/context.json

  Step 3 — promote to ContextPacket for future wiki-evolve:
    wiki promote <query_id>

  Note: promote_suggestion in LLM output is a SIGNAL to run the above steps —
  not a query_id that already exists. Only wiki log-query writes to query_log.
```

---

## wiki-curate protocol

Identify and fix quality issues in the wiki (orphans, duplicates, structural problems).

```
Stage 0 (CLI):
  wiki lint             → prints orphans, broken links, duplicates
  wiki search <terms>   → find pages related to the curation target
  cat .wiki/state/query_log.jsonl   → review past queries for context (optional)

Stage 1 (LLM, dry-run):
  Analyse lint output + page contents
  → write runtime/tmp/curate_plan.md describing all planned operations
    Format: fenced list of operations with page_id, op (create/diff/rewrite), rationale
  → show curate_plan.md to user

  [HUMAN GATE] — user reviews curate_plan.md, approves or requests changes
  user runs: wiki curate-apply

Stage 2 (LLM, after curate-apply invokes apply_drafts):
  wiki curate-apply reads runtime/tmp/curate_plan.md
  → writes runtime/tmp/<page_id>.[op].md draft files
  → calls apply_drafts() internally
    conflict → STOP (I-WIKI-CONFLICT-1)

  → wiki apply-drafts exits 0
  → wiki rebuild

  git commit   ← user runs manually after reviewing changes
```
