import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from qlik_redshift_lineage.analyzer import analyze
from qlik_redshift_lineage.core_ctl import load_documents, normalize_documents
from qlik_redshift_lineage.snowflake import ddl, manifest, map_type


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "redshift-via-qvd"


class LineageTests(unittest.TestCase):
    def apps(self):
        documents = load_documents(FIXTURE / "ctl.json")
        return normalize_documents(documents)

    def source_map(self):
        return json.loads((FIXTURE / "source-map.json").read_text())

    def test_redshift_qvd_reaches_dashboard(self):
        graph, summary = analyze(self.apps(), self.source_map())
        dashboard = next(item for item in summary["dashboards"] if item["id"] == "dashboard:orders-dashboard")
        self.assertEqual(dashboard["classification"], "redshift_via_qvd")
        self.assertIn("orders.qvd", [str(item).lower() for item in dashboard["qvds"]])
        self.assertTrue(any(item["source_system"] == "redshift" for item in summary["source_tables"]))
        self.assertGreaterEqual(len(graph.edges), 8)

    def test_evidence_has_script_lines(self):
        graph, _ = analyze(self.apps(), self.source_map())
        script_edges = [
            edge for edge in graph.edges.values()
            if edge.relation == "qlik_table_loads_from_warehouse_table"
        ]
        self.assertTrue(script_edges)
        self.assertTrue(script_edges[0].evidence[0].line_start)

    def test_unknown_connection_does_not_become_redshift(self):
        apps = self.apps()
        apps[0]["connections"][0]["name"] = "warehouse-prod"
        _, summary = analyze(apps, {"connections": []})
        self.assertEqual(summary["source_tables"][0]["source_system"], "unknown")

    def test_cross_filter_plan_builds_selection_actions(self):
        _, summary = analyze(self.apps(), self.source_map())
        plan = summary["cross_filters"]
        self.assertEqual(len(plan["controls"]), 1)
        self.assertEqual(len(plan["actions"]), 2)
        self.assertTrue(all(action["trigger"] == "on-select" for action in plan["actions"]))
        self.assertTrue(any(
            effect["value"]["formula"] == "[Selection/CUSTOMER_ID]"
            for action in plan["actions"]
            for effect in action["effects"]
        ))
        self.assertEqual(len(plan["clear_buttons"]), 1)

    def test_alternate_state_is_reviewed_not_silently_mapped(self):
        apps = self.apps()
        apps[0]["connections"][0]["name"] = "redshift-prod"
        apps[1]["dashboards"][0]["sheets"][0]["charts"][0]["alternate_state"] = "AltState"
        _, summary = analyze(apps, self.source_map())
        review_kinds = {item["kind"] for item in summary["cross_filters"]["review"]}
        self.assertIn("alternate_state", review_kinds)
        self.assertFalse(any(
            action["host_element"] == "chart:revenue-by-customer"
            for action in summary["cross_filters"]["actions"]
        ))


class SnowflakeTests(unittest.TestCase):
    def test_numeric_mapping_preserves_precision(self):
        result = map_type({"column_name": "amount", "data_type": "numeric", "numeric_precision": 18, "numeric_scale": 2})
        self.assertEqual(result["target_type"], "NUMBER(18,2)")
        self.assertEqual(result["status"], "AUTO")

    def test_manifest_and_ddl(self):
        apps = normalize_documents(load_documents(FIXTURE / "ctl.json"))
        _, summary = analyze(apps, json.loads((FIXTURE / "source-map.json").read_text()))
        catalog = json.loads((FIXTURE / "redshift-catalog.json").read_text())
        target = json.loads((FIXTURE / "target-config.json").read_text())
        result = manifest(summary, catalog, target)
        self.assertEqual(result["tables"][0]["target_table"], "ORDERS")
        generated = ddl(result)
        self.assertIn("CREATE TABLE IF NOT EXISTS ANALYTICS.QLIK_STAGE.ORDERS", generated)
        self.assertIn("NUMBER(18,2)", generated)


if __name__ == "__main__":
    unittest.main()
