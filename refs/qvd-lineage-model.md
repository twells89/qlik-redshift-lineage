# QVD Lineage Model

A QVD is a persisted Qlik data artifact, not necessarily a copy of one
warehouse table. It can contain renamed columns, joins, filters, calculated
fields, concatenated facts, or aggregates.

## Supported Paths

```text
Dashboard → Sheet → Chart → Field → Qlik table → QVD
QVD → Producer app → Qlik table → Redshift table
Qlik table → SQL SELECT → Redshift table
```

The analyzer follows these paths transitively. Multiple producers for one QVD
remain separate and are reported for review.

## Recreation Strategies

| Strategy | Use when |
|---|---|
| `replicate_raw_table` | The Qlik table directly selects one warehouse table with no derived logic |
| `recreate_derived_table` | The QVD contains joins, filters, calculated fields, or aggregation |
| `create_view` | The QVD logic can remain live and is inexpensive to recompute |
| `review_multiple_producers` | More than one app writes the same QVD |
| `review_missing_producer` | Consumers exist but no producer or source script is available |

The first release emits source evidence and a raw-table manifest. Derived-QVD
strategy detection is a planned extension and should not be inferred from a
single filename.
