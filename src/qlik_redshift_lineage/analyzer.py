"""Build the normalized graph and impact classifications."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .classification import classify
from .core_ctl import normalize_documents
from .graph import Evidence, LineageGraph
from .qlik_script import parse_script


def _safe(value: object) -> str:
    return str(value or "").strip()


def _qvd_name(value: str) -> str:
    return _safe(value).replace("\\", "/").rsplit("/", 1)[-1].lower()


def _field_token(value: str) -> str:
    value = re.sub(r"\[[^]]+\]", lambda m: m.group(0)[1:-1], value)
    return value.strip(" '\"[]").upper()


def _rules(source_map: Optional[dict]) -> list[dict]:
    if not source_map:
        return []
    return source_map.get("connections", []) if isinstance(source_map, dict) else []


def analyze(apps: Iterable[dict], source_map: Optional[dict] = None) -> tuple[LineageGraph, dict]:
    graph = LineageGraph()
    app_scripts: Dict[str, object] = {}
    connection_systems: Dict[str, str] = {}
    qvd_producers: Dict[str, List[str]] = {}
    logical_tables: Dict[str, List[str]] = {}
    logical_table_fields: Dict[str, set[str]] = {}
    unresolved: List[dict] = []

    for app in apps:
        app_id = app["id"]
        graph.add_node(app_id, "app", name=app["name"], file=app["file"])
        for connection in app.get("connections", []):
            system = classify(connection, _rules(source_map))
            connection_systems[connection["id"]] = system
            graph.add_node(connection["id"], "connection", name=connection["name"], source_system=system)
            graph.add_edge(app_id, connection["id"], "app_uses_connection", "high", [Evidence(app["file"], app["json_path"])])
        script_text = app.get("load_script", "")
        if script_text:
            analysis = parse_script(script_text)
            app_scripts[app_id] = analysis
            app_systems = {
                classify(connection, _rules(source_map))
                for connection in app.get("connections", [])
            }
            app_systems.discard("unknown")
            for warning in analysis.warnings:
                unresolved.append({"app": app_id, "kind": "script_warning", "message": warning})
            for load in analysis.loads:
                table_id = f"qlik_table:{app_id}/{load.label}"
                logical_tables.setdefault(load.label.upper(), []).append(table_id)
                logical_table_fields[table_id] = {
                    _field_token(field) for field in load.fields if _field_token(field)
                }
                graph.add_node(
                    table_id,
                    "qlik_table",
                    name=load.label,
                    app_id=app_id,
                    fields=sorted(logical_table_fields[table_id]),
                )
                evidence = [Evidence(app["file"], f"{app['json_path']}.load_script", load.line_start, load.line_end, "Qlik load statement")]
                graph.add_edge(app_id, table_id, "app_contains_qlik_table", "high", evidence)
                if load.qvd:
                    qvd_id = f"qvd:{_qvd_name(load.qvd)}"
                    graph.add_node(qvd_id, "qvd", name=load.qvd)
                    graph.add_edge(table_id, qvd_id, "qlik_table_loads_from_qvd", "high", evidence)
                if load.warehouse_table:
                    warehouse_id = f"warehouse_table:{load.warehouse_table.lower()}"
                    source_system = next(iter(app_systems)) if len(app_systems) == 1 else "unknown"
                    graph.add_node(
                        warehouse_id,
                        "warehouse_table",
                        name=load.warehouse_table,
                        source_system=source_system,
                    )
                    graph.add_edge(table_id, warehouse_id, "qlik_table_loads_from_warehouse_table", "high", evidence)
                if load.source_kind == "unknown":
                    unresolved.append({"app": app_id, "kind": "load_source", "table": load.label, "message": "Load statement has no resolvable source."})
            for store in analysis.stores:
                qvd_id = f"qvd:{_qvd_name(store.qvd)}"
                graph.add_node(qvd_id, "qvd", name=store.qvd)
                graph.add_edge(app_id, qvd_id, "app_produces_qvd", "high", [Evidence(app["file"], f"{app['json_path']}.load_script", store.line_start, store.line_end, "Qlik STORE statement")])
                qvd_producers.setdefault(_qvd_name(store.qvd), []).append(app_id)

        for qvd in app.get("qvds", []):
            qvd_id = qvd["id"]
            graph.add_node(qvd_id, "qvd", name=qvd["name"], path=qvd.get("path"))
            graph.add_edge(app_id, qvd_id, "app_consumes_qvd", "high", [Evidence(qvd["file"], qvd["json_path"], reason="Core CTL QVD reference")])
            if qvd.get("producer_app"):
                producer = f"app:{qvd['producer_app']}"
                graph.add_node(producer, "app", name=str(qvd["producer_app"]))
                graph.add_edge(producer, qvd_id, "app_produces_qvd", "medium", [Evidence(qvd["file"], qvd["json_path"])])

        for dashboard in app.get("dashboards", []):
            dashboard_id = dashboard["id"]
            graph.add_node(dashboard_id, "dashboard", name=dashboard["name"], app_id=app_id)
            graph.add_edge(app_id, dashboard_id, "app_contains_dashboard", "high", [Evidence(app["file"], app["json_path"])])
            for sheet in dashboard.get("sheets", []):
                sheet_id = sheet["id"]
                graph.add_node(sheet_id, "sheet", name=sheet["name"], dashboard_id=dashboard_id)
                graph.add_edge(dashboard_id, sheet_id, "dashboard_contains_sheet", "high")
                for chart in sheet.get("charts", []):
                    chart_id = chart["id"]
                    graph.add_node(
                        chart_id,
                        "chart",
                        name=chart["name"],
                        expression=chart.get("expression"),
                        app_id=app_id,
                        dashboard_id=dashboard_id,
                        dimensions=chart.get("dimensions", []),
                        measures=chart.get("measures", []),
                        selectable=chart.get("selectable", True),
                        alternate_state=chart.get("alternate_state", ""),
                    )
                    graph.add_edge(sheet_id, chart_id, "sheet_contains_chart", "high")
                    for field in chart.get("fields", []):
                        field_id = f"field:{chart_id}/{_field_token(field)}"
                        graph.add_node(field_id, "field", name=field, chart_id=chart_id)
                        graph.add_edge(chart_id, field_id, "chart_references_field", "high")
                        candidates = []
                        token = _field_token(field)
                        for candidate_tables in logical_tables.values():
                            for table_id in candidate_tables:
                                if token in logical_table_fields.get(table_id, set()):
                                    candidates.append(table_id)
                        # Core CTL may provide a logical table in chart metadata.
                        explicit_table = chart.get("table") or chart.get("qlik_table")
                        if explicit_table:
                            candidates = logical_tables.get(_safe(explicit_table).upper(), [])
                        # A dashboard normally resolves fields in its own app's
                        # in-memory model. Prefer that scope before considering
                        # same-named tables from other exported apps.
                        local_candidates = [
                            candidate for candidate in candidates
                            if candidate.startswith(f"qlik_table:{app_id}/")
                        ]
                        if local_candidates:
                            candidates = local_candidates
                        if len(candidates) == 1:
                            graph.add_edge(field_id, candidates[0], "field_belongs_to_qlik_table", "medium")
                        elif len(candidates) > 1:
                            unresolved.append({"chart": chart_id, "field": field, "kind": "ambiguous_field", "tables": candidates})
                        else:
                            unresolved.append({"chart": chart_id, "field": field, "kind": "unresolved_field", "message": "No logical Qlik table matched this field."})

    # Connect QVD producers to Qlik tables and propagate source tables through the graph.
    for qvd_name, producer_apps in qvd_producers.items():
        qvd_nodes = [node_id for node_id, node in graph.nodes.items() if node["type"] == "qvd" and _qvd_name(node.get("name", "")) == qvd_name]
        for qvd_id in qvd_nodes:
            for producer_app in producer_apps:
                for table_id in [node_id for node_id in graph.nodes if node_id.startswith(f"qlik_table:{producer_app}/")]:
                    graph.add_edge(qvd_id, table_id, "qvd_produced_by_qlik_table", "medium")

    # Qlik's associative model links logical tables on shared field names. This
    # is the basis for cross-filter target inference, not the QVD contents.
    tables_by_app: Dict[str, List[str]] = {}
    for table_id, node in graph.nodes.items():
        if node.get("type") == "qlik_table":
            tables_by_app.setdefault(str(node.get("app_id")), []).append(table_id)
    for app_id, table_ids in tables_by_app.items():
        for index, left_id in enumerate(table_ids):
            left_fields = set(graph.nodes[left_id].get("fields", []))
            for right_id in table_ids[index + 1:]:
                shared = sorted(left_fields & set(graph.nodes[right_id].get("fields", [])))
                if not shared:
                    continue
                evidence = [Evidence("<normalized-qlik-model>", reason=f"Shared Qlik field(s): {', '.join(shared)}")]
                graph.add_edge(left_id, right_id, "qlik_tables_associated_by_field", "medium", evidence)
                graph.add_edge(right_id, left_id, "qlik_tables_associated_by_field", "medium", evidence)

    # Add source-system nodes for explicit connection declarations and classify warehouse nodes.
    for node_id, node in list(graph.nodes.items()):
        if node["type"] != "warehouse_table":
            continue
        # Keep the explicit connection-derived classification when available.
        # A table name is never enough evidence to classify a warehouse.
        node.setdefault("source_system", "unknown")

    from .interactions import build_cross_filter_plan

    summary = summarize(graph, unresolved)
    summary["cross_filters"] = build_cross_filter_plan(graph)
    return graph, summary


def summarize(graph: LineageGraph, unresolved: List[dict]) -> dict:
    dashboards = []
    qvds = []
    source_tables = []
    for node_id, node in sorted(graph.nodes.items()):
        if node["type"] == "dashboard":
            reachable = graph.reachable(node_id)
            systems = {graph.nodes[item].get("source_system") for item in reachable if graph.nodes.get(item, {}).get("type") == "warehouse_table"}
            qvd_names = [graph.nodes[item].get("name") for item in reachable if graph.nodes.get(item, {}).get("type") == "qvd"]
            if "redshift" in systems and "snowflake" in systems:
                classification = "mixed_redshift_snowflake"
            elif "redshift" in systems:
                classification = "redshift_direct" if not qvd_names else "redshift_via_qvd"
            elif "snowflake" in systems:
                classification = "snowflake_direct"
            else:
                classification = "unresolved"
            dashboards.append({"id": node_id, "name": node.get("name"), "classification": classification, "qvds": sorted(set(qvd_names)), "warehouse_tables": sorted(graph.nodes[item].get("name") for item in reachable if graph.nodes.get(item, {}).get("type") == "warehouse_table")})
        elif node["type"] == "qvd":
            reachable = graph.reachable(node_id)
            tables = [graph.nodes[item].get("name") for item in reachable if graph.nodes.get(item, {}).get("type") == "warehouse_table"]
            qvds.append({"id": node_id, "name": node.get("name"), "warehouse_tables": sorted(set(tables)), "classification": "redshift_via_qvd" if any(graph.nodes[item].get("source_system") == "redshift" for item in reachable if item in graph.nodes) else "unresolved"})
        elif node["type"] == "warehouse_table":
            source_tables.append({"id": node_id, "name": node.get("name"), "source_system": node.get("source_system", "unknown")})
    return {"dashboards": dashboards, "qvds": qvds, "source_tables": source_tables, "unresolved": unresolved}
