# Agent Development Guide

## Purpose

This file is the implementation contract for AI-assisted and human development on this repository.

- Read [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) first for product scope, architecture narrative, and design rationale.
- Use this guide for coding constraints, subsystem boundaries, and guardrails.
- Keep all changes inside the approved linear pipeline (Intake → Router → PandasAI Multi-Table Agent → Formatter) and the semantic-first data layer.

## Architecture Constraints

- **Pipeline only** — New logic must fit Intake, Router, Agent, or Formatter. Do not add parallel analytics engines or alternate request paths.
- **Thin Router** — Route requests into the agent pipeline only. Do not perform business analytics, SQL generation, or dataset selection in Router.
- **Agent is the brain** — All dataset selection and analytics reasoning must live in the PandasAI Multi-Table Agent integration layer.
- **Formatter is presentation-only** — Shape agent output for Slack (formatting, truncation, user-facing errors). Do not re-query data or re-run agent reasoning in Formatter.
- **PostgreSQL as the primary data source** — Application data should originate from PostgreSQL and be exposed through semantic models.
- **Align with product scope** — Do not build BI dashboards, end-user SQL tools, or write-back/mutation paths (see [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) §2).

Approved flow: Slack → Intake → Router → PandasAI Multi-Table Agent → Formatter → Slack. PostgreSQL and semantic models feed the agent only.

## Semantic Layer Requirements

- **Location** — All semantic model definitions live under `semantic_models/`. These are first-class project assets and must be versioned with the repo.
- **Role** — Describe tables, columns, relationships, aliases, metadata, and derived metrics so the agent can interpret questions without users knowing physical schema names.
- **Consumption** — Load semantic models into the PandasAI agent configuration. Do not duplicate business definitions inline in application code.
- **Change order** — When exposing a new table or metric to users, update semantic models first (or in the same change), then wire agent and datasource configuration—not the reverse.
- **Derived metrics** — Define in the semantic layer where possible. Do not scatter metric formulas across Router, Formatter, or unrelated modules.
- **Naming** — Use business-facing names and aliases in models. Map to PostgreSQL identifiers in model configuration, not in Slack-facing copy.

## Approved Subsystems

| Subsystem | Responsibility | Must not |
|-----------|----------------|----------|
| **Intake** | Slack event/message ingestion, validation, request envelope | Analytics, SQL, semantic model loading |
| **Router** | Dispatch to the analytics handler | Dataset selection, LLM reasoning |
| **PandasAI Multi-Table Agent** | Dataset selection, multi-table analytics, agent execution | Slack formatting |
| **Formatter** | Agent output → Slack blocks or text | Data access, agent orchestration |
| **Semantic models (`semantic_models/`)** | Business layer over PostgreSQL | Runtime Slack I/O |
| **PostgreSQL access** | Connections and query execution for the agent | Business metric definitions |

**External (not application subsystems):** Slack API and PostgreSQL database. 

## Out-of-Scope Features

**Product (from [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)):**

- Custom business intelligence dashboards
- Manual SQL interfaces for end users
- Data modification or write-back operations

**Implementation (unless explicitly requested by the maintainer):**

- Separate **planner** subsystem
- Separate **data-selector** subsystem
- Dedicated memory or state-management subsystems beyond PandasAI's built-in capabilities
- **Workflow orchestration** frameworks (e.g. LangGraph-style supervisors, custom DAG runners) that wrap or replace the linear pipeline
- **RAG or vector stores** for schema or document retrieval instead of semantic models plus live PostgreSQL
- Duplicate agent stacks (e.g. a second LLM path for “routing” analytics)

If a feature appears to require any of the above, stop and confirm scope with the maintainer before implementing.

## Development Guidelines

- **PandasAI first** — Prefer built-in multi-table agent, connectors, and semantic-layer features before custom Python analytics wrappers.
- **Minimal abstractions** — Extend approved subsystems rather than introducing new top-level packages or orchestration layers.
- **Dependencies** — Add libraries only when PandasAI or the Slack/PostgreSQL stack cannot cover the need. Document the reason in the PR or commit message.
- **Secrets** — Use environment variables only (`.env` locally, keys documented in `.env.example`). Never commit credentials.
- **Errors** — Return clear, user-facing messages via Formatter; log technical detail server-side.
- **Idempotent handling** — Design Intake and Router so duplicate Slack deliveries do not cause harmful side effects (analytics is read-only).
- **When unsure** — Re-read [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) §3–§5 before adding a component.

## Testing Guidelines

- **Unit tests** — Formatter output shaping; semantic model loading and validation; small pure helpers.
- **Integration tests** — Intake → Router → Agent with mocked LLM/DB; Agent → Formatter using fixture semantic models under `semantic_models/`.
- **Contract tests** — Semantic model files parse and reference valid PostgreSQL relations (test database or MCP during development).
- **Mock at boundaries** — Do not test Slack API internals or PandasAI library internals directly.
- **Failure cases** — For each subsystem, include at least one non-happy path (missing table, agent error, empty result) once code exists. Avoid golden-path-only coverage.

## Documentation Guidelines

- **PROJECT_CONTEXT.md** — Product and architecture only. Do not add implementation detail or file-layout conventions there.
- **AGENTS.md** — Implementation rules and guardrails. Update when subsystem boundaries change.
- **README.md** — Human onboarding (setup, environment variables, local run) when populated.
- **semantic_models/** — Use brief comments or a local README per model or domain folder to explain metrics and relationships for contributors.
- **Code comments** — Reserve for non-obvious business rules or PostgreSQL quirks. Prefer clear naming in semantic models for business meaning.
