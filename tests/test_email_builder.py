"""Real graph evaluation and local draft capture; no live provider calls."""

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from emailcenter.application.workspace import WorkspaceService
from emailcenter.email_builder import EmailBuilderService, node, starter_graph, validate_graph
from emailcenter.data_source_library import DataSourceLibrary
from emailcenter.documents import extract_docx_text
from emailcenter.mail_bulk import BulkMailService
from emailcenter.mail_service import MailService
from emailcenter.preferences import Preferences, PreferencesStore
from test_documents import _make_docx


def edge(a, output, b, input):
    return {"from": a["id"], "output": output, "to": b["id"], "input": input}


class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.root = Path(self.temp.name)
        self.workspace = WorkspaceService()
        self.workspace.create(str(self.root / "project"), "Builder")
        self.project, self.db = self.workspace.project, self.workspace.project.connection
        self.service = EmailBuilderService(self.project)
        self.graph = starter_graph()
        self.graph["nodes"][0]["config"]["sources"] = [{"kind": "manual", "fields": {"contact.display_name": name, "contact.email": name.lower() + "@example.test", "company.name": name + " GmbH", "application.cover_letter": "Anschreiben " + name}} for name in ("Ada", "Grace")]

    def tearDown(self):
        self.workspace.close()
        self.temp.cleanup()

    def create(self, **options):
        preview = self.service.preview(self.graph, **options)
        self.assertTrue(preview["ready"], preview["rows"])
        return self.service.create("Builder-Gruppe", self.graph, preview["fingerprint"], **options)["batch"]

    def document_chain(self, pdf=False):
        source = self.root / "input.docx"
        _make_docx(source)
        doc, replacement = node("docx"), node("replace")
        doc["config"]["path"] = str(source)
        # Fixture contains NAME split across runs and COMPANY.
        replacement["config"]["rules"] = [{"find": "{{NAME}}", "replacement": "", "field": "contact.display_name"}, {"find": "{{COMPANY}}", "replacement": "", "field": "company.name"}]
        replacement["config"]["rules"].extend({"find": "{{" + key + "}}", "replacement": "Beispiel", "field": ""} for key in ("ROLE", "DATE", "UNKNOWN"))
        self.graph["nodes"].extend([doc, replacement])
        self.graph["edges"].extend([edge(doc, "file", replacement, "docx"), edge(self.graph["nodes"][0], "values", replacement, "values")])
        output = replacement
        if pdf:
            output = node("convert")
            self.graph["nodes"].append(output)
            self.graph["edges"].append(edge(replacement, "file", output, "docx"))
        self.graph["edges"].append(edge(output, "file", self.graph["nodes"][3], "attachments"))
        return source

    def test_preview_is_read_only_and_personalized(self):
        value = self.service.preview(self.graph)
        self.assertTrue(value["ready"])
        self.assertEqual(value["rows"][0]["subject"], "Bewerbung bei Ada GmbH")
        self.assertIn("Anschreiben Grace", value["rows"][1]["body"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM email_drafts").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM templates").fetchone()[0], 0)

    def test_local_group_uses_existing_bulk_with_no_jobs(self):
        batch = self.create()
        self.assertEqual(len(batch["items"]), 2)
        self.assertEqual(BulkMailService(self.project).batch(batch["id"])["items"][0]["recipients"]["to"], ["ada@example.test"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM email_jobs").fetchone()[0], 0)
        self.assertIn("builder_graph", batch["items"][0]["source_snapshot"])

    def test_saved_versions_immutable_stale_and_reopen(self):
        first = self.service.save("Ablauf", self.graph)["version"]
        self.graph["nodes"][1]["config"]["text"] = "Neuer Betreff"
        second = self.service.save("Ablauf", self.graph, builder_id=first["builder_id"], base_version_id=first["id"])["version"]
        self.assertEqual(second["version_number"], 2)
        self.assertNotEqual(self.service.version(first["id"])["graph"], second["graph"])
        with self.assertRaisesRegex(ValueError, "geändert"):
            self.service.save("Ablauf", self.graph, builder_id=first["builder_id"], base_version_id=first["id"])
        self.workspace.close()
        self.workspace.open(str(self.root / "project"))
        self.assertEqual(EmailBuilderService(self.workspace.project).version(second["id"])["graph"], self.graph)

    def test_saved_version_hash_tampering_rejected(self):
        version = self.service.save("Ablauf", self.graph)["version"]
        self.db.execute("UPDATE email_builder_versions SET content_hash='changed' WHERE id=?", (version["id"],))
        with self.assertRaisesRegex(ValueError, "verändert"):
            self.service.version(version["id"])

    def test_save_incomplete_graph_preview_requires_inputs(self):
        graph = {"nodes": [node("email")], "edges": []}
        self.service.save("Unfertig", graph)
        with self.assertRaisesRegex(ValueError, "fehlt"):
            self.service.preview(graph)

    def test_invalid_connector_duplicate_missing_node_and_cycle(self):
        for change in ("types", "duplicate", "missing", "cycle"):
            graph = deepcopy(self.graph)
            if change == "types":
                graph["edges"][0]["input"] = "subject"
            elif change == "duplicate":
                graph["edges"].append(graph["edges"][0])
            elif change == "missing":
                graph["edges"][0]["to"] = "absent"
            else:
                a, b = node("replace"), node("replace")
                graph["nodes"].extend([a, b])
                graph["edges"].extend([edge(a, "file", b, "docx"), edge(b, "file", a, "docx")])
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_graph(graph)

    def test_unconnected_nodes_and_multiple_sources_rejected(self):
        for kind in ("text", "data", "email"):
            graph = deepcopy(self.graph)
            graph["nodes"].append(node(kind))
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.service.preview(graph)

    def test_missing_fields_duplicates_and_bad_address_block_all(self):
        for key, value in (("company.name", ""), ("contact.email", "bad"), ("contact.email", "grace@example.test")):
            graph = deepcopy(self.graph)
            graph["nodes"][0]["config"]["sources"][0]["fields"][key] = value
            preview = self.service.preview(graph)
            self.assertFalse(preview["ready"])
            with self.assertRaises(ValueError):
                self.service.create("Blocked", graph, preview["fingerprint"])
            self.assertEqual(self.db.execute("SELECT COUNT(*) FROM email_drafts").fetchone()[0], 0)

    def test_html_escapes_values_not_template_markup_nonrecursive(self):
        self.graph["nodes"][2]["config"]["text"] = "<p>{{contact.display_name}}</p>"
        self.graph["nodes"][3]["config"]["body_format"] = "html"
        self.graph["nodes"][0]["config"]["sources"][0]["fields"]["contact.display_name"] = "<Ada> {{company.name}}"
        body = self.service.preview(self.graph)["rows"][0]["body"]
        self.assertEqual(body, "<p>&lt;Ada&gt; {{company.name}}</p>")

    def test_stale_file_and_list_block_capture(self):
        stored = DataSourceLibrary(self.db).save_list("Liste", [{"fields": s["fields"]} for s in self.graph["nodes"][0]["config"]["sources"]])["list"]
        self.graph["nodes"][0]["config"]["sources"] = [{"kind": "list", "list_id": stored["id"], "row_id": row["id"]} for row in stored["rows"]]
        preview = self.service.preview(self.graph)
        changed = deepcopy(stored["rows"])
        changed[0]["fields"]["company.name"] = "Neu"
        DataSourceLibrary(self.db).save_list("Liste", changed, list_id=stored["id"], expected_version=stored["version"])
        with self.assertRaisesRegex(ValueError, "geändert"):
            self.service.create("Stale", self.graph, preview["fingerprint"])
        attachment = node("file")
        path = self.root / "attachment.txt"
        path.write_text("old")
        attachment["config"]["path"] = str(path)
        self.graph["nodes"].append(attachment)
        self.graph["edges"].append(edge(attachment, "file", self.graph["nodes"][3], "attachments"))
        preview = self.service.preview(self.graph)
        path.write_text("new")
        with self.assertRaisesRegex(ValueError, "geändert"):
            self.service.create("Stale", self.graph, preview["fingerprint"])

    def test_word_replace_personal_attachments_registered_original_preserved(self):
        source = self.document_chain()
        original = source.read_bytes()
        preview = self.service.preview(self.graph)
        self.assertTrue(preview["ready"], preview["rows"])
        self.assertIn("Ada", preview["rows"][0]["documents"][0]["text"])
        self.assertNotIn("path", preview["rows"][0]["attachments"][0])
        batch = self.create()
        for item in batch["items"]:
            draft = MailService(self.project).draft(item["draft_id"])
            attachment = draft["configuration"]["attachments"][0]
            self.assertIn(item["name_snapshot"], extract_docx_text(self.project.file_path(attachment["path"])))
            self.assertTrue(attachment["document_id"])
        self.assertEqual(source.read_bytes(), original)
        from emailcenter.bulk_delivery import BulkDeliveryService
        from emailcenter.credentials import WindowsTokenStore
        from test_mail import FakeProvider, MemoryVault
        provider = FakeProvider()
        mail = MailService(self.project, token_store=WindowsTokenStore(self.project.project_id, backend=MemoryVault()), provider_factory=lambda account: provider)
        account = mail.register_account(provider.email, {"refresh_token": "test-only"})
        delivery = BulkDeliveryService(self.project, mail=mail)
        with patch.object(mail, "_provider", side_effect=AssertionError("No network during preparation")):
            state = delivery.begin(batch["id"], account["id"])
            for _ in batch["items"]:
                state = delivery.prepare_next(state["id"])
        self.assertEqual(state["status"], "Ready")
        self.assertTrue(all(item["job"]["approval_status"] == "pending" for item in state["items"]))
        self.assertEqual(provider.sent, [])
        self.assertIn("Ada GmbH", state["items"][0]["job"]["subject_snapshot"])

    def test_pdf_chain_uses_adapter_and_captures_real_final_hash(self):
        self.document_chain(pdf=True)
        converter = self.root / "soffice.exe"
        converter.write_bytes(b"test adapter")
        calls = []
        def convert(source, target, **options):
            calls.append(options)
            Path(target).write_bytes(b"%PDF-1.4\n" + extract_docx_text(source).encode())
            return Path(target)
        with patch("emailcenter.email_builder.convert_docx_to_pdf", side_effect=convert):
            preview = self.service.preview(self.graph, libreoffice_path=str(converter))
            self.assertEqual(calls, [])
            batch = self.create(libreoffice_path=str(converter))
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["timeout_seconds"], 120)
        draft = MailService(self.project).draft(batch["items"][0]["draft_id"])
        self.assertTrue(draft["configuration"]["attachments"][0]["hash"])

    def test_pdf_missing_converter_and_unresolved_document(self):
        self.document_chain(pdf=True)
        with patch("emailcenter.email_builder.find_libreoffice", return_value=None), self.assertRaisesRegex(ValueError, "LibreOffice"):
            self.service.preview(self.graph)
        self.graph["nodes"][-2]["config"]["rules"] = [{"find": "{{NAME}}", "replacement": "Ada", "field": ""}]
        converter = self.root / "soffice.exe"
        converter.write_bytes(b"adapter")
        self.assertFalse(self.service.preview(self.graph, libreoffice_path=str(converter))["ready"])

    def test_copy_failure_rolls_back_drafts_documents_and_templates(self):
        self.document_chain()
        preview = self.service.preview(self.graph)
        original = MailService._copy_attachments
        calls = []
        def copy(service, *args):
            calls.append(1)
            if len(calls) == 2:
                raise OSError("copy failed")
            return original(service, *args)
        with patch.object(MailService, "_copy_attachments", copy), self.assertRaises(OSError):
            self.service.create("Fail", self.graph, preview["fingerprint"])
        for table in ("email_drafts", "email_draft_batches", "documents", "templates"):
            self.assertEqual(self.db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0], 0)
        self.assertEqual([p for p in (self.project.path / "exports").rglob("*") if p.is_file()], [])

    def test_cancel_and_workspace_preview_consumed(self):
        with self.assertRaisesRegex(ValueError, "abgebrochen"):
            self.service.preview(self.graph, cancelled=lambda: True)
        preview = self.workspace.execute("builder_preview", {"graph": self.graph})
        self.workspace.execute("builder_create", {"name": "Single-use", "preview_id": preview["preview_id"]})
        with self.assertRaisesRegex(ValueError, "erneut"):
            self.workspace.execute("builder_create", {"name": "Twice", "preview_id": preview["preview_id"]})

    def test_direct_single_recipient_without_data(self):
        recipient, subject, body, email = node("recipient"), node("text"), node("text"), node("email")
        recipient["config"]["text"], subject["config"]["text"], body["config"]["text"] = "ada@example.test", "Hallo", "Direkter Text"
        self.graph = {"nodes": [recipient, subject, body, email], "edges": [edge(recipient, "email", email, "recipient"), edge(subject, "text", email, "subject"), edge(body, "text", email, "body")]}
        self.assertEqual(len(self.create()["items"]), 1)

    def test_personal_files_from_rows_body_order_and_internal_template_hidden(self):
        from emailcenter.mail_templates import MailTemplateService
        file = node("file")
        file["config"]["path"] = "{{attachment.path}}"
        for row in self.graph["nodes"][0]["config"]["sources"]:
            path = self.root / (row["fields"]["contact.display_name"] + ".txt")
            path.write_text(row["fields"]["contact.display_name"])
            row["fields"]["attachment.path"] = str(path)
        extra = node("text")
        extra["config"]["text"] = "Zweiter Text"
        self.graph["nodes"].extend([file, extra])
        self.graph["edges"].extend([edge(self.graph["nodes"][0], "values", file, "values"), edge(file, "file", self.graph["nodes"][3], "attachments"), edge(extra, "text", self.graph["nodes"][3], "body")])
        value = self.service.preview(self.graph)
        self.assertTrue(value["rows"][0]["body"].endswith("\n\nZweiter Text"))
        batch = self.create()
        for item in batch["items"]:
            attachment = MailService(self.project).draft(item["draft_id"])["configuration"]["attachments"][0]
            self.assertEqual(attachment["filename"], item["name_snapshot"] + ".txt")
        self.assertEqual(MailTemplateService(self.db).choices(), [])

    def test_excel_import_sources_keep_extra_columns_in_builder(self):
        from emailcenter.import_service import ImportService
        from emailcenter.bulk_sources import BulkSourceService
        path = self.root / "data.csv"
        path.write_text("Name;Email;Firma;Anschreiben\nAda;ada@example.test;Ada GmbH;Excel Brief", encoding="utf-8")
        importer = ImportService(self.project)
        run = importer.prepare(str(path), "contacts", {"display_name": "Name", "email": "Email"}, options={"delimiter": ";"})
        rows = importer.list_rows(run["id"])["rows"]
        mapping = {"contact.display_name": "Name", "contact.email": "Email", "company.name": "Firma", "application.cover_letter": "Anschreiben"}
        selected = BulkSourceService(self.db).select([r["id"] for r in rows], mapping)
        self.graph["nodes"][0]["config"]["sources"] = [c["source"] for c in selected["contacts"]]
        value = self.service.preview(self.graph)
        self.assertTrue(value["ready"])
        self.assertIn("Excel Brief", value["rows"][0]["body"])
        self.assertEqual(value["rows"][0]["source_snapshot"]["filename"], "data.csv")

    def test_mutation_during_pdf_capture_rolls_back(self):
        source = self.document_chain(pdf=True)
        converter = self.root / "soffice.exe"
        converter.write_bytes(b"adapter")
        preview = self.service.preview(self.graph, libreoffice_path=str(converter))
        def convert(original, target, **options):
            Path(target).write_bytes(b"%PDF-1.4\nexample")
            source.write_bytes(b"Changed source")
            return Path(target)
        with patch("emailcenter.email_builder.convert_docx_to_pdf", side_effect=convert), self.assertRaises(ValueError):
            self.service.create("Changed", self.graph, preview["fingerprint"], libreoffice_path=str(converter))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM email_drafts").fetchone()[0], 0)

    def test_attachment_type_limit_and_unsafe_ids(self):
        for identifier in ("../outside", "slash/id", "", "a" * 101):
            graph = deepcopy(self.graph)
            graph["nodes"][0]["id"] = identifier
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                validate_graph(graph)
        file = node("pdf")
        path = self.root / "fake.pdf"
        path.write_bytes(b"not a pdf")
        file["config"]["path"] = str(path)
        self.graph["nodes"].append(file)
        self.graph["edges"].append(edge(file, "file", self.graph["nodes"][3], "attachments"))
        self.assertFalse(self.service.preview(self.graph)["ready"])
        path = self.root / "too-large.pdf"
        path.write_bytes(b"%PDF-" + b"x" * (20 * 1024 * 1024))
        file["config"]["path"] = str(path)
        self.assertIn("20 MiB", self.service.preview(self.graph)["rows"][0]["error"])

    def test_builder_settings_roundtrip_and_validation(self):
        store = PreferencesStore(self.root / "settings.json")
        store.load()
        preferences = Preferences.validate({**Preferences().values(), "builder_grid": False, "builder_snap": False, "builder_zoom": 150})
        store.save(preferences)
        self.assertEqual(store.load()[0], preferences)
        for changes in ({"builder_grid": 1}, {"builder_snap": "yes"}, {"builder_zoom": True}, {"builder_zoom": 251}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                Preferences.validate({**Preferences().values(), **changes})

    def test_semantic_blocks_html_and_typed_subject(self):
        self.graph["nodes"][2]["kind"] = "description"
        self.graph["nodes"][2]["config"]["text"] = "<Text> {{contact.display_name}}\nZweite Zeile"
        self.graph["nodes"][3]["config"]["body_format"] = "html"
        heading, line, closing, html_block = node("heading"), node("separator"), node("closing"), node("html")
        heading["config"]["text"] = "Für {{company.name}}"
        closing["config"]["text"] = "Viele Grüße"
        html_block["config"]["text"] = "<b>{{contact.display_name}}</b>"
        self.graph["nodes"].extend([heading, line, closing, html_block])
        self.graph["edges"].extend([edge(self.graph["nodes"][0], "values", heading, "values"), edge(self.graph["nodes"][0], "values", html_block, "values")])
        self.graph["edges"].extend(edge(block, "text", self.graph["nodes"][3], "body") for block in (heading, line, closing, html_block))
        value = self.service.preview(self.graph)
        self.assertTrue(value["ready"], value["rows"])
        body = value["rows"][0]["body"]
        self.assertIn("&lt;Text&gt; Ada<br>Zweite Zeile", body)
        self.assertIn("<h2>Für Ada GmbH</h2>", body)
        self.assertIn("<hr>", body)
        self.assertIn("<b>Ada</b>", body)
        invalid = deepcopy(self.graph)
        invalid["edges"].append(edge(invalid["nodes"][1], "text", invalid["nodes"][3], "body"))
        with self.assertRaisesRegex(ValueError, "Stecker"):
            validate_graph(invalid)
        self.graph["nodes"][3]["config"]["body_format"] = "plain"
        self.assertIn("HTML", self.service.preview(self.graph)["rows"][0]["error"])

    def test_all_new_text_blocks_save_and_personal_preview(self):
        from emailcenter.email_builder import TEXT_KINDS
        for kind in TEXT_KINDS:
            graph = deepcopy(self.graph)
            if kind == "subject":
                graph["nodes"][1]["kind"] = kind
            else:
                graph["nodes"][2]["kind"] = kind
                if kind in ("link", "button"):
                    graph["nodes"][2]["config"]["url"] = "https://example.test"
                elif kind == "list":
                    graph["nodes"][2]["config"]["ordered"] = False
                graph["nodes"][3]["config"]["body_format"] = "html" if kind == "html" else "plain"
            with self.subTest(kind=kind):
                self.service.save(kind, graph)
                preview = self.service.preview(graph)
                self.assertTrue(preview["ready"], preview["rows"])
                self.assertIn("Anschreiben Ada", preview["rows"][0]["node_previews"][graph["nodes"][2]["id"]]["text"])

    def test_asset_autoload_rejects_changed_file_with_expected_preview_hash(self):
        from emailcenter.word_replace import file_hash
        pdf = node("pdf")
        source = self.root / "local.pdf"
        source.write_bytes(b"%PDF-1.4\npreview")
        pdf["config"]["path"] = str(source)
        graph = {"nodes": [pdf], "edges": []}
        checksum = file_hash(source)
        self.assertEqual(self.service.asset_preview(graph, pdf["id"], expected_hash=checksum)["content"], source.read_bytes())
        source.write_bytes(b"%PDF-1.4\nchanged")
        with self.assertRaisesRegex(ValueError, "wurde geändert"):
            self.service.asset_preview(graph, pdf["id"], expected_hash=checksum)

    def test_asset_preview_literal_media_and_personal_docx(self):
        self.document_chain()
        replacement = self.graph["nodes"][-1]
        result = self.service.asset_preview(self.graph, replacement["id"], row_number=2)
        self.assertEqual(result["format"], "text")
        self.assertIn("Grace", result["text"])
        self.assertNotIn("Ada", result["text"])
        pdf = node("pdf")
        source = self.root / "local.pdf"
        source.write_bytes(b"%PDF-1.4\npreview")
        pdf["config"]["path"] = str(source)
        graph = {"nodes": [pdf], "edges": []}
        result = self.service.asset_preview(graph, pdf["id"])
        self.assertEqual(result["content"], source.read_bytes())
        self.assertNotIn("path", result)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM email_jobs").fetchone()[0], 0)
        with self.assertRaises(ValueError):
            self.service.asset_preview(graph, "missing")

    def test_node_preview_hides_temporary_paths_and_pdf_metadata(self):
        self.document_chain(pdf=True)
        converter = self.root / "converter.exe"
        converter.write_bytes(b"adapter")
        value = self.service.preview(self.graph, libreoffice_path=str(converter))
        for row in value["rows"]:
            for preview in row["node_previews"].values():
                self.assertNotIn("path", preview)
                if preview.get("conversion"):
                    self.assertIsNone(preview["hash"])
                    self.assertIsNone(preview["size"])

    def account(self):
        from emailcenter.credentials import WindowsTokenStore
        from test_mail import MemoryVault
        mail = MailService(self.project, token_store=WindowsTokenStore(self.project.project_id, backend=MemoryVault()))
        return mail.register_account("sender@example.test", {"refresh_token": "test-only"})["id"]

    def test_builder_plan_atomic_and_persisted(self):
        account = self.account()
        preview = self.service.preview(self.graph, provider_account_id=account)
        plan = {"interval_seconds": 7, "scheduled_local": (datetime.now(timezone.utc) + timedelta(days=2)).replace(tzinfo=None, microsecond=0).isoformat(), "timezone_id": "UTC"}
        with patch.object(MailService, "_provider", side_effect=AssertionError("No provider")):
            value = self.service.create("Geplant", self.graph, preview["fingerprint"], provider_account_id=account, delivery_plan=plan)
        self.assertEqual(value["dispatch"]["status"], "Preparing")
        self.assertEqual(value["dispatch"]["interval_seconds"], 7)
        self.assertEqual(value["dispatch"]["scheduled_local"], plan["scheduled_local"])
        self.assertEqual(value["dispatch"]["counts"]["prepared"], 0)
        self.workspace.close()
        self.workspace.open(str(self.root / "project"))
        from emailcenter.bulk_delivery import BulkDeliveryService
        self.assertEqual(BulkDeliveryService(self.workspace.project).details(value["batch"]["id"])["dispatch"]["scheduled_local"], plan["scheduled_local"])

    def test_bad_plan_rolls_back_drafts_metadata_documents_and_files(self):
        self.document_chain()
        account = self.account()
        preview = self.service.preview(self.graph, provider_account_id=account)
        base = {"interval_seconds": 2, "scheduled_local": None, "timezone_id": "UTC"}
        for change in ({"interval_seconds": 0}, {"timezone_id": "Unknown/Zone"}, {"scheduled_local": "2000-01-01T12:00:00"}, {"extra": True}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.service.create("Ungültig", self.graph, preview["fingerprint"], provider_account_id=account, delivery_plan={**base, **change})
            for table in ("email_drafts", "email_draft_batches", "email_bulk_dispatches", "documents", "templates"):
                self.assertEqual(self.db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0], 0, table)
            self.assertEqual(list((self.project.path / "exports/mail/drafts").rglob("*.docx")), [])

    def test_workspace_plan_prepares_fixed_jobs_without_approval_or_sending(self):
        account = self.account()
        preview = self.workspace.builder_preview(graph=self.graph, provider_account_id=account)
        with patch.object(MailService, "_provider", side_effect=AssertionError("No provider")):
            value = self.workspace.builder_create("Sofort", preview["preview_id"], {"interval_seconds": 3, "scheduled_local": None, "timezone_id": "UTC"})
        self.assertEqual(value["dispatch"]["status"], "Ready")
        self.assertEqual(value["dispatch"]["counts"]["prepared"], 2)
        for item in value["dispatch"]["items"]:
            self.assertEqual(item["job"]["approval_status"], "pending")
            self.assertEqual(item["job"]["status"], "Draft")

    def test_plan_preparation_cancel_can_resume_without_duplicate_jobs(self):
        from emailcenter.bulk_delivery import BulkDeliveryService
        account = self.account()
        preview = self.workspace.builder_preview(graph=self.graph, provider_account_id=account)
        prepared = []
        original = BulkDeliveryService.prepare_next
        def step(delivery, identifier):
            value = original(delivery, identifier)
            prepared.append(identifier)
            return value
        self.workspace.cancel_requested = lambda: bool(prepared)
        with patch.object(BulkDeliveryService, "prepare_next", new=step):
            value = self.workspace.builder_create("Fortsetzen", preview["preview_id"], {"interval_seconds": 2, "scheduled_local": None, "timezone_id": "UTC"})
        self.assertEqual(value["dispatch"]["status"], "Preparing")
        self.assertEqual(value["dispatch"]["counts"]["prepared"], 1)
        state = BulkDeliveryService(self.project).prepare_next(value["dispatch"]["id"])
        self.assertEqual(state["status"], "Ready")
        self.assertEqual(state["counts"]["prepared"], 2)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM email_jobs").fetchone()[0], 2)

    def test_plan_without_account_leaves_no_partial_group(self):
        preview = self.service.preview(self.graph)
        with self.assertRaisesRegex(ValueError, "Gmail"):
            self.service.create("Fehlt", self.graph, preview["fingerprint"], delivery_plan={"interval_seconds": 2, "scheduled_local": None, "timezone_id": "UTC"})
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM email_draft_batches").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM email_drafts").fetchone()[0], 0)

    def test_theme_catalog_roundtrip_and_pairs(self):
        from emailcenter.appearance import THEMES, is_dark_theme, paired_theme
        store = PreferencesStore(self.root / "themes.json")
        store.load()
        for theme in THEMES:
            with self.subTest(theme=theme):
                preferences = Preferences.validate({**Preferences().values(), "theme": theme})
                store.save(preferences)
                self.assertEqual(store.load()[0].theme, theme)
                self.assertNotEqual(is_dark_theme(theme), is_dark_theme(paired_theme(theme)))
                self.assertEqual(paired_theme(paired_theme(theme)), theme)


if __name__ == "__main__":
    unittest.main()
