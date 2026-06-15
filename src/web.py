"""web — panneau de contrôle LOCAL (navigateur, boutons) pour piloter le pipeline.

L'interface la plus simple au quotidien : `python -m src.web` ouvre un petit serveur
sur http://127.0.0.1:8765. Contrairement au dashboard Vercel (distant, lecture seule,
agrégats), ce panneau tourne **sur ta machine** (là où vivent SQLite/SMTP/IMAP) donc il
peut **agir** : relever les retours, envoyer la file du jour, valider une réponse, voir
les leads chauds nominatifs.

🔒 **Localhost uniquement** par défaut → la PII ne sort jamais. NE PAS exposer publiquement.
Respecte « jamais d'auto-envoi » : l'envoi réel reste TON clic (case à cocher + bouton).
Le `.env` est chargé automatiquement (aucune variable à exporter).

CLI :
    python -m src.web [--db state.sqlite] [--port 8765]
"""
from __future__ import annotations

import argparse
import base64
import hmac
import html
import os
import sqlite3
import urllib.parse
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import calendly as _calendly
from . import config as _C
from . import daily as _daily
from . import db as _db
from . import inbox as _inbox
from . import preflight as _preflight
from . import replies as _replies
from . import report as _report
from . import scoring as _scoring
from .sender import SmtpConfig, due_messages, smtp_transport
from .templates import MessageContext

_STYLE = (
    "body{font-family:system-ui,Arial,sans-serif;margin:0;background:#0f1115;color:#e7ebf0}"
    "main{max-width:980px;margin:0 auto;padding:1.2rem}"
    "h1{font-size:1.3rem}h2{font-size:.95rem;color:#8b95a7;text-transform:uppercase;"
    "letter-spacing:.05em;margin:1.6rem 0 .6rem}"
    ".card{background:#181b22;border:1px solid #262b36;border-radius:12px;padding:1rem;margin:.6rem 0}"
    ".kpis{display:grid;gap:.8rem;grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}"
    ".kpi .v{font-size:1.7rem;font-weight:700}.kpi .l{color:#8b95a7;font-size:.75rem;text-transform:uppercase}"
    "table{width:100%;border-collapse:collapse;font-size:.86rem}"
    "th,td{text-align:left;padding:.4rem .6rem;border-bottom:1px solid #262b36}th{color:#8b95a7}"
    "button{background:#2ecc71;color:#06281a;border:0;border-radius:8px;padding:.5rem .9rem;"
    "font-weight:700;cursor:pointer}input,select{background:#0b0d11;color:#e7ebf0;border:1px solid"
    " #2b3340;border-radius:7px;padding:.4rem .5rem}label{font-size:.88rem}"
    ".flash{background:#13351f;border:1px solid #2ecc71;padding:.7rem 1rem;border-radius:10px;margin:.6rem 0}"
    ".go{color:#2ecc71;font-weight:700}.nogo{color:#ff6b4a;font-weight:700}.muted{color:#8b95a7;font-size:.82rem}"
)


def basic_auth_header(user: str, password: str) -> str:
    """En-tête `Authorization: Basic …` attendu pour (user, password)."""
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


def auth_ok(authorization: str | None, user: str, password: str) -> bool:
    """True si la requête est autorisée. Sans user/password configurés → pas d'auth.

    Indispensable dès que le panneau est exposé (tunnel) : protège la PII. Comparaison
    à temps constant.
    """
    if not (user and password):
        return True
    return hmac.compare_digest(authorization or "", basic_auth_header(user, password))


def _esc(x: object) -> str:
    return html.escape(str(x))


def _kpi(label: str, value: object) -> str:
    return f"<div class='card kpi'><div class='v'>{_esc(value)}</div><div class='l'>{_esc(label)}</div></div>"


def render_panel(conn: sqlite3.Connection, *, flash: str = "", on_date: date | None = None) -> str:
    on_date = on_date or date.today()
    checks = _preflight.run_preflight(conn)
    verdict = _preflight.verdict(checks)
    fails = [c for c in checks if c.status == _preflight.FAIL]

    funnel = _report.funnel(conn)
    kpis = _report.kpis(conn)
    due = len(due_messages(conn, on_date))
    hot = _scoring.hot_leads(conn, 20)
    ab = _report.ab_subjects(conn)

    smtp_ready = not SmtpConfig.from_env().missing()
    imap_ready = not _inbox.ImapConfig.from_env().missing()
    cal_ready = not _calendly.CalendlyConfig.from_env().missing()

    vclass = "go" if verdict == "GO" else "nogo"
    fail_txt = ("" if not fails else " · à corriger : "
                + ", ".join(_esc(c.name) for c in fails))

    kpi_html = "".join([
        _kpi("À envoyer aujourd'hui", due),
        _kpi("Leads chauds", len(_scoring.hot_leads(conn, 100000))),
        _kpi("RDV", funnel["rdv"]),
        _kpi("Taux ouverture", f"{kpis['taux_ouverture_%']} %"),
        _kpi("Taux réponse", f"{kpis['taux_reponse_%']} %"),
    ])

    # Action : relever + envoyer la file du jour
    real_note = ("" if smtp_ready else
                 "<span class='muted'> (SMTP non configuré → simulation forcée)</span>")
    send_card = (
        "<form method='post' action='/action'>"
        "<input type='hidden' name='action' value='run'>"
        "<label>Plafonner à <input type='number' name='limit' min='1' placeholder='ex. 25' style='width:90px'>"
        " (vide = plafond warm-up)</label><br><br>"
        f"<label><input type='checkbox' name='confirm' value='1'> Envoi réel{real_note}</label>"
        "<br><br><button type='submit'>Relever les retours + Envoyer la file du jour</button>"
        "<div class='muted'>Sans « envoi réel » coché : simulation (rien n'est envoyé).</div>"
        "</form>"
    )

    # Action : valider une réponse
    opts = "".join(f"<option value='{_esc(lbl)}'>{_esc(lbl)}</option>" for lbl in _replies.ALL_LABELS)
    reply_card = (
        "<form method='post' action='/action'>"
        "<input type='hidden' name='action' value='reply'>"
        "<label>Contact #<input type='number' name='contact_id' min='1' required style='width:90px'></label> "
        f"<select name='label'>{opts}</select> "
        "<button type='submit'>Valider la réponse</button>"
        "<div class='muted'>Applique l'action validée (STOP→blacklist, INTERESSE→Calendly, etc.).</div>"
        "</form>"
    )

    hot_rows = "".join(
        f"<tr><td>#{_esc(h['contact_id'])}</td><td>{_esc(h['email'])}</td><td>{_esc(h['dernier_clic'])}</td></tr>"
        for h in hot
    ) or "<tr><td colspan='3' class='muted'>Aucun lead chaud pour l'instant.</td></tr>"

    ab_rows = "".join(
        f"<tr><td>{_esc(r['subject'])}</td><td>{_esc(r['sent'])}</td>"
        f"<td>{_esc(r['taux_ouverture_%'])} %</td><td>{_esc(r['taux_reponse_%'])} %</td></tr>"
        for r in ab
    ) or "<tr><td colspan='4' class='muted'>Aucun envoi pour l'instant.</td></tr>"

    flash_html = f"<div class='flash'>{_esc(flash)}</div>" if flash else ""

    return (
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>DATA RÉNO — pilotage local</title><style>{_STYLE}</style></head><body><main>"
        "<h1>DATA RÉNO — panneau de pilotage (local)</h1>"
        f"<p>Gate : <span class='{vclass}'>{verdict}</span>{fail_txt} · "
        f"SMTP {'✅' if smtp_ready else '—'} · IMAP {'✅' if imap_ready else '—'} · "
        f"Calendly {'✅' if cal_ready else '—'}</p>"
        f"{flash_html}"
        f"<div class='kpis'>{kpi_html}</div>"
        f"<h2>Geste du jour</h2><div class='card'>{send_card}</div>"
        f"<h2>Valider une réponse</h2><div class='card'>{reply_card}</div>"
        "<h2>Leads chauds — cliqueurs sans réponse (à relancer)</h2>"
        f"<div class='card'><table><thead><tr><th>Contact</th><th>Email</th><th>Dernier clic</th></tr></thead>"
        f"<tbody>{hot_rows}</tbody></table></div>"
        "<h2>A/B objet</h2>"
        f"<div class='card'><table><thead><tr><th>Objet</th><th>Envoyés</th><th>Ouv.</th><th>Rép.</th></tr></thead>"
        f"<tbody>{ab_rows}</tbody></table></div>"
        "<p class='muted'>Localhost uniquement — ne pas exposer (contient des données personnelles). "
        "Le cron quotidien et le détail restent en CLI.</p>"
        "</main></body></html>"
    )


def action_run(conn: sqlite3.Connection, *, confirm: bool, limit: int | None) -> str:
    """Relève les retours (IMAP+Calendly si configurés) puis envoie/simule la file du jour."""
    smtp_cfg = SmtpConfig.from_env()
    transport = None if smtp_cfg.missing() else smtp_transport(smtp_cfg, MessageContext.from_env())
    imap_cfg = _inbox.ImapConfig.from_env()
    imap_cfg = None if imap_cfg.missing() else imap_cfg
    cal_cfg = _calendly.CalendlyConfig.from_env()
    cal_cfg = None if cal_cfg.missing() else cal_cfg
    s = _daily.run_daily(conn, transport=transport, confirm=confirm,
                         imap_cfg=imap_cfg, calendly_cfg=cal_cfg, limit=limit)
    snd = s["send"]
    if snd.get("dry_run"):
        return f"Simulation : {snd.get('would_send', 0)} message(s) seraient envoyés (rien n'est parti)."
    if snd.get("circuit_breaker"):
        return f"⛔ Envoi bloqué (coupe-circuit {snd['circuit_breaker']}, bounce-rate {snd.get('bounce_rate')})."
    return f"Envoyés : {snd['sent']} · échecs {snd['failed']} · bloqués {snd['blocked_placeholder'] + snd['blocked_claim']}."


def action_reply(conn: sqlite3.Connection, contact_id: int, label: str) -> str:
    """Valide la classe d'une réponse pour un contact (action humaine)."""
    if label not in _replies.ALL_LABELS:
        return f"Classe inconnue : {label}"
    _replies.record_reply(conn, contact_id, label)
    r = _replies.apply_action(conn, contact_id, label, ctx=MessageContext.from_env())
    return (f"Contact #{contact_id} → {label} · touches annulées {r['cancelled']} · "
            f"suppression {'oui' if r['suppressed'] else 'non'}.")


def _make_handler(db_path: str, user: str = "", password: str = ""):
    class Handler(BaseHTTPRequestHandler):
        def _send_html(self, body: str, code: int = 200) -> None:
            data = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _guard(self) -> bool:
            """Renvoie False (et émet 401) si l'auth est requise et invalide."""
            if auth_ok(self.headers.get("Authorization"), user, password):
                return True
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="DATA RENO"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return False

        def do_GET(self) -> None:  # noqa: N802
            if not self._guard():
                return
            if self.path.split("?")[0] not in ("/", "/index.html"):
                self._send_html("<p>404</p>", 404)
                return
            conn = _db.connect(db_path)
            try:
                self._send_html(render_panel(conn))
            finally:
                conn.close()

        def do_POST(self) -> None:  # noqa: N802
            if not self._guard():
                return
            length = int(self.headers.get("Content-Length", 0))
            form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"))
            action = form.get("action", [""])[0]
            conn = _db.connect(db_path)
            try:
                if action == "run":
                    limit = form.get("limit", [""])[0].strip()
                    flash = action_run(conn, confirm=form.get("confirm", [""])[0] == "1",
                                       limit=int(limit) if limit.isdigit() else None)
                elif action == "reply":
                    cid = form.get("contact_id", ["0"])[0]
                    flash = action_reply(conn, int(cid) if cid.isdigit() else 0,
                                         form.get("label", [""])[0])
                else:
                    flash = "Action inconnue."
                self._send_html(render_panel(conn, flash=flash))
            finally:
                conn.close()

        def log_message(self, *args) -> None:  # silence (pas de PII dans les logs serveur)
            return

    return Handler


def main(argv: list[str] | None = None) -> int:
    _C.load_env()  # charge .env automatiquement
    parser = argparse.ArgumentParser(description="Panneau de pilotage local (navigateur).")
    parser.add_argument("--db", default=_db.DEFAULT_DB)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1", help="Défaut localhost (NE PAS exposer : PII).")
    parser.add_argument("--no-open", action="store_true", help="Ne pas ouvrir le navigateur.")
    args = parser.parse_args(argv)

    user = os.getenv("WEB_USER", "").strip()
    password = os.getenv("WEB_PASSWORD", "").strip()
    url = f"http://{args.host}:{args.port}"
    httpd = ThreadingHTTPServer((args.host, args.port), _make_handler(args.db, user, password))
    auth_state = "auth ON (Basic)" if (user and password) else "auth OFF"
    print(f"Panneau de pilotage → {url}  [{auth_state}]  (Ctrl+C pour arrêter)")  # noqa: T201
    exposed = args.host not in ("127.0.0.1", "localhost")
    if (exposed or os.getenv("WEB_EXPOSED")) and not (user and password):
        print("⚠️  Panneau accessible hors localhost SANS auth : définis WEB_USER/WEB_PASSWORD "  # noqa: T201
              "(données personnelles). Recommandé même derrière un tunnel.")
    if not args.no_open:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")  # noqa: T201
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
