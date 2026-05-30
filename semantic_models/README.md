# Semantic Models

Business-layer definitions over PostgreSQL for the Talk-to-Data Slackbot. These files describe what each table means, how columns map to business language, and how datasets connect—so the PandasAI v3 multi-table agent can answer natural-language questions without users knowing physical schema names.

Semantic models are consumed by the agent only (see [PROJECT_CONTEXT.md](../PROJECT_CONTEXT.md) and [AGENTS.md](../AGENTS.md)). They are versioned here at the repo root; loading and validation code lives in `talk_to_data_slackbot/pandas_ai/`.

## Current models

| File | Dataset | PostgreSQL table | Role |
|------|---------|------------------|------|
| [users.yaml](users.yaml) | `users` | `users` | Signups and acquisition |
| [subscriptions.yaml](subscriptions.yaml) | `subscriptions` | `subscriptions` | Subscription lifecycle |
| [sessions.yaml](sessions.yaml) | `sessions` | `sessions` | User engagement sessions |
| [payments.yaml](payments.yaml) | `payments` | `payments` | Revenue transactions |

Each file declares a `source` block (`type: postgres`, physical `table`, connection details) and is intended for PandasAI v3 semantic-layer registration.

## Naming conventions

- **One file per dataset**, placed directly under `semantic_models/` (no nested model directories).
- **Filename:** lowercase snake_case matching the dataset `name` and PostgreSQL table — e.g. `users.yaml` for `name: users` and `table: users`.
- **Dataset `name`:** singular or plural business noun, stable identifier used in `relationships` (`dataset:` references).
- **Column `name`:** match the PostgreSQL column name; use `alias` for business-facing terms users might say in Slack.
- **New tables:** add or update a YAML file here first, then wire agent and datasource configuration—not the reverse ([AGENTS.md](../AGENTS.md)).

## Model elements

### Table description

The top-level `description` explains what one row represents and which date or dimension fields drive common analyses. Keep business rules and semantics here—not in application code.

Example: `users` describes each row as a unique user, with `signup_date` as the primary date for signup trends.

### Column descriptions

Each entry under `columns` documents a physical or computed field:

- `name` — PostgreSQL column (or derived field name)
- `type` — logical type (`integer`, `string`, `datetime`, `float`, …)
- `description` — plain-language meaning for the agent

Optional flags such as `group_by: true` mark dimensions commonly used in breakdowns.

### Aliases

An `alias` gives a business term the agent should recognize when users ask questions in everyday language. Physical names stay in `name`; aliases appear in user-facing phrasing only inside the model.

| Dataset | Column | Alias |
|---------|--------|-------|
| users | `country` | `region` |
| users | `device_type` | `platform` |
| subscriptions | `plan` | `subscription_plan` |
| subscriptions | `status` | `subscription_status` |
| sessions | `activity_type` | `engagement_type` |
| payments | `amount_usd` | `revenue` |
| payments | `method` | `payment_method` |

### Relationships

The `relationships` block declares foreign keys between datasets so PandasAI can join across tables:

```yaml
relationships:
  - from: user_id
    to:
      dataset: users
      column: user_id
```

- `from` — column on **this** dataset
- `to.dataset` — target model `name` (filename stem without `.yaml`)
- `to.column` — join key on the target dataset

Define relationships on the **many** side of a link (child → parent).

### Derived fields

Derived columns add computed metrics in the semantic layer instead of scattering formulas in Router, Formatter, or other code. They use an `expression` (SQL-compatible) alongside `name`, `type`, and `description`:

| Dataset | Field | Expression (summary) |
|---------|-------|----------------------|
| subscriptions | `subscription_length_days` | Days from `start_date` to `end_date` (or today if still active) |
| sessions | `session_hours` | `duration_minutes / 60.0` |

Prefer defining reusable metrics here when possible ([AGENTS.md](../AGENTS.md)).

## Cross-table analytics

Relationships form a join path the multi-table agent uses for questions spanning datasets:

```
users ──< subscriptions ──< payments
  │
  └──< sessions
```

- **users → subscriptions** (`user_id`): tie signups to plans, status, and lifecycle dates.
- **users → sessions** (`user_id`): tie signups to engagement, duration, and activity type.
- **subscriptions → payments** (`subscription_id`): tie plans and subscription periods to revenue and payment method.

Example questions this graph supports:

- Revenue by signup region — join `payments` → `subscriptions` → `users`, group by `country` (alias `region`).
- Average session hours for active subscribers — join `sessions` → `users` → `subscriptions`, filter on subscription `status`.
- Subscription length by platform — join `subscriptions` → `users`, group by `device_type` (alias `platform`).

Without declared relationships, the agent cannot reliably select and join the right datasets for multi-table questions.

## Contributing

When adding or changing a model:

1. Edit the YAML under `semantic_models/` only.
2. Document business rules in the table `description`.
3. Add `relationships` for every foreign key used in cross-table analysis.
4. Put computed metrics in `expression` columns rather than application code.
5. Run semantic validation (once implemented in `pandas_ai/`) against the dev PostgreSQL schema before merging.
