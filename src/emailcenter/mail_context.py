"""Read-only suggestions for composing mail from project records."""

from .language import translate as _ui_tr, format_text as _ui_format

from .mail_models import MailError, address
from .record_service import RecordService


def _inline(value):
    return " ".join((value or "").replace("\x00", "").split())


def compose_context(connection, *, application_id=None, contact_id=None):
    if not application_id and not contact_id:
        raise ValueError(_ui_tr('Bitte eine Bewerbung oder einen Kontakt auswählen.'))
    records = RecordService(connection)
    warnings, documents = [], []
    if application_id:
        application = records.get("applications", application_id)
        job = connection.execute(
            "SELECT title,reference_number FROM job_postings WHERE id=? AND deleted_at IS NULL",
            (application["job_posting_id"],),
        ).fetchone()
        title = _inline(job["title"] if job else application["title"])
        reference = _inline(job["reference_number"]) if job else ""
        subject = f"Bewerbung: {title}" + (f" (Referenz: {reference})" if reference else "")
        paragraph = f"hiermit bewerbe ich mich auf die Stelle „{title}“."
        if reference:
            paragraph += f" Die Referenz lautet {reference}."
        source_label = _ui_format('Bewerbung: {0}', _inline(application['title']))
        contacts = [dict(row) for row in connection.execute(
            "SELECT c.id,c.display_name,c.email,0 AS is_primary FROM application_contacts ac "
            "JOIN contacts c ON c.id=ac.contact_id WHERE ac.application_id=? AND c.deleted_at IS NULL "
            "ORDER BY c.display_name COLLATE NOCASE,c.id", (application_id,))]
        contact_source = _ui_tr('Bewerbung')
        if not contacts:
            contacts = [dict(row) for row in connection.execute(
                "SELECT c.id,c.display_name,c.email,cc.is_primary FROM company_contacts cc "
                "JOIN contacts c ON c.id=cc.contact_id JOIN companies co ON co.id=cc.company_id "
                "WHERE cc.company_id=? AND c.deleted_at IS NULL AND co.deleted_at IS NULL "
                "ORDER BY cc.is_primary DESC,c.display_name COLLATE NOCASE,c.id",
                (application["company_id"],))]
            contact_source = _ui_tr('Unternehmen', context='field')
        documents = [dict(row) for row in connection.execute(
            "SELECT d.id,d.original_filename,d.format FROM documents d "
            "LEFT JOIN document_sets s ON s.id=d.document_set_id "
            "WHERE COALESCE(d.application_id,s.application_id)=? AND d.deleted_at IS NULL "
            "ORDER BY d.created_at DESC,d.id", (application_id,))]
    else:
        contact = records.get("contacts", contact_id)
        contacts = [{**contact, "is_primary": 0}]
        contact_source = _ui_tr('Kontakt')
        source_label = _ui_format('Kontakt: {0}', _inline(contact['display_name']))
        subject, paragraph = "Nachricht an " + _inline(contact["display_name"]), ""

    candidates = []
    for contact in contacts:
        try:
            email = address(contact["email"])
        except MailError:
            warnings.append(_ui_format('{0}: E-Mail fehlt oder ist ungültig; bitte manuell ergänzen.', _inline(contact['display_name'])))
            continue
        candidates.append({"id": contact["id"], "display_name": _inline(contact["display_name"]),
                           "email": email, "is_primary": bool(contact["is_primary"]),
                           "source": contact_source})
    selected = None
    if contact_id and application_id:
        selected = next((item for item in candidates if item["id"] == contact_id), None)
        if selected is None:
            raise ValueError(_ui_tr('Der Kontakt besitzt keine gültige E-Mail oder gehört nicht zu dieser Bewerbung.'))
    elif len(candidates) == 1:
        selected = candidates[0]
    elif candidates and contact_source == "Unternehmen":
        primary = [item for item in candidates if item["is_primary"]]
        if len(primary) == 1:
            selected = primary[0]
    if not candidates:
        warnings.append(_ui_tr('Kein gültiger Ansprechpartner gefunden. Empfänger manuell eingeben.'))
    elif len(candidates) > 1 and selected is None:
        warnings.append(_ui_tr('Mehrere Ansprechpartner: gewünschten Empfänger ausdrücklich auswählen.'))
    greeting = "Guten Tag" + (" " + selected["display_name"] if selected else "") + ","
    return {
        "application_id": application_id, "source_label": source_label,
        "candidates": candidates, "selected_contact_id": selected["id"] if selected else None,
        "recipients": {"to": [selected["email"]] if selected else [], "cc": [], "bcc": []},
        "subject": subject[:998], "body": greeting + "\n\n" + paragraph + "\n\n",
        "documents": documents, "warnings": warnings,
    }
