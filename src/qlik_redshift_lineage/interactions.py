"""Infer Sigma action templates for Qlik's associative chart selections.

QVDs describe persisted data, not dashboard behavior. This module only emits
cross-filter actions when dashboard metadata and the parsed Qlik model provide
enough evidence to identify a selectable chart dimension and its associated
target charts.
"""

from __future__ import annotations

import hashlib
import re
from typing import Dict, Iterable, List, Set

from .graph import LineageGraph


def _token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", str(value or "").strip()).strip("_").lower()


def _field_token(value: str) -> str:
    return str(value or "").strip(" '\"[]").upper()


def _control_id(dashboard_id: str, field: str) -> str:
    base = f"qlik_filter_{_token(dashboard_id)}_{_token(field)}"
    if len(base) <= 80:
        return base
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:10]
    return f"qlik_filter_{digest}"


def _chart_tables(graph: LineageGraph, chart_id: str) -> Set[str]:
    tables: Set[str] = set()
    for field_edge in graph.outgoing(chart_id):
        if field_edge.relation != "chart_references_field":
            continue
        for table_edge in graph.outgoing(field_edge.target):
            if table_edge.relation == "field_belongs_to_qlik_table":
                tables.add(table_edge.target)
    return tables


def _associated_tables(graph: LineageGraph, tables: Iterable[str]) -> Set[str]:
    result: Set[str] = set(tables)
    queue = list(tables)
    while queue:
        table_id = queue.pop(0)
        for edge in graph.outgoing(table_id):
            if edge.relation != "qlik_tables_associated_by_field":
                continue
            if edge.target not in result:
                result.add(edge.target)
                queue.append(edge.target)
    return result


def _dashboard_charts(graph: LineageGraph, dashboard_id: str) -> List[str]:
    return sorted(
        node_id
        for node_id, node in graph.nodes.items()
        if node.get("type") == "chart" and node.get("dashboard_id") == dashboard_id
    )


def _dashboard_pages(graph: LineageGraph, dashboard_id: str) -> List[str]:
    return sorted(
        node_id
        for node_id, node in graph.nodes.items()
        if node.get("type") == "sheet" and node.get("dashboard_id") == dashboard_id
    )


def build_cross_filter_plan(graph: LineageGraph) -> dict:
    controls: Dict[str, dict] = {}
    actions: List[dict] = []
    clear_buttons: List[dict] = []
    review: List[dict] = []

    for dashboard_id, dashboard in sorted(graph.nodes.items()):
        if dashboard.get("type") != "dashboard":
            continue
        charts = _dashboard_charts(graph, dashboard_id)
        dashboard_controls: Set[str] = set()
        for chart_id in charts:
            chart = graph.nodes[chart_id]
            dimensions = chart.get("dimensions") or []
            if not chart.get("selectable", True):
                review.append({
                    "dashboard": dashboard_id,
                    "chart": chart_id,
                    "kind": "selection_disabled",
                    "message": "Qlik chart metadata disables selections; no Sigma on-select action was emitted.",
                })
                continue
            if chart.get("alternate_state"):
                review.append({
                    "dashboard": dashboard_id,
                    "chart": chart_id,
                    "kind": "alternate_state",
                    "state": chart["alternate_state"],
                    "message": "Qlik alternate-state behavior requires manual Sigma review.",
                })
                continue
            if not dimensions:
                continue
            source_tables = _chart_tables(graph, chart_id)
            if not source_tables:
                review.append({
                    "dashboard": dashboard_id,
                    "chart": chart_id,
                    "kind": "unresolved_selection_source",
                    "message": "No Qlik logical table was resolved for the chart dimensions.",
                })
                continue
            associated_tables = _associated_tables(graph, source_tables)
            effects = []
            for field in dimensions:
                target_charts = []
                for target_id in charts:
                    target_tables = _chart_tables(graph, target_id)
                    if target_tables & associated_tables:
                        target_charts.append(target_id)
                target_charts = sorted(set(target_charts))
                if not target_charts:
                    review.append({
                        "dashboard": dashboard_id,
                        "chart": chart_id,
                        "field": field,
                        "kind": "no_filter_targets",
                        "message": "The selected field has no resolved chart targets.",
                    })
                    continue
                control_id = _control_id(dashboard_id, field)
                dashboard_controls.add(control_id)
                controls.setdefault(
                    control_id,
                    {
                        "id": control_id,
                        "control_id": control_id,
                        "name": f"Qlik selection: {field}",
                        "field": field,
                        "scope": "dashboard",
                        "dashboard": dashboard_id,
                        "target_elements": target_charts,
                        "source_tables": sorted(source_tables),
                        "target_strategy": "associated_qlik_tables",
                        "confidence": "medium",
                        "sigma_binding": {
                            "control_type": "list",
                            "requires_source_element_mapping": True,
                            "requires_filter_target_mapping": True,
                        },
                    },
                )
                effects.append({
                    "effect": "set-control-value",
                    "control": control_id,
                    "value": {"type": "formula", "formula": f"[Selection/{field}]"},
                    "selection_field": field,
                    "target_elements": target_charts,
                })
            if effects:
                actions.append({
                    "id": f"action:{chart_id}:on-select",
                    "host_element": chart_id,
                    "trigger": "on-select",
                    "effects": effects,
                    "confidence": "medium",
                    "behavior": "set_associated_field_controls",
                    "notes": [
                        "Sigma action shape is verified, but the converter must map host and target IDs to the built workbook.",
                        "Qlik selection toggle and multi-select clearing semantics require runtime validation in Sigma.",
                    ],
                })
        if dashboard_controls:
            pages = _dashboard_pages(graph, dashboard_id) or [dashboard_id]
            clear_buttons.append({
                "id": f"button:{dashboard_id}:clear-selections",
                "kind": "button",
                "text": "Clear selections",
                "dashboard": dashboard_id,
                "actions": [{
                    "id": f"action:{dashboard_id}:clear-selections",
                    "trigger": "on-click",
                    "effects": [
                        {
                            "effect": "clear-control",
                            "scope": {"type": "page", "page": page_id},
                        }
                        for page_id in pages
                    ],
                }],
                "notes": [
                    "Map each neutral sheet ID to the corresponding Sigma page ID.",
                    "Generated as a Sigma equivalent of Qlik clear selections, not an inferred source object.",
                ],
            })
    return {
        "schema_version": 1,
        "semantics": "qlik_associative_selection_to_sigma_control_actions",
        "controls": [controls[key] for key in sorted(controls)],
        "actions": sorted(actions, key=lambda item: item["id"]),
        "clear_buttons": sorted(clear_buttons, key=lambda item: item["id"]),
        "review": review,
    }
