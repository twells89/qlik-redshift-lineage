---
name: qlik-redshift-lineage
description: >-
  Analyze Core CTL Qlik JSON exports and load scripts to identify Redshift-backed
  QVDs, source tables, and affected dashboards, then produce a Snowflake migration
  manifest and Redshift-to-Snowflake mapping guidance. Read-only; does not modify
  Qlik, Redshift, Snowflake, or Sigma.
user-invocable: true
---

# Qlik Redshift Lineage

Use this skill before converting Qlik content when the customer has QVDs whose
upstream data may live in Redshift. It answers which QVDs and dashboards depend
on Redshift and what must be recreated in Snowflake.

This is a standalone repository. It has no runtime dependency on Sigma or the
`qlik-to-sigma` repository.

## Safety Contract

- Analysis is local and read-only.
- The tool never connects to Qlik, Redshift, or Snowflake.
- The tool never creates warehouse objects or moves data.
- Unknown source systems remain `unknown`; names alone do not prove Redshift.
- Missing QVD producers, ambiguous fields, unresolved variables, and unsupported
  SQL are reported as review items.
- Generated DDL is only a starting point and must be reviewed before execution.

## Inputs

The primary input is a Core CTL JSON file or export directory. The adapter
accepts the canonical shape described in `refs/core-ctl-input-contract.md` and
common aliases used by Qlik export tools. A redacted customer export is still
needed to add a precise Core CTL adapter when the deployment uses fields not
covered by the tolerant adapter.

Optional inputs:

- `--source-map`: explicit connection-name/ID patterns that classify Redshift
  and Snowflake connections.
- `--redshift-catalog`: an `information_schema.columns` snapshot. Required for
  column-level DDL; without it the tool emits a migration manifest only.
- `--target-config`: Snowflake database/schema defaults.

Cross-filter behavior is a separate output from warehouse lineage. Do not infer
it from QVD names or QVD rows alone. The analyzer uses chart dimensions,
selection metadata, Qlik load-script fields, and shared-field associations to
produce a Sigma action plan.

## Run

From the repository root:

```bash
python3 scripts/analyze.py analyze \
  --input fixtures/redshift-via-qvd/ctl.json \
  --source-map fixtures/redshift-via-qvd/source-map.json \
  --redshift-catalog fixtures/redshift-via-qvd/redshift-catalog.json \
  --target-config fixtures/redshift-via-qvd/target-config.json \
  --out out/redshift-via-qvd
```

Installed package form:

```bash
qlik-redshift-lineage analyze \
  --input <core-ctl-export> \
  --out <output-directory>
```

Use `--strict` in CI or a migration gate. It exits non-zero when unresolved
lineage exists; normal analysis still writes all outputs.

## Workflow

1. Validate and normalize Core CTL JSON into apps, dashboards, sheets, charts,
   fields, QVDs, connections, and load scripts.
2. Parse Qlik `LIB CONNECT TO`, `LOAD`, `SQL SELECT`, `RESIDENT`, and `STORE`
   statements with line-number evidence.
3. Build the transitive graph:
   `dashboard → sheet → chart → field → Qlik table → QVD → producer app →
   warehouse table`.
4. Classify dashboard impact as Redshift direct, Redshift via QVD, mixed,
   Snowflake direct, or unresolved.
5. Generate CSV, JSON, Markdown, a Snowflake migration manifest, and optional
   catalog-driven DDL.
6. Review every unresolved item and every `REVIEW` or `UNSUPPORTED` type
   mapping before creating Snowflake objects.

## Cross-Filter Actions

For every selectable chart dimension, the skill can emit a neutral Sigma action
manifest:

```text
chart selection → [Selection/<field>] → set-control-value → dashboard control → target charts
```

The manifest is a handoff artifact for the workbook-building process. It does
not call the Sigma API and does not claim that Qlik's multi-select toggling or
alternate-state semantics are automatically reproduced. Read
`refs/cross-filtering.md` before using the action output.

## Outputs

- `lineage.json`: canonical graph with nodes, edges, confidence, and evidence.
- `report.md`: customer-facing summary and review list.
- `redshift-dashboard-impact.csv`: dashboard and chart impact inventory.
- `redshift-qvd-impact.csv`: QVD producer/consumer and source inventory.
- `redshift-source-tables.csv`: classified warehouse tables.
- `snowflake-migration-manifest.json`: target table strategy and dependencies.
- `snowflake-type-mapping.csv`: column-level Redshift-to-Snowflake mappings and
  `AUTO`/`REVIEW`/`UNSUPPORTED` status.
- `snowflake-ddl.sql`: generated only for tables with catalog columns.
- `sigma-cross-filter-actions.json`: inferred Sigma `on-select` actions,
  dashboard-scoped controls, and a clear-selections button template.
- `cross-filter-impact.csv`: one row per inferred chart selection effect.
- `unresolved-lineage.json`: missing, ambiguous, or unsupported evidence.

## Handoff To Qlik Conversion

After the customer recreates the required Redshift data in Snowflake, use the
normal Qlik conversion process separately. The migration manifest preserves
the logical Qlik table, source table, QVD, and dashboard relationships needed
to configure that next step. This repository does not edit Sigma workbooks or
Qlik conversion inputs automatically.

## References

- `refs/core-ctl-input-contract.md`
- `refs/qvd-lineage-model.md`
- `refs/redshift-to-snowflake.md`
- `refs/confidence-and-evidence.md`
- `refs/cross-filtering.md`
