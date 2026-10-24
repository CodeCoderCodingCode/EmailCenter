"""Project-scoped OAuth secrets stored exclusively in Windows Credential Manager."""

from .language import translate as _ui_tr, format_text as _ui_format

import json
import os
from uuid import UUID, uuid4

from .mail_models import MailError


class WindowsTokenStore:
    """Generation chunks keep blobs below WinVault's size limit; head commits last."""

    def __init__(self, project_id, *, backend=None):
        self.project_id = project_id
        self._backend = backend

    @property
    def backend(self):
        if self._backend is None:
            if os.name != "nt":
                raise MailError(_ui_tr('OAuth-Tokenablage benötigt Windows Credential Manager.'))
            try:
                from keyring.backends.Windows import WinVaultKeyring
                backend = WinVaultKeyring()
                backend.persist = "local machine"
                self._backend = backend
            except Exception:
                raise MailError(_ui_tr('Windows-Anmeldedatenspeicher ist nicht verfügbar.')) from None
        return self._backend

    def _service(self, account_id, suffix="head"):
        return f"EmailCenter/{self.project_id}/{account_id}/{suffix}"

    def _head(self, account_id):
        value = self.backend.get_password(self._service(account_id), "oauth")
        if value is None:
            return None
        head = json.loads(value)
        if not isinstance(head, dict) or not isinstance(head.get("count"), int) or not 1 <= head["count"] <= 100:
            raise ValueError(_ui_tr('Invalid credential manifest'))
        if str(UUID(head.get("generation", ""))) != head["generation"]:
            raise ValueError(_ui_tr('Invalid credential generation'))
        return head

    def get(self, account_id):
        try:
            head = self._head(account_id)
            if head is None:
                return None
            chunks = [self.backend.get_password(self._service(account_id, f'{head["generation"]}/{index}'), "oauth")
                      for index in range(head["count"])]
            if any(chunk is None for chunk in chunks):
                raise ValueError(_ui_tr('Missing credential chunk'))
            value = json.loads("".join(chunks))
            if not isinstance(value, dict):
                raise ValueError(_ui_tr('Invalid credential value'))
            return value
        except Exception:
            raise MailError(_ui_tr('Gmail-Zugangsdaten fehlen oder können nicht sicher gelesen werden. Konto neu verbinden.')) from None

    def put(self, account_id, info):
        generation = str(uuid4())
        written = []
        try:
            try:
                old = self._head(account_id)
            except (ValueError, TypeError, AttributeError):
                old = None  # A new authorization can replace a malformed manifest.
            text = json.dumps(info, ensure_ascii=True, allow_nan=False)
            chunks = [text[index:index + 1000] for index in range(0, len(text), 1000)]
            if not 1 <= len(chunks) <= 100:
                raise ValueError(_ui_tr('Credential exceeds limit'))
            for index, chunk in enumerate(chunks):
                service = self._service(account_id, f"{generation}/{index}")
                self.backend.set_password(service, "oauth", chunk)
                written.append(service)
            self.backend.set_password(self._service(account_id), "oauth", json.dumps({"generation": generation, "count": len(chunks)}))
        except Exception:
            for service in written:
                self._remove(service)
            raise MailError(_ui_tr('Gmail-Zugangsdaten konnten nicht sicher gespeichert werden.')) from None
        if old:
            self._remove_chunks(account_id, old)

    def delete(self, account_id):
        try:
            head = self._head(account_id)
            if head:
                self.backend.delete_password(self._service(account_id), "oauth")
                self._remove_chunks(account_id, head)
        except Exception:
            raise MailError(_ui_tr('Gmail-Zugangsdaten konnten nicht entfernt werden.')) from None

    def _remove_chunks(self, account_id, head):
        for index in range(head["count"]):
            self._remove(self._service(account_id, f'{head["generation"]}/{index}'))

    def _remove(self, service):
        try:
            self.backend.delete_password(service, "oauth")
        except Exception:
            pass  # Cleanup may leave protected old chunks, never plaintext files.
