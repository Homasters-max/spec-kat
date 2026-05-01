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
  wiki ingest --pending --take 1
  → prints ContextPacket path (runtime/cache/<sha256>.json)

Stage 1 (LLM):
  Read ContextPacket from the printed path
  → analyse content_chunks, glossary_hints, related_pages
  → write runtime/tmp/extraction.json  (must conform to ExtractionResult schema)

  ExtractionResult schema:
    entities:            list[ExtractedEntity]
    relations:           list[Relation]
    conflicts:           list[ConflictNote]
    glossary_proposals:  list[GlossaryProposal]

  → user runs: wiki validate-extraction
    exit non-zero → STOP, fix extraction.json and retry

Stage 2 (LLM):
  Read ExtractionResult from runtime/tmp/extraction.json
  Read existing wiki pages referenced in entities/relations
  → for each page operation write a draft file:
      runtime/tmp/<page_id>.create.md   — new page (full content)
      runtime/tmp/<page_id>.diff.md     — incremental patch (unified diff)
      runtime/tmp/<page_id>.rewrite.md  — full replacement (YAML frontmatter with reason field)
  page_id must NOT contain dots

  → user runs: wiki apply-drafts
    conflict → STOP, resolve manually then retry

Post-action (CLI, run in order):
  wiki rebuild        ← regenerates derived/index.md + derived/graph.json
  wiki lint           ← exit 1 if broken links / orphans / duplicates
  git commit          ← commit raw file + wiki pages together
  wiki sync-glossary  ← interactive review of glossary_pending.yaml
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
  wiki promote <query_id>
  → saves context_snapshot to query_log so it can be re-ingested later via wiki-evolve
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
