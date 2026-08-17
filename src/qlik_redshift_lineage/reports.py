"""Stable JSON, CSV, and Markdown outputs."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .graph import LineageGraph


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            normalized = {}
            for field in fields:
                value = row.get(field, "")
                normalized[field] = ", ".join(str(item) for item in value) if isinstance(value, list) else value
            writer.writerow(normalized)


def write_outputs(out: Path, graph: LineageGraph, summary: dict, manifest: dict, ddl_text: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "lineage.json").write_text(json.dumps(graph.as_dict(), indent=2) + "\n", encoding="utf-8")
    (out / "snowflake-migration-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (out / "snowflake-ddl.sql").write_text(ddl_text, encoding="utf-8")
    dashboards = summary.get("dashboards", [])
    _write_csv(out / "redshift-dashboard-impact.csv", dashboards, ["id", "name", "classification", "qvds", "warehouse_tables"])
    qvds = summary.get("qvds", [])
    _write_csv(out / "redshift-qvd-impact.csv", qvds, ["id", "name", "classification", "warehouse_tables"])
    _write_csv(out / "redshift-source-tables.csv", summary.get("source_tables", []), ["id", "name", "source_system"])
    mapping_rows = [
        {
            "source_schema": table.get("source_schema", ""),
            "source_table": table.get("source_table", ""),
            "column": column.get("column", ""),
            "source_type": column.get("source_type", ""),
            "target_type": column.get("target_type", ""),
            "status": column.get("status", ""),
        }
        for table in manifest.get("tables", [])
        for column in table.get("columns", [])
    ]
    _write_csv(out / "snowflake-type-mapping.csv", mapping_rows, ["source_schema", "source_table", "column", "source_type", "target_type", "status"])
    (out / "unresolved-lineage.json").write_text(json.dumps(summary.get("unresolved", []), indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Qlik Redshift Lineage Report",
        "",
        "This report is read-only analysis of the supplied Core CTL/Qlik metadata.",
        "",
        "## Summary",
        f"- Apps represented: {len({node.get('app_id', node.get('id')) for node in graph.nodes.values() if node.get('type') == 'app'})}",
        f"- Dashboards: {len(dashboards)}",
        f"- QVDs: {len(qvds)}",
        f"- Warehouse tables: {len(summary.get('source_tables', []))}",
        f"- Unresolved items: {len(summary.get('unresolved', []))}",
        "",
        "## Dashboard Impact",
        "",
        "| Dashboard | Classification | QVDs | Warehouse tables |",
        "|---|---|---|---|",
    ]
    for item in dashboards:
        lines.append(f"| {item.get('name', '')} | {item.get('classification', '')} | {', '.join(item.get('qvds', []))} | {', '.join(item.get('warehouse_tables', []))} |")
    lines.extend(["", "## Review Items", ""])
    if summary.get("unresolved"):
        for item in summary["unresolved"]:
            lines.append(f"- `{item.get('kind', 'review')}`: {json.dumps(item, sort_keys=True)}")
    else:
        lines.append("- None.")
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
