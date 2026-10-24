"""CSV/XLSX parsing, durable previews and restart-safe import receipts."""

from datetime import datetime
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from emailcenter.database import ApplicationRepository, CompanyRepository
from emailcenter.import_sources import ImportSourceError, read_source, suggest_mapping
from emailcenter.import_service import ImportService, ImportServiceError
from emailcenter.project import create_project, open_project

try:
    from openpyxl import Workbook
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.directory = Path(self.temporary.name)
        self.project = create_project(self.directory / "project")
        self.service = ImportService(self.project)

    def tearDown(self):
        self.project.close()
        self.temporary.cleanup()

    def csv(self, text, encoding="utf-8-sig"):
        source = self.directory / "source.csv"
        source.write_text(text, encoding=encoding)
        return source

    def prepare_contacts(self, text):
        source = self.csv(text)
        return self.service.prepare(str(source), "contacts", {"display_name": "Name", "email": "E-Mail"})

    def test_csv_encoding_delimiter_quotes_and_blank_rows(self):
        source = self.csv('Name;Notizen\nMüller;"Hallo; Welt\nzweite Zeile"\n;\n', "cp1252")
        table = read_source(source)
        self.assertEqual(table.options, {"encoding": "cp1252", "delimiter": ";"})
        self.assertEqual(table.rows[0].values["Name"], "Müller")
        self.assertEqual(table.rows[0].values["Notizen"], "Hallo; Welt\nzweite Zeile")
        self.assertEqual(table.rows[1].number, 3)

    def test_duplicate_and_empty_headers_are_rejected(self):
        for text in ("Name,name\nAda,Other", "Name,\nAda,Other", "\n"):
            with self.subTest(text=text), self.assertRaises(ImportSourceError):
                read_source(self.csv(text))

    def test_suggestions_only_use_unambiguous_headers(self):
        self.assertEqual(suggest_mapping(("Name", "E-Mail", "Telefon"), "contacts"),
                         {"display_name": "Name", "email": "E-Mail", "phone": "Telefon"})
        self.assertNotIn("email", suggest_mapping(("Name", "Email", "E-Mail"), "contacts"))

    def test_preview_logs_invalid_duplicate_and_empty_rows_without_creating_records(self):
        run = self.prepare_contacts("Name,E-Mail\nAda,ada@example.test\nGrace,bad-mail\nAda Again,ADA@example.test\n,\n")
        self.assertEqual(run["counts"], {"Valid": 1, "Invalid": 1, "DuplicateReview": 1, "Skipped": 1})
        rows = self.service.list_rows(run["id"])["rows"]
        self.assertEqual([r["row_number"] for r in rows], [2, 3, 4, 5])
        self.assertIn("Ungültige E-Mail", rows[1]["errors"][0])
        self.assertEqual(self.project.connection.execute("SELECT COUNT(*) FROM contacts").fetchone()[0], 0)
        self.assertTrue(self.project.file_path(run["source_file_path"]).is_file())

    def test_extra_cells_are_logged_as_invalid_instead_of_discarded(self):
        source = self.csv("Name\nAda,unmapped-extra\n")
        run = self.service.prepare(str(source), "contacts", {"display_name": "Name"})
        self.assertEqual(run["counts"], {"Invalid": 1})
        self.assertIn("Zusätzliche Zellen", self.service.list_rows(run["id"])["rows"][0]["errors"][0])

    def test_mapping_validation_and_changed_source_leave_no_run(self):
        source = self.csv("Name,E-Mail\nAda,ada@example.test\n")
        inspection = self.service.inspect(str(source))
        for mapping in ({}, {"display_name": "Missing"}, {"display_name": "Name", "email": "Name"}):
            with self.subTest(mapping=mapping), self.assertRaises(ImportServiceError):
                self.service.prepare(str(source), "contacts", mapping)
        source.write_text("Name,E-Mail\nChanged,changed@example.test\n", encoding="utf-8")
        with self.assertRaisesRegex(ImportServiceError, "seit der Vorschau"):
            self.service.prepare(str(source), "contacts", {"display_name": "Name"}, expected_hash=inspection["source_hash"])
        self.assertEqual(self.service.list_runs()["total"], 0)
        self.assertEqual(list((self.project.path / "imports").rglob("*.csv")), [])

    def test_batch_resume_after_reopen_uses_fixed_profile_snapshot(self):
        source = self.csv("Name,E-Mail\nAda,ada@example.test\nGrace,grace@example.test\nLinus,linus@example.test\n")
        run = self.service.prepare(str(source), "contacts", {"display_name": "Name", "email": "E-Mail"}, profile_name="Contacts")
        self.service.process(run["id"], max_rows=1)
        self.project.connection.execute("UPDATE import_profiles SET mapping_json='{}',options_json='{}'")
        source.unlink()
        project_path = self.project.path
        self.project.close()
        self.project = open_project(project_path)
        self.service = ImportService(self.project)
        resumed = self.service.process(run["id"])
        self.assertEqual(resumed["status"], "Completed")
        self.assertEqual(resumed["counts"], {"Imported": 3})
        self.assertEqual(resumed["configuration"]["mapping"]["email"], "E-Mail")
        self.service.process(run["id"])
        self.assertEqual(self.project.connection.execute("SELECT COUNT(*) FROM contacts").fetchone()[0], 3)

    def test_pause_preserves_committed_rows_and_can_continue(self):
        run = self.prepare_contacts("Name,E-Mail\nAda,ada@example.test\nGrace,grace@example.test\nLinus,linus@example.test\n")
        calls = []
        def cancelled():
            calls.append(True)
            return len(calls) > 2
        result = self.service.process(run["id"], cancelled=cancelled)
        self.assertTrue(result["paused"])
        self.assertEqual(result["counts"], {"Imported": 2, "Valid": 1})
        self.assertEqual(result["status"], "Pending")
        self.assertEqual(self.service.process(run["id"])["counts"], {"Imported": 3})

    def test_duplicate_check_handles_unicode_and_new_project_records(self):
        CompanyRepository(self.project.connection).create("Müller GmbH")
        source = self.csv("Firma\nMÜLLER   GMBH\nNew Company\n")
        run = self.service.prepare(str(source), "companies", {"name": "Firma"})
        self.assertEqual(run["counts"], {"DuplicateReview": 1, "Valid": 1})
        CompanyRepository(self.project.connection).create("New Company")
        result = self.service.process(run["id"])
        self.assertEqual(result["counts"], {"DuplicateReview": 2})
        self.assertEqual(self.project.connection.execute("SELECT COUNT(*) FROM companies").fetchone()[0], 2)

    def test_duplicate_decisions_are_explicit_and_not_replayed(self):
        run = self.prepare_contacts("Name,E-Mail\nAda,ada@example.test\nAda Again,ada@example.test\n")
        self.service.process(run["id"])
        rows = self.service.list_rows(run["id"])["rows"]
        with self.assertRaises(ImportServiceError):
            self.service.edit_row(rows[0]["id"], {"display_name": "Changed"})
        self.service.review_row(rows[1]["id"], "import_new")
        self.service.process(run["id"])
        self.service.process(run["id"])
        self.assertEqual(self.project.connection.execute("SELECT COUNT(*) FROM contacts").fetchone()[0], 2)
        self.assertTrue(self.service.list_rows(run["id"])["rows"][1]["mapped_data"]["allow_duplicate"])

    def test_invalid_row_can_be_corrected_without_changing_source_log(self):
        run = self.prepare_contacts("Name,E-Mail\nAda,bad-mail\n")
        row = self.service.list_rows(run["id"])["rows"][0]
        updated = self.service.edit_row(row["id"], {"display_name": "Ada", "email": "ada@example.test"})
        self.assertEqual(updated["counts"], {"Valid": 1})
        self.service.process(run["id"])
        row = self.service.list_rows(run["id"])["rows"][0]
        self.assertEqual(row["source_data"]["E-Mail"], "bad-mail")
        self.assertEqual(row["mapped_data"]["fields"]["email"], "ada@example.test")

    def test_skip_decision_is_logged_and_not_imported(self):
        run = self.prepare_contacts("Name,E-Mail\nAda,bad-mail\n")
        row = self.service.list_rows(run["id"])["rows"][0]
        self.service.review_row(row["id"], "skip")
        self.assertEqual(self.service.process(run["id"])["status"], "Completed")
        self.assertEqual(self.project.connection.execute("SELECT COUNT(*) FROM contacts").fetchone()[0], 0)
        self.assertIn("Benutzer", self.service.list_rows(run["id"])["rows"][0]["errors"][0])

    def test_receipt_failure_rolls_back_record_then_retry_imports_once(self):
        run = self.prepare_contacts("Name,E-Mail\nAda,ada@example.test\n")
        self.project.connection.execute("CREATE TRIGGER reject_receipt BEFORE UPDATE OF status ON import_rows "
                                        "WHEN NEW.status='Imported' BEGIN SELECT RAISE(ABORT,'receipt failed'); END")
        result = self.service.process(run["id"])
        self.assertEqual(result["counts"], {"Failed": 1})
        self.assertEqual(self.project.connection.execute("SELECT COUNT(*) FROM contacts").fetchone()[0], 0)
        self.project.connection.execute("DROP TRIGGER reject_receipt")
        row = self.service.list_rows(run["id"])["rows"][0]
        self.service.edit_row(row["id"], row["mapped_data"]["fields"])
        self.service.process(run["id"])
        self.service.process(run["id"])
        self.assertEqual(self.project.connection.execute("SELECT COUNT(*) FROM contacts").fetchone()[0], 1)

    def test_application_import_resolves_references_dates_and_provenance(self):
        company = CompanyRepository(self.project.connection).create("Example GmbH")
        source = self.csv("Stelle,Firma,Datum,Status\nEngineer,Example GmbH,11.10.2026,interview\nOther,Missing,invalid,unknown\n")
        run = self.service.prepare(str(source), "applications", {
            "title": "Stelle", "company_name": "Firma", "application_date": "Datum", "status_code": "Status"})
        self.assertEqual(run["counts"], {"Valid": 1, "Invalid": 1})
        result = self.service.process(run["id"])
        self.assertEqual(result["status"], "CompletedWithErrors")
        application = ApplicationRepository(self.project.connection).list()[0]
        self.assertEqual(application["company_id"], company["id"])
        self.assertEqual(application["application_date"], "2026-10-11")
        self.assertEqual(application["status_code"], "interview")
        row = self.service.list_rows(run["id"])["rows"][0]
        self.assertEqual(row["created_record_id"], application["id"])
        self.assertEqual(row["created_record_type"], "applications")

    def test_application_receipt_failure_rolls_back_activity_and_application(self):
        source = self.csv("Stelle\nEngineer\n")
        run = self.service.prepare(str(source), "applications", {"title": "Stelle"})
        self.project.connection.execute("CREATE TRIGGER reject_receipt BEFORE UPDATE OF status ON import_rows "
                                        "WHEN NEW.status='Imported' BEGIN SELECT RAISE(ABORT,'rejected'); END")
        self.service.process(run["id"])
        for table in ("applications", "activity_log"):
            self.assertEqual(self.project.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)

    @unittest.skipUnless(EXCEL_AVAILABLE, "openpyxl missing")
    def test_xlsx_sheets_dates_formulas_and_zero_cells(self):
        path = self.directory / "source.xlsx"
        workbook = Workbook()
        workbook.active.title = "Other"
        workbook.active.append(["Unused"])
        sheet = workbook.create_sheet("Applications")
        sheet.append(["Stelle", "Datum", "Notizen"])
        sheet.append(["Engineer", datetime(2026, 10, 11), 0])
        sheet.append(["Other", "=TODAY()", "formula"])
        workbook.save(path)
        workbook.close()
        table = read_source(path, {"sheet": "Applications"})
        self.assertEqual(table.sheets, ("Other", "Applications"))
        self.assertEqual(table.rows[0].values["Notizen"], "0")
        run = self.service.prepare(str(path), "applications", {"title": "Stelle", "application_date": "Datum", "notes": "Notizen"}, options={"sheet": "Applications"})
        self.assertEqual(run["counts"], {"Valid": 1, "Invalid": 1})
        self.assertIn("Formel", self.service.list_rows(run["id"])["rows"][1]["errors"][0])
        self.service.process(run["id"])
        self.assertEqual(ApplicationRepository(self.project.connection).list()[0]["application_date"], "2026-10-11")

    def test_transactional_application_entry_requires_a_transaction(self):
        repository = ApplicationRepository(self.project.connection)
        with self.assertRaises(RuntimeError):
            repository.create_in_transaction("Engineer")
        self.project.connection.execute("BEGIN")
        try:
            repository.create_in_transaction("Engineer")
            with self.assertRaises(RuntimeError):
                repository.create("Other")
        finally:
            self.project.connection.rollback()
        self.assertEqual(repository.list(), [])

    def test_duplicate_index_reuses_one_scan_for_a_batch(self):
        run = self.prepare_contacts("Name,E-Mail\n" + "".join(f"Person {i},p{i}@example.test\n" for i in range(40)))
        statements = []
        self.project.connection.set_trace_callback(statements.append)
        try:
            self.service.process(run["id"])
        finally:
            self.project.connection.set_trace_callback(None)
        scans = [statement for statement in statements if statement.startswith("SELECT id,display_name,email,phone FROM contacts")]
        self.assertEqual(len(scans), 1)

    def test_duplicate_index_detects_records_committed_by_another_connection(self):
        source = self.csv("Firma\nNew Company\n")
        run = self.service.prepare(str(source), "companies", {"name": "Firma"})
        with open_project(self.project.path) as other:
            CompanyRepository(other.connection).create("New Company")
        self.assertEqual(self.service.process(run["id"])["counts"], {"DuplicateReview": 1})

    def test_error_does_not_discard_other_valid_rows(self):
        run = self.prepare_contacts("Name,E-Mail\nAda,ada@example.test\nGrace,grace@example.test\n")
        self.project.connection.execute("CREATE TRIGGER reject_contact BEFORE INSERT ON contacts WHEN NEW.display_name='Ada' "
                                        "BEGIN SELECT RAISE(ABORT,'rejected'); END")
        result = self.service.process(run["id"])
        self.assertEqual(result["counts"], {"Failed": 1, "Imported": 1})
        self.assertEqual(self.project.connection.execute("SELECT display_name FROM contacts").fetchone()[0], "Grace")


if __name__ == "__main__":
    unittest.main()
