"""Recoverable editor checkpoints, layout and new mail blocks; no network."""

from copy import deepcopy
from contextlib import closing
import sqlite3
import unittest
import zipfile

import test_email_builder as builder_harness
from emailcenter.builder_workspace import BuilderWorkspaceService, arrange_graph, validate_state
from emailcenter.email_builder import node, NODE_TYPES


class WorkspaceCheckpointTests(unittest.TestCase):
    setUp = builder_harness.BuilderTests.setUp
    tearDown = builder_harness.BuilderTests.tearDown

    def state(self):
        return {"graph": deepcopy(self.graph), "name": "Arbeitsstand", "builder_id": None, "version_id": None,
            "provider_account_id": None, "signature_id": None, "last_batch": None, "delivery_mode": "scheduled",
            "scheduled_local": "2030-01-02T12:00:00", "timezone_id": "UTC", "interval_seconds": 7,
            "view": {"zoom": 1.2, "x": 250, "y": 180}}

    def test_roundtrip_partial_inputs_and_reopen_without_versions_or_jobs(self):
        service = BuilderWorkspaceService(self.project)
        state = self.state()
        state["name"] = ""
        state["graph"]["nodes"][2]["config"]["text"] = "Unfertig {{company."
        pending = node("replace")
        pending["config"]["rules"] = [{"find": "", "replacement": "", "field": ""}]
        state["graph"]["nodes"].append(pending)
        value = service.save(self.project.project_id, state, 0)
        self.assertEqual(value["revision"], 1)
        for table in ("email_jobs", "email_builder_versions", "email_drafts", "documents"):
            self.assertEqual(self.db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0], 0)
        self.workspace.close()
        self.workspace.open(str(self.root / "project"))
        loaded = BuilderWorkspaceService(self.workspace.project).load()
        self.assertEqual(loaded["state"], state)
        self.assertEqual(loaded["warning"], "")

    def test_same_state_does_not_increment_revision_and_conflict_preserves_latest(self):
        service = BuilderWorkspaceService(self.project)
        state = self.state()
        self.assertEqual(service.save(self.project.project_id, state, 0)["revision"], 1)
        self.assertEqual(service.save(self.project.project_id, state, 1)["revision"], 1)
        changed = deepcopy(state)
        changed["name"] = "Neuer"
        with self.assertRaisesRegex(ValueError, "anderen Fenster"):
            service.save(self.project.project_id, changed, 0)
        self.assertEqual(service.load()["state"], state)
        self.assertEqual(service.save(self.project.project_id, changed, 1)["revision"], 2)

    def test_invalid_project_state_and_revision_do_not_overwrite(self):
        service = BuilderWorkspaceService(self.project)
        service.save(self.project.project_id, self.state(), 0)
        for changes in ({"view": {"zoom": 0, "x": 0, "y": 0}}, {"interval_seconds": True}, {"name": "a\n"}, {"extra": 1}, {"version_id": "missing"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                service.save(self.project.project_id, {**self.state(), **changes}, 1)
        for project, revision in (("other-project", 1), (self.project.project_id, True), (self.project.project_id, -1)):
            with self.assertRaises(ValueError):
                service.save(project, self.state(), revision)
        self.assertEqual(service.load()["revision"], 1)

    def test_corrupt_state_is_reported_without_removal(self):
        service = BuilderWorkspaceService(self.project)
        service.save(self.project.project_id, self.state(), 0)
        for column, value in (("content_hash", "changed"), ("state_json", "{invalid")):
            self.db.execute("UPDATE email_builder_workspace SET " + column + "=? WHERE id=1", (value,))
            result = service.load()
            self.assertIsNone(result["state"])
            self.assertTrue(result["warning"])
            self.assertEqual(result["revision"], 1)
            self.assertEqual(self.db.execute("SELECT " + column + " FROM email_builder_workspace").fetchone()[0], value)

    def test_checkpoint_restores_exact_named_base_without_changing_versions(self):
        service = BuilderWorkspaceService(self.project)
        first = self.service.save("Version", self.graph)["version"]
        state = self.state()
        state["builder_id"], state["version_id"] = first["builder_id"], first["id"]
        state["graph"]["nodes"][2]["config"]["text"] = "Noch ungespeichert"
        service.save(self.project.project_id, state, 0)
        loaded = service.load()
        self.assertEqual(loaded["base_version"]["graph"], self.graph)
        self.assertNotEqual(loaded["base_version"]["graph"], loaded["state"]["graph"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM email_builder_versions").fetchone()[0], 1)

    def test_project_backup_contains_checkpoint(self):
        service = BuilderWorkspaceService(self.project)
        state = self.state()
        service.save(self.project.project_id, state, 0)
        path = self.project.create_backup()
        target = self.root / "backup.sqlite3"
        with zipfile.ZipFile(path) as archive:
            target.write_bytes(archive.read("emailcenter.sqlite3"))
        with closing(sqlite3.connect(target)) as db:
            self.assertEqual(db.execute("SELECT revision FROM email_builder_workspace").fetchone()[0], 1)

    def test_layout_is_deterministic_preserves_edges_and_has_no_overlaps(self):
        for index in range(15):
            self.graph["nodes"].append(node("file", 9000, 9000))
        original = deepcopy(self.graph)
        result = arrange_graph(self.graph)
        self.assertEqual(self.graph, original)
        self.assertEqual(result["edges"], original["edges"])
        self.assertEqual(arrange_graph(result), result)
        for item in result["nodes"]:
            for other in result["nodes"]:
                if other["id"] != item["id"] and other["x"] == item["x"]:
                    height = max(115, 88 + max(len(NODE_TYPES[item["kind"]]["inputs"]), len(NODE_TYPES[item["kind"]]["outputs"])) * 29)
                    self.assertTrue(other["y"] < item["y"] or other["y"] >= item["y"] + height)
        self.assertGreater(result["nodes"][3]["x"], result["nodes"][1]["x"])

    def test_link_and_button_render_plain_and_safe_html_from_row_values(self):
        block = self.graph["nodes"][2]
        for source in self.graph["nodes"][0]["config"]["sources"]:
            source["fields"]["company.website"] = "https://example.test/?a=1&b=2"
        for kind in ("link", "button"):
            block["kind"], block["config"] = kind, {"text": "Profil von {{contact.display_name}}", "url": "{{company.website}}"}
            for body_format in ("plain", "html"):
                self.graph["nodes"][3]["config"]["body_format"] = body_format
                value = self.service.preview(self.graph)
                self.assertTrue(value["ready"], value["rows"])
                body = value["rows"][0]["body"]
                self.assertIn("Profil von Ada", body)
                self.assertIn('href="https://example.test/?a=1&amp;b=2"' if body_format == "html" else "(https://example.test/?a=1&b=2)", body)
                if kind == "button" and body_format == "html":
                    self.assertIn("display:inline-block", body)

    def test_bad_links_and_empty_lists_block_whole_group(self):
        block = self.graph["nodes"][2]
        block["kind"], block["config"] = "link", {"text": "Link", "url": ""}
        for url in ("javascript:alert(1)", "file:///C:/secret", "https://", "https://example.test:bad", "https://user:password@example.test", "https://example.test/path with spaces", "{{missing.field}}"):
            block["config"]["url"] = url
            self.assertFalse(self.service.preview(self.graph)["ready"], url)
        block["kind"], block["config"] = "list", {"text": "\n  \n", "ordered": False}
        self.assertFalse(self.service.preview(self.graph)["ready"])

    def test_lists_render_ordered_and_unordered_html_and_plain(self):
        block = self.graph["nodes"][2]
        block["kind"], block["config"] = "list", {"text": "{{contact.display_name}}\n\n<Text>\nDritter", "ordered": False}
        for ordered in (False, True):
            block["config"]["ordered"] = ordered
            self.graph["nodes"][3]["config"]["body_format"] = "plain"
            self.assertEqual(self.service.preview(self.graph)["rows"][0]["body"], "1. Ada\n2. <Text>\n3. Dritter" if ordered else "• Ada\n• <Text>\n• Dritter")
            self.graph["nodes"][3]["config"]["body_format"] = "html"
            tag = "ol" if ordered else "ul"
            self.assertEqual(self.service.preview(self.graph)["rows"][0]["body"], "<" + tag + "><li>Ada</li><li>&lt;Text&gt;</li><li>Dritter</li></" + tag + ">")
