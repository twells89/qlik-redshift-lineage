# Qlik Cross-Filtering To Sigma Actions

## What The QVD Can And Cannot Tell Us

A QVD contains persisted rows and fields. It does **not** contain dashboard
selection behavior. The action plan therefore combines three sources:

1. Qlik dashboard metadata identifies charts, dimensions, measures, selection
   settings, and alternate states.
2. Qlik load scripts identify logical tables and the fields they contain.
3. Shared fields between logical tables approximate Qlik's associative model.

The QVD is useful for tracing a chart back to its producer and Redshift source,
but it cannot prove that one chart filters another.

## Generated Sigma Pattern

For a selectable chart with a dimension, the analyzer emits:

```yaml
host_element: chart-revenue
trigger: on-select
effects:
  - effect: set-control-value
    control: qlik_filter_orders_dashboard_customer_id
    value:
      type: formula
      formula: "[Selection/CUSTOMER_ID]"
```

The generated control is dashboard-scoped and targets every chart whose Qlik
logical table is reachable through shared-field associations. The downstream
Sigma workbook builder must map the neutral chart IDs to its actual element IDs
and wire the control's filter targets to each element's source columns.

The action shape follows Sigma's verified `on-select` + `set-control-value`
pattern. The action manifest is intentionally not a complete workbook spec:
source element IDs, control source shapes, and Sigma page IDs are only known to
the workbook builder.

## Clear Selections

The plan emits a generated `Clear selections` button using a page-scoped
`clear-control` effect for each normalized sheet/page in the dashboard. This
approximates Qlik's global clear-selections behavior when the workbook builder
maps those neutral sheet IDs to Sigma page IDs. The button is not claimed to be
a source object from Core CTL.

## Confidence And Gaps

The default associative inference is `medium` confidence. It becomes a review
item when:

- The chart has no resolved logical table.
- The chart has no dimension.
- Selections are explicitly disabled.
- The chart uses an alternate state.
- No associated target chart can be resolved.
- Core CTL does not expose enough object metadata to distinguish dimensions
  from measures.

Qlik's selection toggle, multi-select accumulation, alternate states, set
analysis that ignores selections, and synthetic/unassociated fields require
runtime validation or additional source metadata. The generated plan should
not be presented as exact behavioral parity until those cases are tested in
Sigma.
