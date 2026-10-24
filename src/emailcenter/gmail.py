"""Gmail REST adapter with one send request and explicit uncertain results."""

from .language import translate as _ui_tr, format_text as _ui_format

import base64
import json
import re
from pathlib import Path
from typing import Protocol

from .mail_models import MailError, address
from .oauth_callback import run_local_oauth


SCOPES = ("https://www.googleapis.com/auth/gmail.compose", "https://www.googleapis.com/auth/gmail.readonly")
API_ROOT = "https://gmail.googleapis.com/gmail/v1/users/me"


class ProviderError(MailError):
    def __init__(self, message, *, code="provider_error", uncertain=False, retry_after=0):
        super().__init__(message)
        self.code = code
        self.uncertain = uncertain
        self.retry_after = retry_after


class MailProvider(Protocol):
    def profile(self) -> str: ...
    def send(self, raw: bytes) -> str: ...
    def save_draft(self, raw: bytes, draft_id: str | None = None) -> str: ...
    def find_sent(self, message_id: str) -> list[dict]: ...


def load_desktop_client(client_path):
    """Validate a downloaded desktop client without exposing it or opening a browser."""
    try:
        path = Path(client_path)
        if path.stat().st_size > 64 * 1024:
            raise ValueError()
        configuration = json.loads(path.read_text(encoding="utf-8-sig"))
        client = configuration["installed"]
        if (client["auth_uri"] != "https://accounts.google.com/o/oauth2/auth"
                or client["token_uri"] != "https://oauth2.googleapis.com/token"
                or not client["client_id"].endswith(".apps.googleusercontent.com") or not client["client_secret"]):
            raise ValueError()
    except Exception:
        raise MailError(_ui_tr('Bitte die heruntergeladene Google-OAuth-JSON einer Desktop-App auswählen.')) from None
    return configuration


def authorize_desktop(client_path):
    """OAuth in the system browser, PKCE and an exclusive loopback listener."""
    configuration = load_desktop_client(client_path)
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_config(configuration, SCOPES, autogenerate_code_verifier=True)
        request = flow.oauth2session.request
        def bounded_request(*args, **kwargs):
            kwargs.setdefault("timeout", 30)
            return request(*args, **kwargs)
        flow.oauth2session.request = bounded_request
        credentials = run_local_oauth(flow, timeout_seconds=180)
        if not credentials.refresh_token or not credentials.has_scopes(SCOPES):
            raise ValueError()
        return json.loads(credentials.to_json())
    except Exception:
        raise MailError(_ui_tr('Google-Anmeldung abgebrochen oder fehlgeschlagen. Gmail API, Testnutzer und Berechtigungen prüfen.')) from None


class GmailProvider:
    def __init__(self, info, *, persist=lambda info: None, session=None, credentials=None):
        if credentials is None:
            from google.oauth2.credentials import Credentials
            try:
                if info.get("token_uri", "https://oauth2.googleapis.com/token") != "https://oauth2.googleapis.com/token":
                    raise ValueError()
                credentials = Credentials.from_authorized_user_info(info)
                if not credentials.has_scopes(SCOPES):
                    raise ValueError()
            except Exception:
                raise ProviderError(_ui_tr('Gmail-Konto neu verbinden.'), code='credentials') from None
        if session is None:
            import requests
            session = requests.Session()  # Default adapters have zero retries.
        self.credentials, self.session, self.persist = credentials, session, persist

    def _request(self, method, path, *, payload=None, params=None, sending=False):
        if not self.credentials.valid:
            try:
                from google.auth.transport.requests import Request
                request = Request(session=self.session)
                def refresh_request(*args, **kwargs):
                    kwargs["timeout"] = 30
                    return request(*args, **kwargs)
                self.credentials.refresh(refresh_request)
                self.persist(json.loads(self.credentials.to_json()))
            except Exception:
                raise ProviderError(_ui_tr('Gmail-Zugang ist abgelaufen oder nicht verfügbar. Konto neu verbinden.'), code='credentials') from None
        try:
            response = self.session.request(method, API_ROOT + path, json=payload, params=params,
                                            headers={"Authorization": "Bearer " + self.credentials.token},
                                            timeout=(10, 45), allow_redirects=False)
        except Exception:
            raise ProviderError(_ui_tr('Gmail-Verbindung unterbrochen. Ergebnis muss geprüft werden.') if sending else _ui_tr('Gmail ist nicht erreichbar.'), code='connection', uncertain=sending) from None
        if not 200 <= response.status_code < 300:
            status = response.status_code
            reason = ""
            if status in (403, 429):
                try:
                    reasons = [e.get("reason", "") for e in response.json().get("error", {}).get("errors", [])]
                    reason = next((r for r in reasons if r in ("dailyLimitExceeded", "rateLimitExceeded", "userRateLimitExceeded", "quotaExceeded")), "")
                except (ValueError, TypeError, AttributeError):
                    pass
            quota = status == 429 or bool(reason)
            retry_after = 86400 if reason == "dailyLimitExceeded" else 120 if quota else 0
            if quota:
                try:
                    retry_after = max(retry_after, min(604800, int(getattr(response, "headers", {}).get("Retry-After", "0"))))
                except (ValueError, TypeError):
                    pass
            unclear = sending and (status >= 500 or status in (408, 429) or 300 <= status < 400)
            message = "Gmail meldet ein unklar gebliebenes Versandresultat." if unclear else "Gmail hat die Anfrage abgewiesen. Konto, Berechtigungen oder Limits prüfen."
            if quota:
                message = "Gmail-Limit erreicht. Konto pausieren; Versandresultat vor Wiederholung prüfen."
            raise ProviderError(message, code=("quota_" + (reason or "429")) if quota else f"http_{status}", uncertain=unclear, retry_after=retry_after)
        try:
            value = response.json()
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except Exception:
            raise ProviderError(_ui_tr('Gmail hat keine auswertbare Antwort geliefert.'), code='response', uncertain=sending) from None

    def profile(self):
        return address(self._request("GET", "/profile").get("emailAddress"))

    def send(self, raw):
        result = self._request("POST", "/messages/send", payload={"raw": base64.urlsafe_b64encode(raw).decode("ascii")}, sending=True)
        if not isinstance(result.get("id"), str) or not result["id"]:
            raise ProviderError(_ui_tr('Gmail-Versandantwort enthält keine Nachrichten-ID.'), code='response', uncertain=True)
        return result["id"]

    def save_draft(self, raw, draft_id=None):
        if draft_id is not None and (not isinstance(draft_id, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,256}", draft_id) is None):
            raise ProviderError(_ui_tr('Ungültige Gmail-Entwurfsreferenz.'), code='draft_id')
        payload = {"message": {"raw": base64.urlsafe_b64encode(raw).decode("ascii")}}
        if draft_id:
            payload["id"] = draft_id
        result = self._request("PUT" if draft_id else "POST", "/drafts/" + draft_id if draft_id else "/drafts", payload=payload)
        if not result.get("id"):
            raise ProviderError(_ui_tr('Gmail-Entwurf konnte nicht bestätigt werden.'), code='response')
        return result["id"]

    def find_sent(self, message_id):
        query = "in:sent rfc822msgid:" + message_id.strip("<>")
        result = self._request("GET", "/messages", params={"q": query, "maxResults": 10})
        if result.get("nextPageToken"):
            raise ProviderError(_ui_tr('Mehrere mögliche Versandbelege; Ergebnis ist nicht eindeutig.'), code='reconciliation_ambiguous')
        matches = []
        for item in result.get("messages", []):
            identifier = item.get("id")
            if not isinstance(identifier, str) or not identifier.isalnum():
                raise ProviderError(_ui_tr('Gmail-Abgleich lieferte ungültige Daten.'), code='response')
            message = self._request("GET", "/messages/" + identifier, params={"format": "metadata", "metadataHeaders": ["Message-ID", "From"]})
            headers = {header["name"].lower(): header["value"] for header in message.get("payload", {}).get("headers", [])}
            if "SENT" in message.get("labelIds", []) and headers.get("message-id") == message_id:
                matches.append({"id": identifier, "message_id": headers["message-id"], "sender": headers.get("from", "")})
        return matches
