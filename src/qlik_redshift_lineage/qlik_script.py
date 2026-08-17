"""Conservative parser for the Qlik load-script constructs needed for lineage."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class LoadStatement:
    label: str
    statement: str
    source: str = ""
    source_kind: str = "unknown"
    qvd: str = ""
    warehouse_table: str = ""
    connection: str = ""
    fields: List[str] = field(default_factory=list)
    aliases: List[dict] = field(default_factory=list)
    line_start: int = 1
    line_end: int = 1
    operation: str = "load"


@dataclass
class ScriptAnalysis:
    connections: List[str] = field(default_factory=list)
    loads: List[LoadStatement] = field(default_factory=list)
    stores: List[LoadStatement] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _line_number(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _strip_comments(statement: str) -> str:
    statement = re.sub(r"/\*.*?\*/", " ", statement, flags=re.S)
    # Only treat a line-start // as a comment. Qlik connection paths commonly
    # contain lib://, which must remain intact for QVD lineage.
    return re.sub(r"(?m)^[ \t]*//[^\n]*", " ", statement)


def _split_fields(text: str) -> List[str]:
    fields, current, depth, quote = [], [], 0, ""
    for char in text:
        if quote:
            current.append(char)
            if char == quote:
                quote = ""
            continue
        if char in "'\"":
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            fields.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if current:
        fields.append("".join(current).strip())
    return [item for item in fields if item]


def _field_info(field_text: str) -> tuple[str, Optional[dict]]:
    cleaned = field_text.strip().rstrip(";")
    alias_match = re.match(r"(?is)(.*?)\s+AS\s+[\[\]\"']*([A-Za-z_][\w ]*)[\[\]\"']*\s*$", cleaned)
    if alias_match:
        expression, alias = alias_match.group(1).strip(), alias_match.group(2).strip()
        return alias, {"qlik_field": alias, "expression": expression, "real_column": expression}
    identifier = re.match(r"^[\[\]\"']*([A-Za-z_][\w ]*)[\[\]\"']*$", cleaned)
    if identifier:
        return identifier.group(1).strip(), None
    return cleaned, {"qlik_field": cleaned, "expression": cleaned, "real_column": ""}


def _source(statement: str) -> tuple[str, str, str, str]:
    qvd_match = re.search(r"(?is)\bFROM\s+\[([^\]]+\.qvd)\]", statement)
    if not qvd_match:
        qvd_match = re.search(r"(?is)\bFROM\s+([^\s;]+\.qvd)", statement)
    if qvd_match:
        path = qvd_match.group(1)
        return path, "qvd", path.rsplit("/", 1)[-1], ""
    resident_match = re.search(r"(?is)\bRESIDENT\s+([A-Za-z_][\w]*)", statement)
    if resident_match:
        return resident_match.group(1), "resident", "", ""
    table_match = re.search(
        r"(?is)\b(?:SQL\s+)?SELECT\b.*?\bFROM\s+([\[\]A-Za-z0-9_\"'.-]+(?:\.[\[\]A-Za-z0-9_\"'.-]+){0,2})",
        statement,
    )
    if table_match:
        table = table_match.group(1).strip("[]\"'")
        return table, "warehouse", "", table
    file_match = re.search(r"(?is)\bFROM\s+\[([^\]]+)\]", statement)
    if not file_match:
        file_match = re.search(r"(?is)\bFROM\s+([^\s;]+)", statement)
    if file_match:
        return file_match.group(1), "file", "", ""
    return "", "unknown", "", ""


def _load_from_statement(statement: str, label: str, start: int, source_text: str) -> LoadStatement:
    cleaned = _strip_comments(statement)
    source, kind, qvd, warehouse_table = _source(cleaned)
    load_match = re.search(r"(?is)\bLOAD\b(.*?)(?=\bFROM\b|\bRESIDENT\b|\bINLINE\b|\bAUTOGENERATE\b|\bSQL\s+SELECT\b|$)", cleaned)
    fields, aliases = [], []
    if load_match:
        for item in _split_fields(load_match.group(1)):
            field_name, alias = _field_info(item)
            if field_name and field_name != "*":
                fields.append(field_name)
                if alias:
                    aliases.append(alias)
    return LoadStatement(
        label=label or "unlabeled",
        statement=statement.strip(),
        source=source,
        source_kind=kind,
        qvd=qvd,
        warehouse_table=warehouse_table,
        fields=fields,
        aliases=aliases,
        line_start=_line_number(source_text, start),
        line_end=_line_number(source_text, start + len(statement)),
    )


def parse_script(text: str) -> ScriptAnalysis:
    result = ScriptAnalysis()
    for match in re.finditer(r"(?is)\bLIB\s+CONNECT\s+TO\s+['\"]([^'\"]+)['\"]", text):
        if match.group(1) not in result.connections:
            result.connections.append(match.group(1))

    label = ""
    statement_start = 0
    # Split on semicolons. This is intentionally conservative; expressions with
    # embedded semicolons are reported as review items rather than reinterpreted.
    for match in re.finditer(r"[^;]*;", text, flags=re.S):
        raw = match.group(0)
        cleaned = _strip_comments(raw).strip()
        if not cleaned:
            continue
        label_match = re.match(r"(?is)^\s*([A-Za-z_][\w]*)\s*:\s*", cleaned)
        if label_match:
            label = label_match.group(1)
        if re.search(r"(?is)\bLOAD\b", cleaned):
            result.loads.append(_load_from_statement(raw, label, match.start(), text))
        elif re.search(r"(?is)\bSQL\s+SELECT\b", cleaned):
            record = _load_from_statement(raw, label, match.start(), text)
            record.operation = "sql_select"
            result.loads.append(record)
        store_match = re.search(r"(?is)\bSTORE\b.*?\bINTO\s+\[([^\]]+\.qvd)\]", cleaned)
        if not store_match:
            store_match = re.search(r"(?is)\bSTORE\b.*?\bINTO\s+([^\s;]+\.qvd)", cleaned)
        if store_match:
            path = store_match.group(1)
            result.stores.append(
                LoadStatement(
                    label=label or "unlabeled",
                    statement=raw.strip(),
                    source=path,
                    source_kind="qvd",
                    qvd=path.rsplit("/", 1)[-1],
                    line_start=_line_number(text, match.start()),
                    line_end=_line_number(text, match.end()),
                    operation="store",
                )
            )
        statement_start = match.end()
    if re.search(r"(?is)\bINCLUDE\b|\$\(must_include", text):
        result.warnings.append("Script contains INCLUDE/must_include; external script content was not resolved.")
    if re.search(r"(?is)\$\([^)]*\)", text):
        result.warnings.append("Script contains variable expansion; unresolved values may hide source paths.")
    return result
