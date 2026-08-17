"""Small deterministic lineage graph with evidence attached to every edge."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple


@dataclass(frozen=True)
class Evidence:
    file: str
    path: str = "$"
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    reason: str = ""

    def as_dict(self) -> dict:
        result = {"file": self.file, "path": self.path}
        if self.line_start is not None:
            result["line_start"] = self.line_start
        if self.line_end is not None:
            result["line_end"] = self.line_end
        if self.reason:
            result["reason"] = self.reason
        return result


@dataclass
class Edge:
    source: str
    target: str
    relation: str
    confidence: str = "medium"
    evidence: List[Evidence] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "from": self.source,
            "to": self.target,
            "relation": self.relation,
            "confidence": self.confidence,
            "evidence": [item.as_dict() for item in self.evidence],
        }


class LineageGraph:
    """A graph keyed by stable ``type:id`` node identifiers."""

    def __init__(self) -> None:
        self.nodes: Dict[str, dict] = {}
        self.edges: Dict[Tuple[str, str, str], Edge] = {}

    def add_node(self, node_id: str, node_type: str, **attributes: object) -> str:
        record = self.nodes.setdefault(node_id, {"id": node_id, "type": node_type})
        for key, value in attributes.items():
            if value not in (None, "", [], {}):
                record[key] = value
        return node_id

    def add_edge(
        self,
        source: str,
        target: str,
        relation: str,
        confidence: str = "medium",
        evidence: Optional[Iterable[Evidence]] = None,
    ) -> None:
        key = (source, target, relation)
        current = self.edges.get(key)
        if current is None:
            self.edges[key] = Edge(
                source=source,
                target=target,
                relation=relation,
                confidence=confidence,
                evidence=list(evidence or []),
            )
            return
        confidence_rank = {"unresolved": 0, "low": 1, "medium": 2, "high": 3}
        if confidence_rank.get(confidence, 1) > confidence_rank.get(current.confidence, 1):
            current.confidence = confidence
        for item in evidence or []:
            if item not in current.evidence:
                current.evidence.append(item)

    def outgoing(self, node_id: str) -> List[Edge]:
        return [edge for edge in self.edges.values() if edge.source == node_id]

    def incoming(self, node_id: str) -> List[Edge]:
        return [edge for edge in self.edges.values() if edge.target == node_id]

    def reachable(self, start: str, node_types: Optional[Set[str]] = None) -> Set[str]:
        seen: Set[str] = set()
        queue = [start]
        while queue:
            current = queue.pop(0)
            if current in seen:
                continue
            seen.add(current)
            for edge in self.outgoing(current):
                if edge.target not in seen:
                    queue.append(edge.target)
        if node_types is None:
            return seen
        return {node_id for node_id in seen if self.nodes.get(node_id, {}).get("type") in node_types}

    def as_dict(self) -> dict:
        return {
            "schema_version": 1,
            "nodes": [self.nodes[key] for key in sorted(self.nodes)],
            "edges": [self.edges[key].as_dict() for key in sorted(self.edges)],
        }
