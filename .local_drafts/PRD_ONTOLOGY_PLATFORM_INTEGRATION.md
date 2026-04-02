# PRD: Ontology-Driven Genie Spaces and Agent Knowledge Serving

**Author:** Mikhail Konchits
**Date:** 2026-03-24
**Status:** Draft
**Target:** Ontos v0.7.0+

---

## Problem Statement

Ontos builds rich ontologies — OWL/RDFS class hierarchies, typed entity relationships, domain-scoped semantic links, SPARQL-queryable knowledge graphs — but exposes this knowledge to the Databricks platform only as flat UC tags via the tag sync job. This creates three concrete losses:

1. **Relationships are invisible to downstream consumers.** Ontos knows that `orders.customer_id` references the `Customer` concept and that `Customer` has an `Address`, but Genie sees only `ontos_semantic_customer = "urn:..."`. It cannot reason about joins, hierarchies, or cross-table semantics.

2. **SPARQL stays locked inside the app.** The validated SPARQL endpoint (`POST /api/semantic-models/query`) is only accessible within the Ontos UI. No Databricks notebook, Genie Space, or AI agent can query the ontology programmatically.

3. **Terminology reconciliation doesn't flow to consumers.** Domain-scoped semantic links distinguish "Customer (Sales)" from "Customer (Finance)", but this disambiguation is flattened into a single tag value. Genie and agents have no way to resolve homonyms based on user context.

The result: Ontos is an excellent governance studio, but its full semantic value is not accessible to the business applications that need it most — Genie Spaces, AI agents, and analytical notebooks.

### Context: Industry Direction

The [ontology problem statement](https://docs.google.com/document/d/1h61mJmu0P7FvKQYPdNF_BJ3mR8Z1H_hdxR9d6J2_39s) articulates why structured semantics matter for agents:

- Free-text instructions cannot capture complex relationships and conceptual hierarchies
- Synonyms and homonyms need explicit resolution, not implicit LLM guessing
- Terminology must be consistent across multiple Genie Spaces
- Metric Views capture formulas but not how measures relate to each other or fit within a hierarchy
- Existing ontology vendors (Palantir, Microsoft) have opted for lock-in rather than open standards

Ontos already uses open standards (OWL, RDFS, SKOS, SHACL). The missing piece is exposing this knowledge to the platform.

---

## Solution

Add two capabilities to Ontos:

### Capability 1: Ontology-Driven Genie Space Generation

Auto-generate fully configured Genie Spaces from ontologies and data products, with instructions, join specifications, business terms, and example queries — all derived from the governed knowledge graph.

### Capability 2: Agent Knowledge Serving via MCP

Expose ontology knowledge as MCP tools that AI agents (Genie, custom agents, notebooks) can call at runtime to disambiguate terms, discover relationships, and resolve semantics.

---

## What Already Exists

Significant infrastructure is already built:

| Component | Status | Location |
|-----------|--------|----------|
| Genie Space DB model + repository | Complete | `db_models/genie_spaces.py`, `repositories/genie_spaces_repository.py` |
| Genie API client (`create_genie_space()`) | Complete | `common/genie_client.py` |
| Dataset collection from output ports | Complete | `genie_client.collect_datasets_from_products()` |
| Metadata formatting for Genie | Basic | `genie_client.format_metadata_for_genie()` |
| MCP server (JSON-RPC 2.0) | Complete | `routes/mcp_routes.py` |
| Tool framework + registry | Complete | `tools/base.py`, `tools/registry.py` |
| 12+ MCP tools registered | Complete | `tools/*.py` (search, products, contracts, domains, analytics) |
| SPARQL query engine | Complete | `controller/semantic_models_manager.py` |
| Ontology schema extraction | Complete | `controller/ontology_schema_manager.py` |
| Entity-to-UC mapping (AssetDb.location) | Complete | `db_models/assets.py` |
| Semantic links (entity ↔ IRI) | Complete | `db_models/semantic_links.py` |
| Entity relationships (typed, directional) | Complete | `db_models/entity_relationships.py` |

**What's NOT built:** The bridge between these components — translating ontology knowledge into Genie configs and agent-callable tools.

---

## User Stories

### Capability 1: Genie Space Generation

1. As a **Data Product Owner**, I want to create a Genie Space from my data product with one click, so that business users can immediately ask questions about my product's data with rich semantic context.

2. As a **Data Governance Lead**, I want to generate Genie Spaces for an entire domain, so that all tables within the domain are queryable with consistent terminology, join logic, and business context.

3. As a **Data Governance Lead**, I want Genie Space instructions to include ontology-derived business terms with synonyms, so that business users can ask questions using their own vocabulary and get correct answers.

4. As a **Data Governance Lead**, I want Genie Space join specifications to be derived from entity relationships in the ontology, so that Genie generates correct multi-table queries without manual join configuration.

5. As a **Data Governance Lead**, I want to regenerate all Genie Spaces in a domain when the ontology changes, so that terminology updates propagate automatically to all consuming spaces.

6. As a **Data Product Owner**, I want Genie Space instructions to include disambiguation rules for homonyms, so that when "Customer" appears in multiple domains, Genie uses the definition scoped to this space's domain.

### Capability 2: Agent Knowledge Serving

7. As an **AI Agent Developer**, I want to call an MCP tool to resolve an ambiguous business term in a specific domain context, so that my agent can disambiguate "revenue" into "Sales.Revenue" or "Finance.Revenue" based on the user's role.

8. As an **AI Agent Developer**, I want to call an MCP tool to get related tables and join paths for a concept, so that my agent can construct multi-table queries without hardcoded join logic.

9. As an **AI Agent Developer**, I want to call an MCP tool to get all business terms with definitions for a domain, so that my agent can understand the vocabulary of the domain it's operating in.

10. As an **AI Agent Developer**, I want to call an MCP tool to get metric context (definition, formula, related concepts), so that my agent can explain what a metric means and how it was calculated.

11. As an **AI Agent Developer**, I want to call an MCP tool to disambiguate a term and get all possible meanings across domains, so that my agent can ask the user clarifying questions when a term is ambiguous.

12. As a **Data Analyst**, I want to query ontology knowledge from a Databricks notebook via a serving endpoint, so that I can programmatically access business definitions and relationships without opening the Ontos UI.

---

## Implementation Plan

### Phase 1: Genie Space from Products (Quick Win)

**Goal:** Wire the existing `genie_client` into an API route. No ontology enrichment yet — just product metadata.

**What to build:**
- `POST /api/data-products/{id}/create-genie-space` route
- `POST /api/domains/{id}/create-genie-space` route
- Status polling: `GET /api/genie-spaces/{space_id}/status`
- Uses existing `collect_datasets_from_products()` and `format_metadata_for_genie()`

**Files to modify:**
- `src/backend/src/routes/data_product_routes.py` — add route
- `src/backend/src/routes/data_domain_routes.py` — add route (optional)
- `src/backend/src/routes/genie_space_routes.py` — new file for status/list

**Acceptance criteria:**
- [ ] `POST /api/data-products/{id}/create-genie-space` creates a Genie Space with correct tables
- [ ] GenieSpaceDb record created with space_id, URL, status
- [ ] Instructions include product name, description, and output port metadata
- [ ] Error returns clear message if product has no output ports

**User stories addressed:** 1

**Estimated effort:** 1 day

---

### Phase 2: Ontology-Enriched Instructions (Core Value)

**Goal:** Enrich Genie Space instructions with ontology-derived context: business terms, synonyms, relationships, disambiguation rules.

**What to build:**

**Module A — Instruction Generator** (`src/backend/src/common/genie_instruction_generator.py`, ~200 lines)

```
Input:  domain_id or product_ids + db session
Output: Structured instruction text (max 5000 chars)

Assembles from:
  1. Domain description (DataDomain)
  2. Business terms with synonyms (semantic links → ontology altLabel/prefLabel)
  3. Concept hierarchy summary (SKOS broader/narrower via SPARQL)
  4. Table descriptions with semantic context (Assets + semantic links)
  5. Homonym disambiguation rules (domain-scoped concept definitions)
  6. Metric definitions (from contract quality rules + ontology annotations)
```

Prioritization logic for the 5000-char limit:
- Always include: table descriptions, join guidance, disambiguation rules
- Include if space: business terms with synonyms, concept hierarchy
- Truncate last: metric formulas, extended descriptions

**Module B — Join Spec Generator** (`src/backend/src/common/genie_join_generator.py`, ~150 lines)

```
Input:  List of UC table FQNs
Output: List of {left_table, right_table, join_type, join_condition, description}

Logic:
  1. For each table pair, query EntityRelationshipDb
  2. If relationship exists → derive join condition from relationship metadata
  3. If semantic links exist for both → query ontology ObjectProperty for inferred join
  4. Validate join against UC (optional, if workspace client available)
```

**Files to modify:**
- `src/backend/src/common/genie_client.py` — integrate instruction + join generators
- `src/backend/src/common/genie_instruction_generator.py` — new file
- `src/backend/src/common/genie_join_generator.py` — new file

**Acceptance criteria:**
- [ ] Instructions include business terms with synonyms derived from ontology
- [ ] Instructions include disambiguation rules for terms appearing in multiple domains
- [ ] Join specifications generated from EntityRelationshipDb relationships
- [ ] Join specifications generated from ontology ObjectProperty where direct relationships don't exist
- [ ] Instruction text stays within 5000-char Genie limit with graceful prioritization
- [ ] Regeneration endpoint updates existing Genie Space when ontology changes

**User stories addressed:** 2, 3, 4, 5, 6

**Estimated effort:** 1 week

---

### Phase 3: Agent Knowledge MCP Tools (Agent-Ready)

**Goal:** Register ontology query tools in the MCP server so agents can resolve semantics at runtime.

**What to build:**

5 new MCP tools following the existing `BaseTool` pattern:

**Tool 1: `ResolveConcept`**
```
Input:  {term: "customer", domain: "Sales"}  (domain optional)
Output: {
  matches: [
    {iri: "urn:...", label: "Sales Customer", domain: "Sales",
     definition: "...", synonyms: ["client", "buyer"], confidence: 0.95},
    {iri: "urn:...", label: "Finance Customer", domain: "Finance",
     definition: "...", synonyms: ["account"], confidence: 0.7}
  ]
}
```

**Tool 2: `GetRelatedTables`**
```
Input:  {concept: "CustomerOrder"} or {table: "catalog.schema.orders"}
Output: {
  tables: [
    {fqn: "catalog.schema.customers", relationship: "hasCustomer",
     join_condition: "orders.customer_id = customers.id", direction: "outgoing"}
  ]
}
```

**Tool 3: `GetBusinessTerms`**
```
Input:  {domain: "Sales", limit: 50}
Output: {
  terms: [
    {term: "ARR", definition: "Annual Recurring Revenue...",
     synonyms: ["annual revenue"], related_metrics: ["MRR"],
     domain: "Sales"}
  ]
}
```

**Tool 4: `GetMetricContext`**
```
Input:  {metric: "ARR", domain: "Sales"}
Output: {
  definition: "Annual Recurring Revenue",
  formula: "SUM(monthly_revenue) * 12",
  related_concepts: ["Revenue", "Subscription", "Contract"],
  domain: "Sales",
  disambiguation: "Note: Finance defines ARR as 'recognized recurring revenue' — different basis."
}
```

**Tool 5: `DisambiguateTerm`**
```
Input:  {term: "customer"}
Output: {
  ambiguous: true,
  meanings: [
    {domain: "Sales", definition: "A company or individual who has purchased...", table_examples: ["sales.customers"]},
    {domain: "Support", definition: "An entity with an open support case...", table_examples: ["support.tickets"]},
    {domain: "Finance", definition: "An account with active billing...", table_examples: ["finance.accounts"]}
  ],
  suggested_clarification: "Which department's definition of 'customer' do you mean?"
}
```

**Files to create:**
- `src/backend/src/tools/ontology.py` — all 5 tools
- Add to `src/backend/src/tools/registry.py` — register in `create_default_registry()`

**Supporting addition** (in `SemanticModelsManager`):
- `resolve_term(term, domain=None) -> List[ConceptMatch]` — SPARQL-backed term resolution

**Acceptance criteria:**
- [ ] All 5 tools registered in MCP ToolRegistry and discoverable via `/api/mcp`
- [ ] `ResolveConcept` returns domain-scoped matches ranked by relevance
- [ ] `GetRelatedTables` returns join paths derived from entity relationships + ontology
- [ ] `GetBusinessTerms` returns terms with synonyms from SKOS altLabel
- [ ] `GetMetricContext` returns definition + related concepts
- [ ] `DisambiguateTerm` identifies ambiguous terms and returns all domain-scoped meanings
- [ ] All tools handle missing data gracefully (empty results, not errors)

**User stories addressed:** 7, 8, 9, 10, 11

**Estimated effort:** 1 week

---

### Phase 4: Serving Endpoint (Optional, Platform Integration)

**Goal:** Wrap MCP tools as a Databricks Model Serving endpoint for consumption outside the Ontos app.

**What to build:**
- MLflow PyFunc model that proxies to Ontos API
- Deployment config for Model Serving
- Authentication via Databricks tokens

**Files to create:**
- `src/backend/src/serving/ontology_endpoint.py` — PyFunc model
- `src/backend/src/serving/deploy.py` — deployment script

**Acceptance criteria:**
- [ ] Serving endpoint responds to structured queries (resolve term, get relationships)
- [ ] Accessible from any Databricks notebook via `requests.post()`
- [ ] Authentication uses Databricks workspace tokens
- [ ] Response format matches MCP tool outputs for consistency

**User stories addressed:** 12

**Estimated effort:** 2-3 days

---

## Architecture

### Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│  ONTOS (Governance Studio)                                          │
│                                                                      │
│  Ontology (OWL/RDFS)  →  Knowledge Graph (RDFLib)                   │
│  Semantic Links        →  Entity ↔ IRI mappings                     │
│  Entity Relationships  →  Typed connections between assets           │
│  Data Products         →  Output ports → UC table FQNs               │
│  Business Glossary*    →  Domain-scoped terms with synonyms          │
│                                                                      │
│  * Glossary backend not yet implemented; semantic links used interim │
└──────────┬──────────────────────────────────┬────────────────────────┘
           │                                   │
           │ Capability 1                      │ Capability 2
           │ (design time)                     │ (runtime)
           ▼                                   ▼
┌─────────────────────────┐     ┌──────────────────────────────────┐
│ Genie Space Generator   │     │ MCP Knowledge Tools              │
│                          │     │                                   │
│ Instruction Generator    │     │ ResolveConcept                   │
│   → business terms       │     │ GetRelatedTables                 │
│   → disambiguation       │     │ GetBusinessTerms                 │
│   → semantic context     │     │ GetMetricContext                 │
│                          │     │ DisambiguateTerm                 │
│ Join Spec Generator      │     │                                   │
│   → relationship-based   │     │ ┌─────────────────────────────┐  │
│   → ontology-inferred    │     │ │ Optional: Serving Endpoint  │  │
│                          │     │ │ (MLflow PyFunc wrapper)     │  │
│ Genie API Client         │     │ └─────────────────────────────┘  │
│   → create/update space  │     │                                   │
└──────────┬──────────────┘     └──────────┬───────────────────────┘
           │                                │
           ▼                                ▼
┌─────────────────────────┐     ┌──────────────────────────────────┐
│ Genie Spaces            │     │ AI Agents / Notebooks            │
│                          │     │                                   │
│ Rich instructions from   │     │ Query semantics at runtime:     │
│ ontology, not guesswork  │     │ "What does X mean?"             │
│                          │     │ "How do A and B join?"          │
│ Join specs from          │     │ "Disambiguate Y"                │
│ relationships, not LLM   │     │                                   │
└─────────────────────────┘     └──────────────────────────────────┘
```

### What's NOT in Scope

- **Glossary backend implementation** — Semantic links + ontology labels serve as interim. A full glossary backend with synonym management is a separate PRD.
- **Genie instruction auto-refresh** — Regeneration is manual (or triggered via workflow). Automatic push-on-ontology-change is deferred.
- **User Attribute integration** — Using ABAC User Attributes for automatic domain scoping is deferred until the platform supports it in the agent context.
- **Cross-space routing** — Routing questions to the right Genie Space based on ontology context is a Genie platform feature, not an Ontos feature.

---

## Testing Strategy

### Phase 1 Tests
- Route creates Genie Space with correct datasets from output ports
- Error handling for products without output ports
- GenieSpaceDb record created correctly

### Phase 2 Tests
- Instruction generator includes business terms from semantic links
- Instruction generator includes disambiguation rules for multi-domain terms
- Join spec generator derives joins from EntityRelationshipDb
- Join spec generator derives joins from ontology ObjectProperties
- Instruction text respects 5000-char limit
- Empty ontology produces valid (minimal) instructions

### Phase 3 Tests
- Each MCP tool registered and discoverable
- ResolveConcept returns correct matches for known terms
- ResolveConcept returns domain-filtered results when domain specified
- GetRelatedTables returns join paths from relationships
- DisambiguateTerm identifies terms with multiple domain meanings
- All tools return empty results (not errors) for unknown inputs

### Phase 4 Tests
- Serving endpoint responds to health check
- Serving endpoint returns correct results for each tool proxy
- Authentication rejects invalid tokens

---

## Dependencies

| Dependency | Status | Impact if Missing |
|-----------|--------|-------------------|
| Business Glossary backend | Not implemented | Use semantic links + ontology labels as interim; synonyms limited to SKOS altLabel |
| Genie Space API (create) | Available | Required for Phase 1 |
| MCP server | Implemented | Required for Phase 3 |
| Entity Relationships populated | Partially (via import + manual) | Join spec quality depends on relationship completeness |
| Semantic links assigned | Partially (via UI + tag sync) | Instruction quality depends on link coverage |

---

## Success Metrics

| Metric | Baseline (today) | Target |
|--------|------------------|--------|
| Time to create a domain-scoped Genie Space | 2-4 hours (manual) | <5 minutes (one click) |
| Join accuracy in generated Genie Spaces | 0% (no joins generated) | >80% of valid joins derived from ontology |
| Business term coverage in Genie instructions | 0% (flat tags only) | >90% of domain terms included with synonyms |
| Agent disambiguation capability | None | Resolve ambiguous terms to domain-scoped definitions |
| Ontology value accessible outside Ontos | Tags only (~10% of graph) | Full graph queryable via MCP tools (~90%) |

---

## Relationship to Other Initiatives

| Initiative | Relationship |
|-----------|-------------|
| **AutoGenie** (databricks-field-eng) | Complementary. AutoGenie generates Genie configs from PDFs; this PRD generates them from governed ontologies. Ontos could serve as a knowledge source for AutoGenie's `DomainKnowledgeExtractor` in a future integration. |
| **Issue #58** (RDFLib reasoner) | Enhances this PRD. Inferred triples (subclass closure, PII propagation) would make agent tools smarter — e.g., "all PII tables" includes inferred PII. |
| **Issue #59** (SHACL → DQX) | Same pattern. #59 pushes SHACL constraints to DQX jobs; this PRD pushes ontology knowledge to Genie Spaces and agents. Both are "ontology → platform artifact" bridges. |
| **Issue #43** (Ontology actions) | The action engine could trigger Genie Space regeneration when relevant ontology concepts change. |
| **UC Tag Sync** (existing) | Remains for lightweight metadata. This PRD adds the rich channel that tags can't provide. |

---

## Open Questions

1. **Genie instruction limit:** 5000 chars may be too small for rich ontologies with many domains. Should we split into multiple Genie Spaces per domain or compress instructions?

2. **Glossary interim:** Using semantic links + SKOS labels as a glossary substitute works but limits synonym management to ontology-level edits. Is this acceptable for v1?

3. **MCP tool granularity:** Should `ResolveConcept` and `DisambiguateTerm` be separate tools (clearer intent) or merged (fewer tools for agents to choose from)?

4. **Serving endpoint necessity:** If Genie natively supports MCP tool calling, the serving endpoint wrapper may be unnecessary. Monitor Genie's MCP roadmap.

---

**Version:** 0.1.0 (Draft)
**Last Updated:** 2026-03-24
