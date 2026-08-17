"""Core CTL intake and normalization.

Core CTL exports have differed between deployments. The adapter accepts the
documented canonical shape and a small set of common aliases, while retaining
the original JSON path as evidence. It deliberately does not claim that an
unknown field is lineage.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


ALIASES = {
    "id": ("id", "uid", "resourceId", "objectId", "qId"),
    "name": ("name", "title", "label", "appName", "dashboardName"),
    "apps": ("apps", "applications", "qlikApps", "items"),
    "dashboards": ("dashboards", "dashboard", "sheets", "pages"),
    "sheets": ("sheets", "pages", "tabs"),
    "charts": ("charts", "visuals", "objects", "items", "objectsInSheet"),
    "connections": ("connections", "dataConnections", "connectionsUsed"),
    "load_script": ("load_script", "loadScript", "script", "scriptText", "qvs"),
    "qvds": ("qvds", "qvd", "qvdFiles", "qvdReferences"),
    "source_system": ("source_system", "sourceSystem", "technology", "engine", "type"),
    "source_table": ("source_table", "sourceTable", "table", "tableName", "physicalTable"),
    "fields": ("fields", "columns", "dimensions", "measures", "fieldRefs"),
}


def _key(obj: dict, logical: str) -> Optional[str]:
    for candidate in ALIASES.get(logical, (logical,)):
        if candidate in obj:
            return candidate
    lowered = {str(k).lower(): k for k in obj}
    for candidate in ALIASES.get(logical, (logical,)):
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return None


def value(obj: dict, logical: str, default: Any = None) -> Any:
    key = _key(obj, logical)
    return obj[key] if key is not None else default


def as_list(value_or_item: Any) -> List[Any]:
    if value_or_item is None:
        return []
    if isinstance(value_or_item, list):
        return value_or_item
    return [value_or_item]


def stable_id(prefix: str, raw_id: Any, fallback: str) -> str:
    raw = str(raw_id or fallback).strip()
    raw = re.sub(r"[^A-Za-z0-9_.:/-]+", "_", raw)
    return f"{prefix}:{raw or fallback}"


def json_files(input_path: Path) -> Iterable[Path]:
    if input_path.is_file():
        yield input_path
        return
    yield from sorted(input_path.rglob("*.json"))


def load_documents(input_path: Path) -> List[Tuple[Path, Any]]:
    documents = []
    for path in json_files(input_path):
        try:
            documents.append((path, json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Unable to read JSON file {path}: {exc}") from exc
    if not documents:
        raise ValueError(f"No JSON files found under {input_path}")
    return documents


def _objects_with_key(obj: Any, wanted: set[str], path: str = "$") -> Iterable[Tuple[dict, str]]:
    if isinstance(obj, dict):
        for key, child in obj.items():
            if str(key).lower() in wanted and isinstance(child, list):
                for index, item in enumerate(child):
                    if isinstance(item, dict):
                        yield item, f"{path}.{key}[{index}]"
            yield from _objects_with_key(child, wanted, f"{path}.{key}")
    elif isinstance(obj, list):
        for index, child in enumerate(obj):
            yield from _objects_with_key(child, wanted, f"{path}[{index}]")


def _looks_like_app(obj: dict) -> bool:
    keys = {str(key).lower() for key in obj}
    return bool(keys & {"loadscript", "load_script", "qvds", "qvdfiles", "sheets", "dashboards"}) and bool(
        keys & {"id", "uid", "resourceid", "name", "appname"}
    )


def find_apps(document: Any) -> List[Tuple[dict, str]]:
    found: List[Tuple[dict, str]] = []
    for app, path in _objects_with_key(document, {"apps", "applications", "qlikapps"}):
        found.append((app, path))
    if isinstance(document, dict) and _looks_like_app(document):
        found.append((document, "$"))
    if not found:
        for app, path in _objects_with_key(document, {"app"}):
            if _looks_like_app(app):
                found.append((app, path))
    deduped = []
    seen = set()
    for app, path in found:
        marker = (str(value(app, "id", "")), str(value(app, "name", "")), path)
        if marker not in seen:
            seen.add(marker)
            deduped.append((app, path))
    return deduped


def _text(value_or_obj: Any) -> str:
    if isinstance(value_or_obj, str):
        return value_or_obj
    if isinstance(value_or_obj, (int, float, bool)):
        return str(value_or_obj)
    if isinstance(value_or_obj, dict):
        for key in ("text", "expr", "expression", "definition", "qDef", "value"):
            if key in value_or_obj and isinstance(value_or_obj[key], (str, int, float)):
                return str(value_or_obj[key])
    return ""


def _records(app: dict, logical: str) -> List[dict]:
    result = []
    for item in as_list(value(app, logical)):
        if isinstance(item, dict):
            result.append(item)
    return result


def _nested_records(parent: dict, logical: str, nested_logical: str) -> List[dict]:
    direct = _records(parent, nested_logical)
    if direct:
        return direct
    return [item for record in _records(parent, logical) for item in _records(record, nested_logical)]


def normalize_app(app: dict, file_path: Path, app_path: str, ordinal: int) -> dict:
    app_id = stable_id("app", value(app, "id"), value(app, "name", f"app-{ordinal}"))
    app_name = value(app, "name", app_id.split(":", 1)[-1])
    result = {
        "id": app_id,
        "name": str(app_name),
        "file": str(file_path),
        "json_path": app_path,
        "load_script": _text(value(app, "load_script", "")),
        "connections": [],
        "qvds": [],
        "dashboards": [],
    }

    for index, connection in enumerate(_records(app, "connections")):
        connection_id = stable_id("connection", value(connection, "id"), value(connection, "name", f"{app_id}-{index}"))
        result["connections"].append({
            "id": connection_id,
            "name": str(value(connection, "name", connection_id)),
            "source_system": value(connection, "source_system"),
            "host": connection.get("host") or connection.get("server") or connection.get("endpoint"),
            "raw": connection,
        })

    for index, qvd in enumerate(_records(app, "qvds")):
        qvd_name = value(qvd, "name", value(qvd, "path", f"qvd-{index}"))
        result["qvds"].append({
            "id": stable_id("qvd", qvd_name, f"{app_id}-{index}"),
            "name": str(qvd_name),
            "path": qvd.get("path") or qvd.get("file") or qvd_name,
            "producer_app": qvd.get("producerApp") or qvd.get("producer_app"),
            "consumer": True,
            "file": str(file_path),
            "json_path": f"{app_path}.qvds[{index}]",
        })

    dashboards = _records(app, "dashboards")
    if not dashboards and (_records(app, "sheets") or _records(app, "charts")):
        dashboards = [{"id": app_id.split(":", 1)[-1], "name": app_name, "sheets": _records(app, "sheets"), "charts": _records(app, "charts")}]
    for d_index, dashboard in enumerate(dashboards):
        dashboard_id = stable_id("dashboard", value(dashboard, "id"), f"{app_id}-{d_index}")
        normalized_dashboard = {
            "id": dashboard_id,
            "name": str(value(dashboard, "name", f"Dashboard {d_index + 1}")),
            "sheets": [],
        }
        sheets = _records(dashboard, "sheets")
        if not sheets and value(dashboard, "charts") is not None:
            sheets = [{"id": "default", "name": "Default", "charts": _records(dashboard, "charts")}]
        for s_index, sheet in enumerate(sheets):
            sheet_id = stable_id("sheet", value(sheet, "id"), f"{dashboard_id}-{s_index}")
            normalized_sheet = {
                "id": sheet_id,
                "name": str(value(sheet, "name", f"Sheet {s_index + 1}")),
                "charts": [],
            }
            charts = _records(sheet, "charts")
            for c_index, chart in enumerate(charts):
                chart_id = stable_id("chart", value(chart, "id"), f"{sheet_id}-{c_index}")
                fields = []
                for field_item in as_list(value(chart, "fields")):
                    text = _text(field_item)
                    if text:
                        fields.append(text)
                for key in ("dimensions", "measures"):
                    for field_item in as_list(chart.get(key)):
                        text = _text(field_item)
                        if text:
                            fields.append(text)
                normalized_sheet["charts"].append({
                    "id": chart_id,
                    "name": str(value(chart, "name", f"Chart {c_index + 1}")),
                    "fields": sorted(set(fields)),
                    "expression": _text(chart.get("expression") or chart.get("qDef")),
                })
            normalized_dashboard["sheets"].append(normalized_sheet)
        result["dashboards"].append(normalized_dashboard)
    return result


def normalize_documents(documents: Iterable[Tuple[Path, Any]]) -> List[dict]:
    apps = []
    ordinal = 0
    for file_path, document in documents:
        found = find_apps(document)
        if not found:
            raise ValueError(
                f"No Qlik apps found in {file_path}. Expected an apps array or an app object; "
                "see refs/core-ctl-input-contract.md."
            )
        for app, path in found:
            apps.append(normalize_app(app, file_path, path, ordinal))
            ordinal += 1
    return apps
