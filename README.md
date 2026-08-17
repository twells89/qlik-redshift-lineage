# Qlik Redshift Lineage

Read-only analysis for customers migrating Qlik applications whose QVDs may be
backed by Amazon Redshift. The tool identifies affected QVDs, dashboards,
sheets, charts, and source tables, then produces a Snowflake migration manifest
and type-mapping guidance.

It is intentionally separate from any Qlik-to-Sigma converter. It does not
connect to Qlik, Redshift, Snowflake, or Sigma and does not move data.

## Quick Start

```bash
python3 scripts/analyze.py analyze \
  --input fixtures/redshift-via-qvd/ctl.json \
  --source-map fixtures/redshift-via-qvd/source-map.json \
  --redshift-catalog fixtures/redshift-via-qvd/redshift-catalog.json \
  --target-config fixtures/redshift-via-qvd/target-config.json \
  --out out/redshift-via-qvd
```

Then inspect:

- `out/redshift-via-qvd/report.md`
- `out/redshift-via-qvd/redshift-dashboard-impact.csv`
- `out/redshift-via-qvd/redshift-qvd-impact.csv`
- `out/redshift-via-qvd/snowflake-migration-manifest.json`
- `out/redshift-via-qvd/snowflake-ddl.sql`
- `out/redshift-via-qvd/unresolved-lineage.json`

## Customer Workflow

```text
Core CTL export
      ↓
qlik-redshift-lineage
      ↓
Redshift/QVD/dashboard impact report
      ↓
Recreate required data in Snowflake
      ↓
Run the customer's Qlik-to-Sigma conversion process
```

The tool does not guess a source system from a table or QVD name. Supply an
explicit source map when Core CTL does not identify the database technology.

## Input Contract

See `refs/core-ctl-input-contract.md`. A redacted customer Core CTL export is
needed to add a deployment-specific adapter if its field names differ from the
tolerant aliases supported by the first release.

## Development

The implementation uses only the Python standard library:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/analyze.py analyze --input fixtures/redshift-via-qvd/ctl.json --out /tmp/qlik-lineage-smoke
```

## License

MIT. See `LICENSE`.
