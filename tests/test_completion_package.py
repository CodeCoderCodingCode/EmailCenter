"""OAuth callbacks, common templates, captured tables and reviewed document bundles."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from emailcenter.application.workspace import WorkspaceService
from emailcenter.document_service import DocumentService
from emailcenter.document_tables import extract_tables
from emailcenter.document_bundle import DocumentBundleService
from emailcenter.builder_transfer import BuilderTransferService
from emailcenter.email_builder import node, starter_graph
from emailcenter.mail_templates import MailTemplateService
from emailcenter.oauth_callback import CallbackApp, completion_page, run_local_oauth
from emailcenter.preferences import Preferences, PreferencesStore
from emailcenter.shortcuts import validate_canvas_shortcuts
from test_documents import _make_docx


def table_docx(path, merged=False):
    cells = [["Name", "Email"], ["Ada", "ada@example.test"], ["Grace", "grace@example.test"]]
    xml = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:tbl>'
    for r, row in enumerate(cells):
        xml += "<w:tr>"
        for c, text in enumerate(row):
            xml += "<w:tc>" + ('<w:tcPr><w:gridSpan w:val="2"/></w:tcPr>' if merged and r == 0 and c == 0 else "") + "<w:p><w:r><w:t>" + text + "</w:t></w:r></w:p></w:tc>"
        xml += "</w:tr>"
    xml += "</w:tbl></w:body></w:document>"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return cells


def table_pdf(path):
    content = []
    for x in (50, 190, 400):
        content.append(f"{x} 660 m {x} 750 l S")
    for y in (750, 720, 690, 660):
        content.append(f"50 {y} m 400 {y} l S")
    for y, name, email in ((730, "Name", "Email"), (700, "Ada", "ada@example.test"), (670, "Grace", "grace@example.test")):
        for x, text in ((60, name), (200, email)):
            content.append(f"BT /F1 11 Tf {x} {y} Td ({text}) Tj ET")
    stream = "\n".join(content).encode()
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>", f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"]
    data, offsets = b"%PDF-1.4\n", [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(data)
    data += f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode()
    data += b"".join(f"{offset:010} 00000 n \n".encode() for offset in offsets[1:])
    data += f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    path.write_bytes(data)


class CallbackTests(unittest.TestCase):
    def call(self, app, query, path="/"):
        response = []
        body = b"".join(app({"REQUEST_METHOD": "GET", "PATH_INFO": path, "QUERY_STRING": query}, lambda status, headers: response.append((status, dict(headers)))))
        return response[0], body.decode()

    def test_success_page_is_honest_self_contained_and_does_not_show_codes(self):
        app = CallbackApp("secretstate", "http://127.0.0.1:1234/")
        (status, headers), body = self.call(app, "state=secretstate&code=private-code")
        self.assertEqual(status, "200 OK")
        self.assertIn("Google-Rückmeldung erhalten", body)
        self.assertIn("Abschluss in der App prüfen", body)
        self.assertIn("Tab schließen", body)
        self.assertIn("window.close()", body)
        self.assertIn("prefers-color-scheme:dark", body)
        self.assertIn("image-rendering:pixelated", body)
        self.assertIn("data:image/png;base64,", body)
        self.assertNotIn("private-code", body)
        self.assertNotIn("secretstate", body)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertTrue(app.response.startswith("https://127.0.0.1:1234/"))

    def test_bad_state_duplicate_parameters_and_other_paths_are_ignored(self):
        for query in ("state=wrong&code=x", "state=ok&code=a&code=b", "state=ok&code=x&error=no", "state=ok", "state=%C3%A4&code=x", "code=x"):
            with self.subTest(query=query):
                app = CallbackApp("ok", "http://127.0.0.1:1234/")
                (status, _), _ = self.call(app, query)
                self.assertEqual(status, "400 Bad Request")
                self.assertIsNone(app.response)
        app = CallbackApp("ok", "http://127.0.0.1:1234/")
        self.call(app, "state=ok&code=x", "/favicon.ico")
        self.assertIsNone(app.response)

    def test_denied_page_and_no_js_fallback(self):
        app = CallbackApp("ok", "http://127.0.0.1:1234/")
        _, body = self.call(app, "state=ok&error=access_denied")
        self.assertIn("Anmeldung abgebrochen", body)
        self.assertIn("<noscript>", body)
        self.assertIn("Strg+W", body)

    def test_runner_uses_exclusive_loopback_and_state_before_fetch(self):
        flow, server, browser = MagicMock(), MagicMock(), MagicMock()
        server.__enter__.return_value = server
        server.server_port = 43210
        flow.authorization_url.return_value = ("https://accounts.google.com/authorize", "ok")
        callback = None
        def set_app(app):
            nonlocal callback
            callback = app
        server.set_app.side_effect = set_app
        server.handle_request.side_effect = lambda: self.call(callback, "state=ok&code=synthetic")
        with patch("emailcenter.oauth_callback.make_server", return_value=server) as create:
            result = run_local_oauth(flow, open_browser=browser)
        self.assertEqual(create.call_args.args[:2], ("127.0.0.1", 0))
        self.assertEqual(flow.redirect_uri, "http://127.0.0.1:43210/")
        flow.authorization_url.assert_called_once_with(prompt="consent", access_type="offline")
        browser.assert_called_once_with("https://accounts.google.com/authorize", new=1, autoraise=True)
        flow.fetch_token.assert_called_once_with(authorization_response="https://127.0.0.1:43210/?state=ok&code=synthetic")
        self.assertIs(result, flow.credentials)
        server.__exit__.assert_called_once()

    def test_runner_timeout_does_not_fetch_token(self):
        flow, server = MagicMock(), MagicMock()
        server.__enter__.return_value = server
        server.server_port = 1234
        flow.authorization_url.return_value = ("url", "state")
        with patch("emailcenter.oauth_callback.make_server", return_value=server), self.assertRaises(TimeoutError):
            run_local_oauth(flow, timeout_seconds=0, open_browser=MagicMock())
        flow.fetch_token.assert_not_called()
        server.__exit__.assert_called_once()


class CompletionCoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.root = Path(self.temp.name)
        self.workspace = WorkspaceService()
        self.workspace.create(str(self.root / "project"), "Paket")
        self.project = self.workspace.project
        self.documents = DocumentService(self.project)

    def tearDown(self):
        self.workspace.close()
        self.temp.cleanup()

    def template(self):
        path = self.root / "template.docx"
        _make_docx(path)
        return self.documents.import_template(path, name="Gemeinsam", mapping={"NAME": "contact.display_name"}, required_placeholders=["NAME"])["version"]

    def generated(self, with_pdf=False):
        version = self.template()
        _, doc = self.documents.generate_document(version["id"], {"NAME": "Ada"}, output_filename="Anschreiben.docx")
        if with_pdf:
            def convert(source, target, **kwargs):
                table_pdf(Path(target))
            with patch("emailcenter.document_service.convert_docx_to_pdf", side_effect=convert):
                self.documents.create_pdf_version(doc["id"])
        return doc

    def test_common_search_filter_versions_and_literal_percent(self):
        version = self.template()
        mail = MailTemplateService(self.project.connection).save(name="Gemeinsam Mail", subject="Hallo", body="Text")
        self.assertEqual(self.workspace.list_records("templates", template_type="all", search="gemeinsam")["total"], 2)
        rows = self.workspace.list_records("templates", template_type="email")["rows"]
        self.assertEqual(rows[0]["template_type"], "email")
        self.assertEqual(self.workspace.list_records("templates")["total"], 1)
        self.assertEqual(self.workspace.list_records("templates", template_type="all", search="%")["total"], 0)
        self.assertEqual(self.workspace.list_records("templates", template_type="all", limit=1, offset=1)["total"], 2)
        with self.assertRaises(ValueError):
            self.workspace.list_records("templates", template_type="workflow")

    def test_docx_duplicate_preserves_mapping_and_hash_and_original(self):
        original = self.template()
        before = dict(self.documents.templates.get_version(original["id"]))
        result = self.workspace.document_template_duplicate(original["id"])
        copy = result["version"]
        self.assertNotEqual(copy["template_id"], original["template_id"])
        self.assertNotEqual(copy["file_path"], original["file_path"])
        self.assertEqual(copy["content_hash"], original["content_hash"])
        self.assertEqual(json.loads(copy["configuration_json"]), json.loads(original["configuration_json"]))
        self.assertEqual(self.documents.templates.get_version(original["id"]), before)

    def test_changed_docx_cannot_be_duplicated(self):
        original = self.template()
        self.project.file_path(original["file_path"]).write_bytes(b"changed")
        with self.assertRaisesRegex(Exception, "changed"):
            self.documents.duplicate_template(original["id"])
        self.assertEqual(self.workspace.list_records("templates")["total"], 1)

    def test_docx_duplicate_detects_change_during_capture_and_leaves_no_new_version(self):
        original = self.template()
        source = self.project.file_path(original["file_path"])
        import shutil
        copyfile = shutil.copyfile
        def changed(src, target):
            Path(src).write_bytes(Path(src).read_bytes() + b"changed")
            return copyfile(src, target)
        with patch("emailcenter.document_service.shutil.copyfile", side_effect=changed), self.assertRaisesRegex(Exception, "changed"):
            self.documents.duplicate_template(original["id"])
        self.assertEqual(self.workspace.list_records("templates")["total"], 1)
        self.assertEqual(list((self.project.path / "tmp").glob("duplicate-*.docx")), [])

    def test_extract_docx_cells_and_merged_warning(self):
        path = self.root / "rows.docx"
        expected = table_docx(path)
        value = extract_tables(path)
        self.assertEqual(value["tables"][0]["rows"], expected)
        self.assertEqual(value["filename"], "rows.docx")
        self.assertEqual(len(value["sha256"]), 64)
        table_docx(path, merged=True)
        value = extract_tables(path)
        self.assertTrue(value["tables"][0]["warnings"])
        self.assertEqual(value["tables"][0]["rows"][0], ["Name", "", "Email"])
        with zipfile.ZipFile(path) as archive:
            content = archive.read("word/document.xml").replace(b"Name", b"Na</w:t><w:br/><w:t>me")
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("word/document.xml", content)
        self.assertEqual(extract_tables(path)["tables"][0]["rows"][0][0], "Na\nme")

    def test_real_pdf_table_extraction_with_lines_and_text(self):
        path = self.root / "table.pdf"
        table_pdf(path)
        for strategy in ("lines", "text"):
            with self.subTest(strategy=strategy):
                value = extract_tables(path, pdf_strategy=strategy)
                self.assertTrue(value["tables"][0]["warnings"])
                self.assertEqual(value["tables"][0]["page"], 1)
                text = str(value["tables"][0]["rows"])
                self.assertIn("Ada", text)
                self.assertIn("ada@example.test", text)

    def test_invalid_no_table_and_cancelled_sources(self):
        path = self.root / "bad.docx"
        path.write_bytes(b"invalid")
        with self.assertRaises(Exception):
            extract_tables(path)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p/></w:body></w:document>')
        with self.assertRaisesRegex(Exception, "Keine strukturierte"):
            extract_tables(path)
        table_docx(path)
        with self.assertRaisesRegex(Exception, "abgebrochen"):
            extract_tables(path, cancelled=lambda: True)

    def test_bundle_selection_includes_pdf_variant_and_safe_manifest(self):
        doc = self.generated(with_pdf=True)
        value = self.workspace.document_bundle_preview(selected_ids=[doc["id"]])
        self.assertEqual(value["count"], 2)
        self.assertEqual(value["warnings"], [])
        target = self.project.path / "exports" / "paket.zip"
        result = self.workspace.document_bundle_write(value["preview_id"], target_path=str(target))
        self.assertEqual(result["count"], 2)
        with zipfile.ZipFile(target) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(len(manifest["documents"]), 2)
            self.assertNotIn("file_path", str(manifest))
            self.assertNotIn("oauth", str(manifest).lower())
            self.assertTrue(all(not name.startswith(("/", "..")) for name in archive.namelist()))
        with self.assertRaises(ValueError):
            self.workspace.document_bundle_write(value["preview_id"], target_path=str(target), overwrite=True)

    def test_missing_pdf_requires_explicit_incomplete_confirmation(self):
        doc = self.generated()
        value = self.workspace.document_bundle_preview()
        self.assertTrue(any("PDF-Version fehlt" in warning for warning in value["warnings"]))
        target = self.project.path / "exports" / "paket.zip"
        with self.assertRaisesRegex(Exception, "ausdrücklich"):
            self.workspace.document_bundle_write(value["preview_id"], target_path=str(target))
        self.assertFalse(target.exists())
        result = self.workspace.document_bundle_write(value["preview_id"], target_path=str(target), allow_incomplete=True)
        self.assertEqual(result["count"], 1)
        with zipfile.ZipFile(target) as archive:
            self.assertIn("PDF-Version fehlt", archive.read("Exportbericht.txt").decode())

    def test_stale_bundle_and_project_switch_invalidate_review(self):
        doc = self.generated()
        value = self.workspace.document_bundle_preview(formats=["docx"])
        self.project.file_path(doc["file_path"]).write_bytes(b"changed")
        target = self.root / "stale.zip"
        with self.assertRaisesRegex(ValueError, "verändert"):
            self.workspace.document_bundle_write(value["preview_id"], target_path=str(target))
        self.assertFalse(target.exists())
        value = self.workspace.document_bundle_preview()
        self.workspace.close()
        self.workspace.open(str(self.root / "project"))
        with self.assertRaisesRegex(ValueError, "erneut"):
            self.workspace.document_bundle_write(value["preview_id"], target_path=str(target))

    def test_bundle_cancel_and_failed_replace_preserve_existing_target(self):
        self.generated()
        service = DocumentBundleService(self.project)
        value = service.preview(formats=["docx"])
        target = self.root / "existing.zip"
        target.write_bytes(b"original")
        with self.assertRaisesRegex(Exception, "abgebrochen"):
            service.write(value, target, overwrite=True, cancelled=lambda: True)
        with patch("emailcenter.document_bundle.os.replace", side_effect=PermissionError()), self.assertRaises(PermissionError):
            service.write(value, target, overwrite=True)
        self.assertEqual(target.read_bytes(), b"original")
        self.assertEqual(list(self.root.glob(".emailcenter-documents-*")), [])

    def test_bundle_guarded_destination_and_missing_file_report(self):
        doc = self.generated()
        service = DocumentBundleService(self.project)
        value = service.preview(formats=["docx"])
        for target in ("relative.zip", str(self.project.path / "project.zip"), str(self.root / "wrong.csv")):
            with self.subTest(target=target), self.assertRaises(Exception):
                service.write(value, target)
        self.project.file_path(doc["file_path"]).unlink()
        value = service.preview()
        self.assertEqual(value["count"], 0)
        self.assertIn("fehlt", value["warnings"][0])

    def test_document_bundle_filter_matches_sets_and_escapes_wildcards(self):
        self.generated(with_pdf=True)
        service = DocumentBundleService(self.project)
        self.assertEqual(service.preview(search="Anschreiben")["count"], 2)
        self.assertEqual(service.preview(search="%") ["count"], 0)
        self.assertEqual(service.preview(formats=["docx"])["count"], 1)
        with self.assertRaises(Exception):
            service.preview(selected_ids=["missing"])

    def test_canvas_bindings_conflicts_disabled_legacy_and_roundtrip(self):
        keys = validate_canvas_shortcuts({"connect": "Enter", "next_node": "Ctrl+M"})
        self.assertEqual(keys["connect"], "Return")
        for value in ({"connect": "Ctrl+N"}, {"next_node": "Alt+Left"}, {"cancel": "Alt+F4"}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_canvas_shortcuts(value)
        store = PreferencesStore(self.root / "prefs.json")
        store.load()
        values = Preferences.validate({**Preferences().values(), "shortcuts": {"refresh": "Ctrl+0"}, "canvas_shortcuts": {"fit": "Alt+0", "connect": ""}})
        store.save(values)
        self.assertEqual(PreferencesStore(store.path).load(), (values, None))
        store.path.write_text(json.dumps({"version": 1, "theme": "dark", "accent": "#2862c4", "timezone_id": "UTC", "shortcuts": {"refresh": "Ctrl+0"}}))
        loaded, warning = PreferencesStore(store.path).load()
        self.assertEqual(loaded.shortcuts["refresh"], "Ctrl+0")
        self.assertEqual(loaded.canvas_shortcuts["fit"], "")
        self.assertIn("canvas_shortcuts", warning)

    def test_graph_transfer_retains_nodes_rules_and_layout_but_requires_new_sources(self):
        graph = starter_graph()
        graph["nodes"][0]["config"]["sources"] = [{"kind": "manual", "fields": {"contact.email": "private@example.test", "secret": "synthetic-secret"}}]
        attachment = node("docx", 1200, 350)
        attachment["config"]["path"] = str(self.root / "private.docx")
        graph["nodes"].append(attachment)
        path = self.root / "transfer.json"
        service = BuilderTransferService(self.project)
        original = deepcopy(graph)
        service.export(name="Ablauf", graph=graph, target_path=str(path))
        self.assertNotIn("private@example.test", path.read_text())
        self.assertNotIn("synthetic-secret", path.read_text())
        self.assertNotIn("private.docx", path.read_text())
        self.assertEqual(graph, original)
        imported = service.import_file(str(path))
        self.assertEqual(imported["name"], "Ablauf")
        self.assertEqual(imported["graph"]["nodes"][0]["config"]["sources"], [])
        self.assertEqual(imported["graph"]["nodes"][-1]["config"]["path"], "")
        self.assertEqual(imported["graph"]["edges"], graph["edges"])
        self.assertEqual(len(imported["sources"]), 2)

    def test_graph_import_strips_external_sources_even_in_handwritten_files(self):
        graph = starter_graph()
        graph["nodes"][0]["config"]["sources"] = [{"kind": "list", "list_id": "unrelated-project-id", "row_id": "old-row"}]
        image = node("image")
        image["config"]["path"] = "C:/private/image.png"
        graph["nodes"].append(image)
        path = self.root / "manual.json"
        path.write_text(json.dumps({"format": "emailcenter.builder", "version": 1, "name": "Ablauf", "graph": graph}))
        imported = BuilderTransferService(self.project).import_file(str(path))
        self.assertEqual(imported["graph"]["nodes"][0]["config"]["sources"], [])
        self.assertEqual(imported["graph"]["nodes"][-1]["config"]["path"], "")

    def test_graph_import_rejects_unknown_versions_duplicate_json_and_bad_edges(self):
        service = BuilderTransferService(self.project)
        path = self.root / "invalid.json"
        payload = {"format": "emailcenter.builder", "version": 1, "name": "Ablauf", "graph": starter_graph()}
        cases = ["invalid", '{"version":1,"version":2}', json.dumps({**payload, "version": True}), json.dumps({**payload, "version": 99}), json.dumps({**payload, "token": "no"})]
        malformed = deepcopy(payload)
        malformed["graph"]["edges"][0]["output"] = "missing"
        cases.append(json.dumps(malformed))
        for content in cases:
            with self.subTest(content=content[:40]):
                path.write_text(content)
                with self.assertRaisesRegex(Exception, "Ungültige"):
                    service.import_file(str(path))

    def test_graph_export_overwrite_cancel_and_protected_paths(self):
        service = BuilderTransferService(self.project)
        path = self.root / "graph.json"
        path.write_bytes(b"original")
        options = {"name": "Ablauf", "graph": starter_graph(), "target_path": str(path)}
        with self.assertRaises(Exception):
            service.export(**options)
        with self.assertRaisesRegex(Exception, "abgebrochen"):
            service.export(**options, overwrite=True, cancelled=lambda: True)
        self.assertEqual(path.read_bytes(), b"original")
        self.assertEqual(list(self.root.glob(".emailcenter-graph-*")), [])
        with self.assertRaisesRegex(Exception, "exports"):
            service.export(**{**options, "target_path": str(self.project.path / "graph.json")})
