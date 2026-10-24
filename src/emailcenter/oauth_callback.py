"""Exclusive loopback OAuth callback with honest, accessible browser feedback."""

import secrets
from html import escape
import socket
import sys
import time
from urllib.parse import parse_qs
import webbrowser
from wsgiref.simple_server import WSGIServer, WSGIRequestHandler, make_server

from .branding import logo_data_url
from .language import Message, render, get_language


def completion_page(error=False, *, language=None):
    language = language or get_language()
    language = language if language in ('de', 'en') else 'de'
    def caption(source):
        return escape(render(Message(source), language))
    heading = caption("Anmeldung abgebrochen" if error else "Google-Rückmeldung erhalten")
    message = caption("Google hat die Anmeldung nicht bestätigt. Prüfe die Meldung in EmailCenter und versuche es erneut."
                      if error else "Abschluss in der App prüfen. EmailCenter prüft die Anmeldung und speichert die Kontoverbindung. Das verbundene Konto wird dort bestätigt.")
    return f'''<!doctype html><html lang="{language}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light dark">
<title>EmailCenter · {caption('Anmeldung')}</title><style>
:root {{color-scheme:light dark;--bg:#f0f3f7;--card:#fff;--ink:#172236;--muted:#546174;--accent:#2862c4}}
@media(prefers-color-scheme:dark) {{:root {{--bg:#121926;--card:#1b2638;--ink:#f1f4fa;--muted:#bdc8d9;--accent:#76a8ff}}}}
* {{box-sizing:border-box}} body {{margin:0;padding:24px;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--ink);font:16px/1.6 system-ui,sans-serif}}
main {{width:100%;max-width:540px;background:var(--card);border:1px solid var(--muted);border-radius:24px;padding:32px;box-shadow:0 20px 60px #0002}}
img {{width:128px;height:128px;image-rendering:crisp-edges;image-rendering:pixelated}} .brand {{font-weight:700;letter-spacing:.05em}}
h1 {{font-size:clamp(24px,5vw,32px);line-height:1.2}} p {{color:var(--muted)}} button {{padding:12px 20px;border:0;border-radius:12px;background:var(--accent);color:var(--bg);font:inherit;font-weight:700;cursor:pointer}}
button:focus-visible {{outline:3px solid var(--ink);outline-offset:4px}} small {{display:block;color:var(--muted);margin-top:16px}}
@media(max-width:400px) {{body {{padding:12px}} main {{padding:24px}}}}
</style></head><body><main><img src="{logo_data_url()}" alt=""><div class="brand">EmailCenter</div>
<h1>{heading}</h1><p>{message}</p><button type="button" id="close">{caption('Tab schließen')}</button>
<p id="fallback" role="status" hidden>{caption('Der Browser erlaubt das automatische Schließen nicht. Schließe diesen Tab über das × am Tab oder mit Strg+W und wechsle zu EmailCenter.')}</p>
<noscript><p>{caption('Schließe diesen Tab über das × am Tab oder mit Strg+W.')}</p></noscript>
<small>{caption('Der Browser bestätigt keine gespeicherte Kontoverbindung. Den Status findest du in der App.')}</small></main>
<script>try{{history.replaceState(null,'',location.pathname);}}catch(e){{}}document.getElementById('close').addEventListener('click',()=>{{document.getElementById('fallback').hidden=false;window.close();}});</script></body></html>'''


class CallbackApp:
    def __init__(self, state, redirect_uri):
        self.state, self.redirect_uri, self.response = state, redirect_uri, None

    def __call__(self, environment, start_response):
        query = parse_qs(environment.get("QUERY_STRING", ""), keep_blank_values=True)
        valid = (environment.get("PATH_INFO") == "/" and environment.get("REQUEST_METHOD") == "GET"
                 and len(query.get("state", [])) == 1 and secrets.compare_digest(query["state"][0].encode("utf-8"), self.state.encode("utf-8"))
                 and ((len(query.get("code", [])) == 1 and bool(query["code"][0]) and "error" not in query)
                      or (len(query.get("error", [])) == 1 and "code" not in query)))
        if valid:
            self.response = self.redirect_uri.replace("http://", "https://", 1) + "?" + environment["QUERY_STRING"]
            body, status = completion_page("error" in query).encode("utf-8"), "200 OK"
        else:
            body, status = render(Message("Ungültige OAuth-Rückmeldung. Zur App wechseln.")).encode("utf-8"), "400 Bad Request"
        start_response(status, [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(body))),
                                ("Cache-Control", "no-store"), ("Referrer-Policy", "no-referrer"),
                                ("Content-Security-Policy", "default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"),
                                ("X-Content-Type-Options", "nosniff")])
        return [body]


class ExclusiveServer(WSGIServer):
    allow_reuse_address = False

    def server_bind(self):
        if sys.platform == "win32":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(5)
        return connection, address


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):
        pass  # Callback query strings contain credentials and must never be logged.


def run_local_oauth(flow, *, timeout_seconds=180, open_browser=webbrowser.open):
    with make_server("127.0.0.1", 0, lambda env, start: [], server_class=ExclusiveServer, handler_class=QuietHandler) as server:
        flow.redirect_uri = f"http://127.0.0.1:{server.server_port}/"
        url, state = flow.authorization_url(prompt="consent", access_type="offline")
        callback = CallbackApp(state, flow.redirect_uri)
        server.set_app(callback)
        open_browser(url, new=1, autoraise=True)
        deadline = time.monotonic() + timeout_seconds
        while callback.response is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("OAuth callback timed out")
            server.timeout = min(remaining, 1)
            server.handle_request()
        flow.fetch_token(authorization_response=callback.response)
        return flow.credentials
