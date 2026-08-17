# Confidence And Evidence

Lineage is useful only when a reviewer can see why an edge exists.

| Confidence | Meaning |
|---|---|
| `high` | Direct Core CTL relation or explicit Qlik statement |
| `medium` | Deterministic transitive relation through a known QVD producer |
| `low` | Name or field inference requiring review |
| `unresolved` | The required source or relationship is missing |

Every edge should include the input file, JSON path, and, for script-derived
edges, the source line range. The analyzer must preserve multiple evidence
items when the same edge is observed in more than one artifact.

Never upgrade an edge to `high` because two names happen to match.
