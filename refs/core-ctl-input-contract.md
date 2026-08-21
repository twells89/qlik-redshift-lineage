# Core CTL Input Contract

The first release accepts a Core CTL JSON file or a directory of JSON files.
The adapter is tolerant of common aliases, but lineage is only created from
explicit metadata or parseable Qlik load-script statements.

## Canonical Shape

```json
{
  "apps": [
    {
      "id": "app-orders",
      "name": "Orders",
      "loadScript": "LIB CONNECT TO 'redshift-prod'; ...",
      "connections": [
        {
          "id": "redshift-prod",
          "name": "redshift-prod",
          "source_system": "redshift"
        }
      ],
      "qvds": [
        {"name": "orders.qvd", "path": "lib://QVD/orders.qvd"}
      ],
      "dashboards": [
        {
          "id": "orders-dashboard",
          "name": "Orders Dashboard",
          "sheets": [
            {
              "id": "overview",
              "name": "Overview",
              "charts": [
                {
                  "id": "revenue",
                  "name": "Revenue",
                  "dimensions": ["CUSTOMER_ID"],
                  "measures": ["NET_REVENUE"],
                  "selectionEnabled": true,
                  "alternateState": ""
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

## Supported Aliases

The adapter recognizes common alternatives such as `applications` for `apps`,
`load_script` or `script` for `loadScript`, `visuals` or `objects` for
`charts`, `dataConnections` for `connections`, and `qvdFiles` for `qvds`.

## Evidence

Every Core CTL-derived edge stores the originating file and JSON path. A load
script edge additionally stores line numbers. When an export has no app-like
object, analysis stops with a contract error instead of emitting an empty
lineage report.

## Customer Adapter Work

Core CTL schemas vary by deployment. When a customer provides a redacted
export, add a fixture and a narrow adapter test before expanding aliases.
Never add a recursive heuristic that labels every string ending in `.qvd` as a
producer or every string containing `redshift` as a source system.
