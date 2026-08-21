# Quickstart

## 1. Prepare Inputs

Collect the Core CTL JSON export for the Qlik apps in scope. Include load
scripts, QVD references, dashboard/sheet/chart metadata, and connection
metadata whenever Core CTL can export them.

If the export does not identify Redshift and Snowflake explicitly, create a
source map:

```json
{
  "connections": [
    {"match": "redshift-prod", "source_system": "redshift"},
    {"match": "snowflake-analytics", "source_system": "snowflake"}
  ]
}
```

## 2. Analyze

```bash
python3 scripts/analyze.py analyze \
  --input <ctl-file-or-directory> \
  --source-map <source-map.json> \
  --out out/customer-lineage
```

The command is offline and read-only.

## 3. Add Redshift Catalog Metadata

To generate column-level Snowflake DDL, export a JSON snapshot with this
shape:

```json
{
  "columns": [
    {
      "table_schema": "analytics",
      "table_name": "orders",
      "column_name": "order_id",
      "data_type": "bigint",
      "is_nullable": "NO"
    }
  ]
}
```

Then rerun with `--redshift-catalog` and optionally `--target-config`.

## 4. Review Before Snowflake Work

Review these in order:

1. `unresolved-lineage.json` for missing or ambiguous paths.
2. `redshift-dashboard-impact.csv` for the migration scope.
3. `redshift-qvd-impact.csv` to distinguish raw replication from derived QVD recreation.
4. `snowflake-migration-manifest.json` for target names and strategies.
5. `snowflake-ddl.sql` for `REVIEW` and `UNSUPPORTED` mappings.

For cross-filtering, inspect `sigma-cross-filter-actions.json`. It contains the
chart `on-select` hosts, generated controls, target chart IDs, and clear-
selections button template. Map those neutral IDs to the final Sigma workbook
elements during workbook construction, then validate the behavior with actual
chart selections.

Do not execute generated DDL without reviewing the source catalog and QVD
transformations.
