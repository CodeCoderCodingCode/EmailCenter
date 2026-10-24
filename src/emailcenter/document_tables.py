"""Capture structured DOCX/PDF tables for explicit, reviewed field mapping."""

from .language import translate as _ui_tr, format_text as _ui_format

import hashlib
import io
from pathlib import Path
import zipfile
from defusedxml import ElementTree as ET

from .documents import WORD_NAMESPACE
from .mail_models import MailError

W = "{" + WORD_NAMESPACE + "}"


def extract_tables(path, *, pdf_strategy="lines", cancelled=lambda: False):
    source = Path(path)
    if source.suffix.lower() not in (".docx", ".pdf") or not source.is_file():
        raise MailError(_ui_tr('Eine vorhandene DOCX- oder PDF-Datei auswählen.'))
    if source.stat().st_size > 20 * 1024 * 1024:
        raise MailError(_ui_tr('Tabellenquelle ist größer als 20 MiB.'))
    with source.open("rb") as stream:
        content = stream.read(20 * 1024 * 1024 + 1)
    if len(content) > 20 * 1024 * 1024:
        raise MailError(_ui_tr('Tabellenquelle ist größer als 20 MiB.'))
    if pdf_strategy not in ("lines", "text"):
        raise MailError(_ui_tr('Ungültige PDF-Erkennung.'))
    result = {"filename": source.name, "sha256": hashlib.sha256(content).hexdigest(), "tables": []}

    def add(rows, title, page=None, warnings=()):
        if not rows or not any(any(cell for cell in row) for row in rows):
            return
        width = max(map(len, rows))
        if width > 30 or len(rows) > 1000 or len(result["tables"]) >= 50:
            raise MailError(_ui_tr('Maximal 50 Tabellen, 1000 Zeilen je Tabelle und 30 Spalten; Quelle aufteilen.'))
        values = [["" if value is None else str(value).strip() for value in row] + [""] * (width - len(row)) for row in rows]
        if any(len(cell) > 32768 or "\x00" in cell for row in values for cell in row):
            raise MailError(_ui_tr('Tabellenzelle ist zu lang oder enthält ungültige Zeichen.'))
        if sum(len(cell) for row in values for cell in row) > 2_000_000:
            raise MailError(_ui_tr('Erkannte Tabelle ist zu groß.'))
        result["tables"].append({"title": title, "page": page, "rows": values, "warnings": list(warnings)})

    try:
        if source.suffix.lower() == ".docx":
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                info = archive.getinfo("word/document.xml")
                if info.file_size > 20 * 1024 * 1024:
                    raise MailError(_ui_tr('DOCX-Dokumentteil ist zu groß.'))
                root = ET.fromstring(archive.read(info))
            # Nested tables have ambiguous column alignment; preserve their text in the outer cell.
            tables = root.findall("./" + W + "body/" + W + "tbl")
            for index, table in enumerate(tables, 1):
                if cancelled():
                    raise MailError(_ui_tr('Tabellenerkennung abgebrochen.'))
                rows, merged = [], False
                for row in table.findall(W + "tr"):
                    cells = []
                    for cell in row.findall(W + "tc"):
                        span = cell.find("./" + W + "tcPr/" + W + "gridSpan")
                        count = int(span.get(W + "val", "1")) if span is not None else 1
                        if not 1 <= count <= 30:
                            raise MailError(_ui_tr('Ungültige verbundene DOCX-Zelle.'))
                        merged |= count > 1 or cell.find("./" + W + "tcPr/" + W + "vMerge") is not None
                        def paragraph_text(paragraph):
                            return "".join(element.text or "" if element.tag == W + "t" else
                                           "\n" if element.tag in (W + "br", W + "cr") else
                                           "\t" if element.tag == W + "tab" else "" for element in paragraph.iter())
                        text = "\n".join(paragraph_text(paragraph) for paragraph in cell.iter(W + "p"))
                        cells.extend([text] + [""] * (count - 1))
                    rows.append(cells)
                add(rows, f"DOCX · Tabelle {index}", warnings=["Verbundene Zellen: leere Nachbarzellen und Zeilenzuordnung prüfen."] if merged else [])
        else:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                if len(pdf.pages) > 50:
                    raise MailError(_ui_tr('Für Tabellen höchstens 50 PDF-Seiten auswählen; Datei aufteilen.'))
                for page in pdf.pages:
                    if cancelled():
                        raise MailError(_ui_tr('Tabellenerkennung abgebrochen.'))
                    settings = {"vertical_strategy": pdf_strategy, "horizontal_strategy": pdf_strategy}
                    for index, rows in enumerate(page.extract_tables(settings), 1):
                        add(rows, f"PDF · Seite {page.page_number} · Tabelle {index}", page=page.page_number,
                            warnings=["PDF-Erkennung ist unsicher: jede Zeile, Zellgrenze und Kopfzeile prüfen."])
                    page.close()
    except MailError:
        raise
    except Exception as error:
        raise MailError(_ui_tr('Tabellen konnten nicht gelesen werden. Datei/Passwort prüfen; bei DOCX echte Tabellen verwenden, bei PDF Linien oder Textspalten wählen.')) from error
    if cancelled():
        raise MailError(_ui_tr('Tabellenerkennung abgebrochen.'))
    if not result["tables"]:
        raise MailError(_ui_tr('Keine strukturierte Tabelle erkannt. Bei PDF andere Erkennung wählen; Scans benötigen vorher OCR. Daten alternativ in die manuelle Liste einfügen.'))
    return result
