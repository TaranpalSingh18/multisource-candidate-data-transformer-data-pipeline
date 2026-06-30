# Multi-Source Candidate Data Transformer — System Design & Build Plan

Stack: FastAPI (Python), React, PostgreSQL, Groq (LLM extraction/normalization). Target: ship a system that reads like it was built by someone who has shipped data-merge pipelines in production and has the scars to prove it.

---

## 1. Architecture overview

### 1.1 Why this shape

The core insight is testing: **the canonical record and the output the caller wants are different concerns**. If you let the output schema leak into your merge logic, every new consumer forces you to touch ingestion code. So the system is built as three decoupled layers:

1. **Ingestion/Extraction layer** — per-source adapters that turn arbitrary input (CSV, JSON, API, PDF, free text) into a common `FieldObservation` shape: `{candidate_ref, field_path, value, source_type, source_id, method, raw_confidence, extracted_at}`. Nothing here knows about merging.
2. **Resolution & Canonicalization layer** — groups observations by candidate identity, resolves conflicts field-by-field, computes confidence, and writes one canonical `CandidateProfile` row to Postgres. Nothing here knows about the caller's desired output shape.
3. **Projection layer** — takes a canonical profile + a runtime config and produces caller-shaped, schema-validated JSON. Nothing here touches source data or merge logic; it only reads the canonical record and provenance.

This separation is the single design decision everything else hangs off. It's also why Postgres (not just files) makes sense here: the canonical layer is genuinely something you want queryable, re-projectable, and re-computable without re-running extraction (extraction — especially LLM calls — is the expensive, slow, non-deterministic-ish part you want to cache and not redo every time someone changes a config).

### 1.2 Pipeline

```
detect source type
   -> extract (per-source adapter -> FieldObservation[])
   -> normalize (per-field normalizers: phone/date/country/skill)
   -> identity resolution (blocking + scoring -> candidate clusters)
   -> merge / conflict resolution (per-field winner + provenance)
   -> confidence scoring (per-field + overall)
   -> persist canonical CandidateProfile (Postgres)
   -> project (config-driven, on read) -> validate -> return JSON
```

Extraction and normalization happen once per source per candidate and are cached (raw extraction stored in `raw_observations` table). Identity resolution, merge, and confidence are *recomputable* — if you add a new source for a candidate later, you don't re-extract everything, you just re-run resolution+merge for that cluster. Projection is fully on-read and stateless — config changes never require a backend redeploy or data rewrite.

### 1.3 Why Groq/LLM is scoped narrowly

LLMs are used **only** where structure genuinely doesn't exist: resume prose, recruiter free-text notes, and as a fallback normalizer for messy skill/title strings. They are never used for: CSV parsing, JSON field mapping (deterministic key-mapping table instead — LLMs are nondeterministic and this assignment explicitly grades determinism), phone/date normalization (regex/libphonenumber — deterministic, no reason to pay LLM latency/cost for a solved problem), or merge/conflict decisions (an explicit, explainable scoring function — provenance must be a fact, not a model's guess).

Every LLM call is constrained: extraction prompts force "only return values that literally appear in the text, else null" + Groq's JSON mode / tool-calling forces schema-shaped output + a post-hoc validator rejects/down-confidences any extracted value that doesn't fuzzy-match a substring of the source text. This directly satisfies "robust — unknown values become null, never invented." LLM-extracted fields get a capped max confidence (e.g. 0.75) versus structured-source fields (which can hit 0.95+), because exact-source data is categorically more trustworthy than an inference — this is itself a design decision worth stating explicitly in the one-pager.

---

## 2. Canonical schema & normalization choices

Using the schema given in the doc essentially as-is (it's well-formed), with these concrete normalization rules:

- **Phones**: E.164 via `phonenumbers` (Google's libphonenumber port). Region-guessing for numbers without a country code uses the candidate's resolved location, falling back to `None` (unparseable numbers are kept raw in provenance but excluded from the normalized `phones[]` array — never silently coerced into a wrong-country number).
- **Dates**: `YYYY-MM` as specified. Free-text dates ("Jan 2022", "since 2021", "present") parsed via `dateutil` + light heuristics; "present"/"current" maps to `end: null` with a `current: true` flag added to the experience entry (schema extension, documented).
- **Country**: ISO 3166-1 alpha-2 via `pycountry` fuzzy lookup against free-text city/region/country strings; unresolvable locations keep raw string in provenance, canonical `country` is `null`.
- **Skills**: canonicalized against a maintained skill taxonomy (start with a static curated list — e.g. ~2-3k common tech skills aliased, "ReactJS"/"react.js"/"React" → "React"). Unknown skills fall back to title-cased raw string rather than being dropped — never silently discard signal because it doesn't fit the taxonomy.
- **Names**: Unicode-normalized, whitespace-collapsed; no fuzzy alteration of the name itself (you don't want to be "clever" with someone's name).

---

## 3. Identity resolution & merge policy

### 3.1 Matching (which observations belong to the same candidate)

Blocking + scored matching, not naive exact-match, because the same person legitimately shows up with `john.smith@gmail.com` in the CSV and a GitHub profile with no email at all.

**Blocking keys** (cheap, generates candidate-pairs to compare): normalized email (exact), normalized phone (exact), normalized full name (exact, case/whitespace-insensitive).

**Scoring** for pairs that share at least one blocking key: weighted combination of email exact match (very high weight — near-certain identity signal), phone exact match (high weight), name similarity (Jaro-Winkler, moderate weight), and corroborating signal overlap (same company + overlapping skills — small weight, used only to break near-ties, never alone). A pair merges if score crosses a threshold; this threshold and the weights live in one constants file, not scattered through code, so it's auditable and tunable.

Within a single ingestion run, the `candidate_id` is the resolution engine's output (a UUID minted at first sight of a cluster); a `candidate_ref`-to-`candidate_id` mapping table persists so re-running ingestion is idempotent and stable across runs (this is what "deterministic" actually requires once entity resolution is in play — randomness can't leak into ID assignment).

### 3.2 Conflict resolution (which value wins per field)

A simple "most recent source wins" or "first source wins" is the wrong call here — it fails silently and isn't explainable. Instead, per field:

1. Collect all observations for that field across the cluster.
2. Drop ones the normalizer rejected (and record why, in provenance, with `confidence: 0`).
3. **Source-tier weighting**: each source type has a base trust tier (recruiter CSV/ATS > LinkedIn/GitHub structured fields > resume LLM-extraction > recruiter free-text-note LLM-extraction), reflecting how likely each is to be accurate and current.
4. **Agreement boost**: if two or more independent sources agree (after normalization) on the same value, confidence is boosted and that value wins outright — independent corroboration is the strongest signal available, stronger than any single source's tier.
5. If sources disagree and no corroboration exists, the highest-tier source wins, but confidence is capped lower (e.g. ≤0.6) and **all disagreeing values are retained in provenance**, not discarded. This is the literal implementation of "wrong-but-confident is worse than honestly-empty": a low-confidence single-source value is flagged as such rather than presented as settled fact, and downstream consumers can choose their own risk tolerance by filtering on `confidence`.
6. List-valued fields (emails, phones, skills) are **unioned**, not winner-take-all — confidence is per-element, recorded in `skills[].confidence` and per-element provenance, since there's no reason to discard a second valid email.

### 3.3 Overall confidence

`overall_confidence` is a weighted rollup over field-level confidences (required fields weighted higher than optional ones), not a flat average — a profile missing `years_experience` should score very differently from one with a shaky `headline`.

---

## 4. Runtime-configurable output / projection layer

Config schema follows the example in the doc almost exactly, generalized:

```json
{
  "fields": [
    { "path": "full_name", "type": "string", "required": true },
    { "path": "primary_email", "from": "emails[0]", "type": "string", "required": true },
    { "path": "phone", "from": "phones[0]", "type": "string", "normalize": "E164" },
    { "path": "skills", "from": "skills[].name", "type": "string[]", "normalize": "canonical" }
  ],
  "include_provenance": false,
  "include_confidence": true,
  "on_missing": "null"
}
```

**Implementation approach**: the canonical profile, once assembled, is a plain nested dict/Pydantic model. The projector walks `config.fields`, resolves each `from` (or `path` if `from` absent) against the canonical record using a tiny JSONPath-like resolver supporting dot-paths and `[]`/`[n]` array indexing — no need for a full JSONPath library, the config only needs a handful of operators, and a hand-rolled resolver is easier to make airtight and explainable than pulling in a general-purpose path engine.

For each field: resolve value → apply `normalize` if specified (re-running the same normalizer functions used at canonicalization time, so projection-time and merge-time normalization can never drift apart) → handle missing per `on_missing` (`null` writes `None`, `omit` drops the key entirely, `error` raises a 422 immediately, naming the offending field) → attach `confidence`/`provenance` sub-objects if toggled on.

**Validation**: a Pydantic model is generated dynamically from `config.fields` (types + `required`) and the projected output is validated against it before returning — this is the "validate against the requested schema" requirement satisfied literally, not just by convention. Unknown/invalid config (a `from` path with no resolvable canonical field, an unsupported `normalize` name) fails fast with a clear 400 at config-load time, before touching any candidate data.

This design means: new output shapes for new downstream products are a JSON config change, deployed independently of pipeline code — exactly the point of the exercise.

---

## 5. Tech stack (the "increase as needed" parts)

| Layer | Choice | Why |
|---|---|---|
| API | FastAPI | async, Pydantic-native (huge win since the whole projection layer is Pydantic-model generation), automatic OpenAPI docs for free |
| DB | PostgreSQL | JSONB for `raw_observations`/provenance (flexible, source data is genuinely heterogeneous) + relational tables for `candidates`, `field_values`, normal indexing/querying for "thousands of candidates" scale |
| ORM | SQLAlchemy 2.0 + Alembic | migrations matter even for a take-home — shows production instinct |
| LLM | Groq (Llama 3.3 70B or similar), JSON mode/tool calling | fast inference, structured output mode minimizes hallucination risk |
| Phone parsing | `phonenumbers` | the de facto correct library, don't hand-roll |
| Fuzzy matching | `rapidfuzz` | fast Jaro-Winkler/Levenshtein for name matching & dedup |
| Resume parsing | `pdfplumber` (PDF) / `python-docx` (DOCX) → raw text → Groq extraction | text extraction is deterministic, structuring the prose is the LLM's job |
| GitHub | GitHub REST API (unauthenticated or PAT) | public profile + repos + languages, deterministic, no LLM needed for this source at all (bio could optionally get a light LLM pass for headline extraction, but is not required) |
| LinkedIn | manual/sample JSON fixture | LinkedIn's API is locked down and scraping is ToS-hostile; for the assignment, model it as a structured input (a profile-shaped JSON), same as ATS — document this constraint explicitly in the one-pager as a "deliberately left out" item |
| Frontend | React + Vite + TypeScript, minimal | input form (upload files / paste config) + JSON viewer/diff for provenance — explicitly low priority per the doc, kept thin |
| Background processing | none needed at this scale (sync FastAPI endpoint), but ingestion is structured as a pure function pipeline so it could be lifted into a queue (Celery/RQ) later without rearchitecting — mention this as a scale note, don't build it |
| Testing | pytest | unit tests per normalizer + per merge-policy edge case + one golden-profile integration test |

---

## 6. Edge cases (the 3–5 the one-pager should name, plus what's intentionally cut)

**Handled:**
1. **Same person, no shared identifier** (CSV has email only, GitHub profile has neither email nor phone) — name-similarity scoring with corroborating signal (shared skill/company) as tie-breaker; if confidence is too low to merge, the system deliberately keeps them as **separate candidate clusters** rather than guessing — false-merge is worse than a missed merge, since a false merge corrupts a profile permanently while a missed merge just under-populates one.
2. **Conflicting current employer** (CSV says Company A, LinkedIn says Company B) — both retained in provenance, highest-tier/most-recent-dated source wins for the canonical field, confidence capped, never silently averaged or concatenated.
3. **Malformed/garbage source** (empty CSV, truncated JSON, unparseable PDF) — adapter wraps extraction in a try/except boundary per-source; a failing source produces zero observations and a logged warning, not a pipeline crash — the rest of the candidate's profile still builds from whatever sources succeeded.
4. **LLM hallucination/over-extraction** — extracted values are checked against the source text (substring/fuzzy presence check) before being accepted as observations; anything that fails the check is dropped, not down-weighted, since an invented fact has zero evidentiary value regardless of confidence math.
5. **Partial/fuzzy dates** in resumes ("Summer 2021", "2020 - present") — heuristic date parser handles common patterns and falls back to `null` for genuinely unparseable strings rather than guessing a month.

**Deliberately left out (state this honestly in the one-pager — it's a credibility signal, not a weakness):** real LinkedIn scraping/auth, async/queued processing for very large batches, a skill-taxonomy ML model (static curated list instead), UI polish beyond a functional input/output view, multi-language resume support.

---

## 7. Phased build plan

Each phase below is sized to be completable and demoable on its own, and ends with a working, runnable increment — never a half-built abstraction with nothing to show. Each has a ready-to-use prompt for an AI coding assistant (e.g. Claude Code) to execute that phase. Feed phases in order, in fresh-ish context, and review/correct before moving on — you own every line, so read the diffs.

### Phase 0 — Repo scaffold & data model
Set up the monorepo skeleton, Postgres schema/migrations, and the canonical Pydantic models. No business logic yet — this phase exists so every later phase has a stable foundation to write against.


### Phase 1 — Source adapters & deterministic normalizers
Build the extraction layer for at least one structured + one unstructured source, plus the deterministic normalizers (phone, date, country). This is the largest "correctness surface" phase, so it's split from merge logic deliberately.

### Phase 2 — Identity resolution & merge engine
The core "correctness" logic: clustering observations into candidates and resolving conflicts into a single canonical record with provenance and confidence.


### Phase 3 — Projection layer, config validation & API surface
The configurable-output requirement and the CLI/API surface to drive the whole pipeline end-to-end.


### Phase 4 — Minimal UI, sample data, README & demo polish
Lower priority per the doc — kept intentionally thin. Produces the actual submission artifacts.

---