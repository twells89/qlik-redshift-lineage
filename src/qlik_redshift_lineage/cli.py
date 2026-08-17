"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from .analyzer import analyze
from .core_ctl import load_documents, normalize_documents
from .reports import write_outputs
from .snowflake import ddl, manifest


def _json_file(path: Optional[str]) -> Optional[dict]:
    if not path:
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read JSON file {path}: {exc}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Trace Redshift-backed Qlik QVDs and dashboards.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    analyze_parser = subparsers.add_parser("analyze", help="Analyze Core CTL JSON exports.")
    analyze_parser.add_argument("--input", required=True, help="Core CTL JSON file or export directory.")
    analyze_parser.add_argument("--out", required=True, help="Output directory.")
    analyze_parser.add_argument("--source-map", help="Explicit connection classification JSON.")
    analyze_parser.add_argument("--redshift-catalog", help="Optional Redshift information_schema snapshot JSON.")
    analyze_parser.add_argument("--target-config", help="Optional Snowflake target JSON.")
    analyze_parser.add_argument("--strict", action="store_true", help="Exit non-zero when unresolved lineage exists.")
    return parser


def run_analysis(args: argparse.Namespace) -> int:
    documents = load_documents(Path(args.input))
    apps = normalize_documents(documents)
    source_map = _json_file(args.source_map)
    graph, summary = analyze(apps, source_map)
    catalog = _json_file(args.redshift_catalog)
    target = _json_file(args.target_config)
    migration_manifest = manifest(summary, catalog, target)
    write_outputs(Path(args.out), graph, summary, migration_manifest, ddl(migration_manifest))
    print(f"apps={len(apps)} nodes={len(graph.nodes)} edges={len(graph.edges)} unresolved={len(summary['unresolved'])}")
    print(f"outputs={args.out}")
    return 2 if args.strict and summary["unresolved"] else 0


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "analyze":
            raise SystemExit(run_analysis(args))
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
