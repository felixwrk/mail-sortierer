#!/usr/bin/env python3
"""
Mail-Sortierer – läuft komplett lokal auf deinem Computer (Mac und Windows).

- Holt Mails per IMAP (Gmail mit App-Passwort)
- Sortiert sie mit festen Regeln in Kategorien (keine KI, keine Kosten)
- "Sortieren": Mails als Wischkarten -> Löschen (Papierkorb) / Behalten
- Passwort liegt im Schlüsselbund (Mac) bzw. in der Anmeldeinformationsverwaltung (Windows)
- Aktualisiert sich selbst über GitHub Releases

Nur Python-Standardbibliothek.
"""

import base64
import email
import email.policy
import email.utils
import html
import imaplib
import json
import os
import quopri
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

APP_NAME = "MailSortierer"
APP_VERSION = "0.0.0-dev"          # wird beim Bauen aus dem Git-Tag gesetzt
GITHUB_REPO = "__REPO__"           # wird beim Bauen gesetzt, z. B. "name/mail-sortierer"
PORT = 8765
MAX_MAILS = 400
IMAP_HOST = "imap.gmail.com"

IS_MAC = sys.platform == "darwin"
IS_WIN = os.name == "nt"
FROZEN = getattr(sys, "frozen", False)

if os.environ.get("MAILSORTIERER_DATA"):
    DATA_DIR = Path(os.environ["MAILSORTIERER_DATA"])
elif IS_MAC:
    DATA_DIR = Path.home() / "Library" / "Application Support" / APP_NAME
elif IS_WIN:
    DATA_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
else:
    DATA_DIR = Path.home() / ".config" / APP_NAME
CONFIG_FILE = DATA_DIR / "config.json"
KEPT_FILE = DATA_DIR / "behalten.json"
RULES_FILE = DATA_DIR / "regeln.json"
HERE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))

START_TIME = time.time()
LAST_PING = 0.0

# ---------------------------------------------------------------- Regeln

DEFAULT_RULES = {
    "_hinweis": "Diese Datei kannst du anpassen. Reihenfolge = Priorität. "
                "'absender' prüft die Absenderadresse, 'woerter' den Betreff. "
                "'unwichtig': true = erscheint standardmäßig als Karte beim Sortieren.",
    "kategorien": [
        {"name": "Finanzen & Rechnungen", "unwichtig": False, "werbung_ausschliessen": True,
         "absender": ["paypal", "sparkasse", "volksbank", "ing.de", "dkb", "comdirect",
                      "commerzbank", "deutsche-bank", "n26", "klarna", "postbank",
                      "finanzamt", "elster"],
         "woerter": ["rechnung", "invoice", "zahlung", "kontoauszug", "lastschrift",
                     "mahnung", "überweisung", "beitrag"]},
        {"name": "Bestellungen & Versand", "unwichtig": False, "werbung_ausschliessen": True,
         "absender": ["amazon", "ebay", "dhl", "dpd", "hermes", "ups.com", "gls",
                      "zalando", "otto.de", "kleinanzeigen", "temu", "aliexpress"],
         "woerter": ["bestellung", "versand", "lieferung", "sendung", "paket",
                     "order", "shipped", "zugestellt", "versandbestätigung"]},
        {"name": "Soziale Netzwerke", "unwichtig": True,
         "absender": ["facebook", "facebookmail", "instagram", "linkedin", "twitter",
                      "x.com", "tiktok", "xing", "pinterest", "reddit", "discord",
                      "youtube", "snapchat", "whatsapp"],
         "woerter": []},
        {"name": "Newsletter & Werbung", "unwichtig": True, "abmeldelink_zaehlt": True,
         "absender": ["newsletter", "news@", "marketing", "promo", "angebote",
                      "info@", "mailing"],
         "woerter": ["newsletter", "angebot", "rabatt", "sale", "gutschein", "% ",
                     "deal", "nur heute", "jetzt sparen", "black friday"]},
        {"name": "Benachrichtigungen", "unwichtig": True,
         "absender": ["noreply", "no-reply", "donotreply", "do-not-reply",
                      "notification", "benachrichtigung", "alert", "mailer"],
         "woerter": ["benachrichtigung", "notification", "erinnerung"]},
    ],
    "rest": {"name": "Persönlich & Sonstiges", "unwichtig": False},
}


def load_rules():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not RULES_FILE.exists():
        RULES_FILE.write_text(json.dumps(DEFAULT_RULES, ensure_ascii=False, indent=2), "utf-8")
    try:
        return json.loads(RULES_FILE.read_text("utf-8"))
    except Exception:
        return DEFAULT_RULES


def categorize(mail, rules):
    sender = (mail["from_addr"] + " " + mail["from_name"]).lower()
    subject = mail["subject"].lower()
    for cat in rules["kategorien"]:
        word_hit = any(w in subject for w in cat.get("woerter", []))
        sender_hit = any(a in sender for a in cat.get("absender", []))
        if cat.get("werbung_ausschliessen") and mail.get("bulk") and not word_hit:
            continue
        if word_hit or sender_hit:
            return cat
        if cat.get("abmeldelink_zaehlt") and mail.get("bulk"):
            return cat
    return rules["rest"]


# ---------------------------------------------------------------- Speicher

def read_json(path, default):
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return default


def write_json(path, data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


# ---------------------------------------------------------------- Passwort-Speicher

if IS_WIN:
    import ctypes
    from ctypes import wintypes

    class _CREDENTIAL(ctypes.Structure):
        _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
                    ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
                    ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                    ("CredentialBlob", ctypes.POINTER(ctypes.c_char)), ("Persist", wintypes.DWORD),
                    ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                    ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]

    _adv = ctypes.WinDLL("advapi32", use_last_error=True)
    _adv.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIAL), wintypes.DWORD]
    _adv.CredWriteW.restype = wintypes.BOOL
    _adv.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                               ctypes.POINTER(ctypes.POINTER(_CREDENTIAL))]
    _adv.CredReadW.restype = wintypes.BOOL
    _adv.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    _adv.CredDeleteW.restype = wintypes.BOOL
    _adv.CredFree.argtypes = [ctypes.c_void_p]
    _adv.CredFree.restype = None


def _target(account):
    return f"{APP_NAME}:{account}"


def secret_set(account, password):
    if IS_MAC:
        # Base64, weil "security" Passwörter mit Sonderzeichen sonst als Hex ausgibt
        enc = "b64:" + base64.b64encode(password.encode("utf-8")).decode("ascii")
        subprocess.run(["security", "add-generic-password", "-a", account, "-s", APP_NAME,
                        "-w", enc, "-U"], check=True, capture_output=True)
    elif IS_WIN:
        blob = password.encode("utf-16-le")
        buf = ctypes.create_string_buffer(blob, len(blob))
        cred = _CREDENTIAL()
        cred.Type = 1                      # CRED_TYPE_GENERIC
        cred.TargetName = _target(account)
        cred.CredentialBlobSize = len(blob)
        cred.CredentialBlob = ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))
        cred.Persist = 2                   # CRED_PERSIST_LOCAL_MACHINE
        cred.UserName = account
        if not _adv.CredWriteW(ctypes.byref(cred), 0):
            raise OSError(ctypes.get_last_error(), "Passwort konnte nicht gespeichert werden")
    else:
        store = read_json(DATA_DIR / ".secrets.json", {})
        store[account] = password
        write_json(DATA_DIR / ".secrets.json", store)
        os.chmod(DATA_DIR / ".secrets.json", 0o600)


def secret_get(account):
    if IS_MAC:
        r = subprocess.run(["security", "find-generic-password", "-a", account, "-s", APP_NAME, "-w"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            return None
        val = r.stdout.strip()
        if val.startswith("b64:"):
            try:
                return base64.b64decode(val[4:]).decode("utf-8")
            except Exception:
                return None
        return val
    if IS_WIN:
        p = ctypes.POINTER(_CREDENTIAL)()
        if not _adv.CredReadW(_target(account), 1, 0, ctypes.byref(p)):
            return None
        try:
            c = p.contents
            return ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize).decode("utf-16-le")
        finally:
            _adv.CredFree(p)
    return read_json(DATA_DIR / ".secrets.json", {}).get(account)


def secret_delete(account):
    if IS_MAC:
        subprocess.run(["security", "delete-generic-password", "-a", account, "-s", APP_NAME],
                       capture_output=True)
    elif IS_WIN:
        _adv.CredDeleteW(_target(account), 1, 0)
    else:
        store = read_json(DATA_DIR / ".secrets.json", {})
        store.pop(account, None)
        write_json(DATA_DIR / ".secrets.json", store)


# ---------------------------------------------------------------- IMAP

class MailError(Exception):
    pass


def connect(account=None, password=None):
    cfg = read_json(CONFIG_FILE, {})
    account = account or cfg.get("email")
    if not account:
        raise MailError("Noch kein Konto eingerichtet.")
    password = password or secret_get(account)
    if not password:
        raise MailError("Kein gespeichertes Passwort gefunden. Bitte neu anmelden.")
    try:
        conn = imaplib.IMAP4_SSL(cfg.get("server", IMAP_HOST), timeout=30)
        conn.login(account, password.replace(" ", ""))
        return conn
    except imaplib.IMAP4.error:
        raise MailError("Anmeldung fehlgeschlagen. Stimmen E-Mail und App-Passwort?")
    except (OSError, socket.timeout):
        raise MailError("Keine Verbindung zum Mailserver. Bist du online?")


def logout(conn):
    try:
        conn.logout()
    except Exception:
        pass


def caps(conn):
    return [c.decode() if isinstance(c, bytes) else str(c) for c in conn.capabilities]


def find_trash(conn):
    typ, data = conn.list()
    for line in data or []:
        s = line.decode("utf-8", "replace") if isinstance(line, bytes) else str(line)
        if "\\Trash" in s:
            m = re.search(r'"([^"]+)"\s*$', s) or re.search(r"(\S+)\s*$", s)
            if m:
                return m.group(1)
    for name in ("[Gmail]/Papierkorb", "[Gmail]/Trash", "Trash", "Papierkorb"):
        if conn.select(f'"{name}"', readonly=True)[0] == "OK":
            return name
    raise MailError("Papierkorb-Ordner nicht gefunden.")


def html_to_text(s, keep_lines=False):
    s = re.sub(r"(?is)<(script|style|head).*?</\1>", " ", s)
    if keep_lines:
        s = re.sub(r"(?i)<br\s*/?>", "\n", s)
        s = re.sub(r"(?i)</(p|div|tr|h[1-6]|li|table|blockquote)>", "\n", s)
        s = re.sub(r"(?i)<li[^>]*>", "• ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return html.unescape(s)


def decode_part(part):
    charset = part.get_content_charset() or "utf-8"
    cte = str(part.get("Content-Transfer-Encoding", "")).lower().strip()
    raw = part.get_payload(decode=False)
    if isinstance(raw, list):
        raise ValueError
    raw = raw.encode("ascii", "ignore") if isinstance(raw, str) else raw
    if cte == "base64":
        b = re.sub(rb"[^A-Za-z0-9+/]", b"", raw)
        data = base64.b64decode(b[: len(b) // 4 * 4] or b"")
    elif cte == "quoted-printable":
        data = quopri.decodestring(raw)
    else:
        data = raw
    try:
        return data.decode(charset, "replace")
    except LookupError:
        return data.decode("utf-8", "replace")


def text_parts(msg):
    plain, htm = None, None
    for part in msg.walk():
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        ctype = part.get_content_type()
        try:
            content = decode_part(part)
        except Exception:
            try:
                content = part.get_payload(decode=True).decode("utf-8", "replace")
            except Exception:
                continue
        if ctype == "text/plain" and plain is None:
            plain = content
        elif ctype == "text/html" and htm is None:
            htm = content
    return plain, htm


def extract_snippet(header_bytes, text_bytes):
    try:
        msg = email.message_from_bytes(header_bytes + text_bytes, policy=email.policy.default)
        plain, htm = text_parts(msg)
        text = plain if plain and plain.strip() else html_to_text(htm or "")
    except Exception:
        text = html_to_text(text_bytes.decode("utf-8", "replace"))
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[A-Za-z0-9+/=]{60,}", "", text)
    text = text.replace("�", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:600]


def parse_fetch(data):
    msgs, cur = [], None
    for item in data:
        if isinstance(item, tuple):
            head = item[0].decode("utf-8", "replace")
            if re.match(r"^\d+ \(", head):
                cur = {"header": b"", "text": b""}
                msgs.append(cur)
            if cur is None:
                continue
            for key, rx in (("uid", r"UID (\d+)"), ("gmid", r"X-GM-MSGID (\d+)")):
                m = re.search(rx, head)
                if m:
                    cur[key] = m.group(1)
            if "BODY[HEADER]" in head:
                cur["header"] = item[1]
            elif "BODY[TEXT]" in head:
                cur["text"] = item[1]
        elif isinstance(item, bytes) and cur is not None:
            s = item.decode("utf-8", "replace")
            for key, rx in (("uid", r"UID (\d+)"), ("gmid", r"X-GM-MSGID (\d+)")):
                m = re.search(rx, s)
                if m and key not in cur:
                    cur[key] = m.group(1)
    return msgs


def build_mail(raw):
    hdr = email.message_from_bytes(raw["header"], policy=email.policy.default)

    def h(name):
        try:
            return str(hdr.get(name, "") or "")
        except Exception:
            return ""

    name, addr = email.utils.parseaddr(h("From"))
    try:
        ts = email.utils.parsedate_to_datetime(h("Date")).timestamp()
    except Exception:
        ts = 0
    bulk = bool(h("List-Unsubscribe")) or h("Precedence").lower() in ("bulk", "list", "junk")
    gmid = raw.get("gmid")
    return {
        "uid": raw["uid"],
        "msgid": h("Message-ID").strip(),
        "from_name": name or addr,
        "from_addr": addr,
        "subject": h("Subject") or "(kein Betreff)",
        "ts": ts,
        "bulk": bulk,
        "snippet": extract_snippet(raw["header"], raw["text"]),
        "link": f"https://mail.google.com/mail/u/0/#all/{int(gmid):x}" if gmid else None,
    }


def fetch_mails():
    rules = load_rules()
    conn = connect()
    try:
        is_gmail = "X-GM-EXT-1" in caps(conn)
        conn.select("INBOX", readonly=True)
        typ, data = conn.uid("SEARCH", None, "ALL")
        uids = data[0].split()[-MAX_MAILS:]
        items = "(UID BODY.PEEK[HEADER] BODY.PEEK[TEXT]<0.6000>" + (" X-GM-MSGID)" if is_gmail else ")")
        mails = []
        for i in range(0, len(uids), 80):
            chunk = b",".join(uids[i:i + 80]).decode()
            typ, data = conn.uid("FETCH", chunk, items)
            for raw in parse_fetch(data):
                if "uid" in raw and raw["header"]:
                    try:
                        mails.append(build_mail(raw))
                    except Exception:
                        pass
    finally:
        logout(conn)

    kept = set(read_json(KEPT_FILE, []))
    for m in mails:
        cat = categorize(m, rules)
        m["category"] = cat["name"]
        m["unwichtig"] = bool(cat.get("unwichtig"))
        m["kept"] = m["msgid"] in kept
    mails.sort(key=lambda m: m["ts"], reverse=True)
    cats = [{"name": c["name"], "unwichtig": bool(c.get("unwichtig"))}
            for c in rules["kategorien"] + [rules["rest"]]]
    return {"mails": mails, "categories": cats}


def get_body(uid):
    conn = connect()
    try:
        conn.select("INBOX", readonly=True)
        typ, data = conn.uid("FETCH", uid, "(BODY.PEEK[])")
        raw = next((it[1] for it in data or [] if isinstance(it, tuple)), None)
        if not raw:
            raise MailError("Mail nicht gefunden.")
    finally:
        logout(conn)
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    plain, htm = text_parts(msg)
    text = plain if plain and plain.strip() else html_to_text(htm or "", keep_lines=True)
    text = text.replace("\r", "").replace("�", "")
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in text.split("\n")]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return text[:30000] or "(Diese Mail enthält keinen lesbaren Text.)"


def _move(conn, uid, target):
    if "MOVE" in caps(conn):
        typ, _ = conn.uid("MOVE", uid, target)
    else:
        typ, _ = conn.uid("COPY", uid, target)
        if typ == "OK":
            conn.uid("STORE", uid, "+FLAGS", r"(\Deleted)")
            conn.expunge()
    return typ


def move_to_trash(uid):
    conn = connect()
    try:
        trash = find_trash(conn)
        conn.select("INBOX")
        if _move(conn, uid, f'"{trash}"') != "OK":
            raise MailError("Löschen hat nicht geklappt.")
    finally:
        logout(conn)


def restore_from_trash(msgid):
    conn = connect()
    try:
        trash = find_trash(conn)
        conn.select(f'"{trash}"')
        typ, data = conn.uid("SEARCH", None, "HEADER", "Message-ID", f'"{msgid}"')
        uids = data[0].split() if data and data[0] else []
        if not uids:
            raise MailError("Mail im Papierkorb nicht gefunden.")
        _move(conn, uids[-1].decode(), "INBOX")
    finally:
        logout(conn)


# ---------------------------------------------------------------- Updates

def vtuple(v):
    nums = re.findall(r"\d+", (v or "0").split("-")[0])
    return tuple(int(x) for x in (nums + ["0", "0", "0"])[:3])


def can_self_update():
    if IS_MAC:
        return str(HERE).endswith(".app/Contents/Resources")
    if IS_WIN:
        return FROZEN
    return False


def pick_asset(assets):
    for a in assets:
        n = a.get("name", "")
        if IS_MAC and n.endswith("-mac.zip"):
            return a
        if IS_WIN and n.endswith("Windows.exe"):
            return a
    return None


_update_cache = {"t": 0, "data": None}


def check_update(force=False):
    base = {"current": APP_VERSION, "available": False, "latest": None}
    if "__" in GITHUB_REPO:
        return {**base, "reason": "Update-Server noch nicht eingerichtet"}
    if not force and _update_cache["data"] and time.time() - _update_cache["t"] < 1800:
        return _update_cache["data"]
    req = urllib.request.Request(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                                 headers={"User-Agent": APP_NAME, "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            rel = json.load(r)
    except Exception:
        return {**base, "reason": "Konnte nicht nach Updates suchen (offline?)"}
    latest = (rel.get("tag_name") or "").lstrip("v")
    asset = pick_asset(rel.get("assets", []))
    newer = vtuple(latest) > vtuple(APP_VERSION)
    data = {**base, "latest": latest, "newer": newer,
            "available": bool(asset) and newer and can_self_update(),
            "notes": (rel.get("body") or "")[:2000],
            "url": asset["browser_download_url"] if asset else None}
    _update_cache.update(t=time.time(), data=data)
    return data


def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": APP_NAME})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            f.write(chunk)


def install_update():
    info = check_update(force=True)
    if not info.get("available"):
        raise MailError("Kein Update verfügbar.")
    tmp = Path(tempfile.mkdtemp(prefix="mailsortierer-update-"))
    if IS_MAC:
        dl = tmp / "update.zip"
        download(info["url"], dl)
        subprocess.run(["ditto", "-x", "-k", str(dl), str(tmp / "neu")], check=True)
        new = next((tmp / "neu").glob("*.app"), None)
        if not new:
            raise MailError("Update-Datei ist beschädigt.")
        app = HERE.parents[1]
        script = tmp / "update.sh"
        script.write_text(f'''#!/bin/bash
PID={os.getppid()}
for i in $(seq 1 150); do kill -0 $PID 2>/dev/null || break; sleep 0.2; done
APP="{app}"
rm -rf "$APP.alt"
if mv "$APP" "$APP.alt" && ditto "{new}" "$APP"; then rm -rf "$APP.alt"; else rm -rf "$APP"; mv "$APP.alt" "$APP"; fi
xattr -dr com.apple.quarantine "$APP" 2>/dev/null
open "$APP"
rm -rf "{tmp}"
''', "utf-8")
        subprocess.Popen(["/bin/bash", str(script)], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"ok": True, "mode": "quit-app", "version": info["latest"]}
    if IS_WIN:
        dl = tmp / "MailSortierer-neu.exe"
        download(info["url"], dl)
        exe = Path(sys.executable)
        pid = os.getpid()
        bat = tmp / "update.cmd"
        bat.write_text(f'''@echo off
chcp 65001 >nul
:warte
tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul && (timeout /t 1 /nobreak >nul & goto warte)
move /y "{dl}" "{exe}" >nul
start "" "{exe}" --after-update
''', "utf-8")
        flags = 0x00000008 | 0x00000200 | 0x08000000   # DETACHED | NEW_GROUP | NO_WINDOW
        subprocess.Popen(["cmd", "/c", str(bat)], creationflags=flags, close_fds=True)
        threading.Timer(0.8, lambda: os._exit(0)).start()
        return {"ok": True, "mode": "restart", "version": info["latest"]}
    raise MailError("Updates werden hier nicht unterstützt.")


# ---------------------------------------------------------------- Webserver

def open_file(path):
    if IS_MAC:
        subprocess.run(["open", "-t", str(path)])
    elif IS_WIN:
        subprocess.Popen(["notepad.exe", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def guard(self):
        # nur Anfragen von dieser App selbst (Schutz vor fremden Webseiten)
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        ok_host = host in (f"127.0.0.1:{PORT}", f"localhost:{PORT}")
        ok_origin = origin in (None, f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}")
        if not (ok_host and ok_origin):
            self.send(403, {"error": "verboten"})
            return False
        return True

    def do_GET(self):
        global LAST_PING
        if not self.guard():
            return
        url = urlparse(self.path)
        try:
            if url.path in ("/", "/index.html"):
                self.send(200, (HERE / "index.html").read_bytes(), "text/html")
            elif url.path in ("/api/status", "/api/ping"):
                LAST_PING = time.time()
                cfg = read_json(CONFIG_FILE, {})
                ok = bool(cfg.get("email") and secret_get(cfg["email"]))
                platform = "mac" if IS_MAC else "windows" if IS_WIN else "andere"
                self.send(200, {"configured": ok, "email": cfg.get("email"),
                                "version": APP_VERSION, "platform": platform})
            elif url.path == "/api/mails":
                self.send(200, fetch_mails())
            elif url.path == "/api/body":
                uid = parse_qs(url.query).get("uid", [""])[0]
                self.send(200, {"text": get_body(uid)})
            elif url.path == "/api/update/check":
                force = parse_qs(url.query).get("force", ["0"])[0] == "1"
                self.send(200, check_update(force))
            else:
                self.send(404, {"error": "nicht gefunden"})
        except MailError as e:
            self.send(400, {"error": str(e)})
        except Exception as e:
            self.send(500, {"error": f"Fehler: {e}"})

    def do_POST(self):
        if not self.guard():
            return
        try:
            b = self.body()
            if self.path == "/api/setup":
                acc, pw = b.get("email", "").strip(), b.get("password", "").replace(" ", "")
                logout(connect(acc, pw))     # Anmeldung testen
                secret_set(acc, pw)
                write_json(CONFIG_FILE, {"email": acc, "server": IMAP_HOST})
                self.send(200, {"ok": True})
            elif self.path == "/api/delete":
                move_to_trash(str(b["uid"]))
                self.send(200, {"ok": True})
            elif self.path == "/api/restore":
                restore_from_trash(b["msgid"])
                self.send(200, {"ok": True})
            elif self.path == "/api/keep":
                kept = read_json(KEPT_FILE, [])
                if b["msgid"] not in kept:
                    kept.append(b["msgid"])
                    write_json(KEPT_FILE, kept[-5000:])
                self.send(200, {"ok": True})
            elif self.path == "/api/unkeep":
                write_json(KEPT_FILE, [k for k in read_json(KEPT_FILE, []) if k != b["msgid"]])
                self.send(200, {"ok": True})
            elif self.path == "/api/logout":
                cfg = read_json(CONFIG_FILE, {})
                if cfg.get("email"):
                    secret_delete(cfg["email"])
                write_json(CONFIG_FILE, {})
                self.send(200, {"ok": True})
            elif self.path == "/api/rules":
                load_rules()
                open_file(RULES_FILE)
                self.send(200, {"ok": True})
            elif self.path == "/api/update/install":
                self.send(200, install_update())
            elif self.path == "/api/quit":
                self.send(200, {"ok": True})
                threading.Timer(0.3, lambda: os._exit(0)).start()
            else:
                self.send(404, {"error": "nicht gefunden"})
        except MailError as e:
            self.send(400, {"error": str(e)})
        except Exception as e:
            self.send(500, {"error": f"Fehler: {e}"})


# ---------------------------------------------------------------- Fenster & Start

def open_window(url):
    """Windows: eigenes App-Fenster über Microsoft Edge. Sonst: Standardbrowser."""
    if IS_WIN:
        for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                     os.environ.get("LOCALAPPDATA")):
            if not base:
                continue
            edge = Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            if edge.exists():
                subprocess.Popen([str(edge), f"--app={url}", f"--user-data-dir={DATA_DIR / 'fenster'}",
                                  "--window-size=1220,840", "--no-first-run",
                                  "--no-default-browser-check", "--disable-features=Translate"])
                return
    webbrowser.open(url)


def watch_parent():
    """Mac-App: Dienst beenden, sobald das Fenster-Programm weg ist."""
    parent = os.getppid()
    while True:
        time.sleep(2)
        if os.getppid() != parent:
            os._exit(0)


def watch_heartbeat():
    """Windows: Dienst beenden, wenn das Fenster geschlossen wurde (keine Lebenszeichen mehr)."""
    while True:
        time.sleep(5)
        if time.time() - START_TIME > 90 and time.time() - LAST_PING > 45:
            os._exit(0)


def window_flow(url, after_update):
    if after_update:
        # Nach einem Update meldet sich das alte Fenster meist von selbst wieder
        t0 = time.time()
        while time.time() - t0 < 6:
            if LAST_PING > START_TIME:
                return
            time.sleep(0.25)
    open_window(url)


def selftest():
    ok = True

    def check(name, cond):
        nonlocal ok
        print(("OK      " if cond else "FEHLER  ") + name, flush=True)
        ok = ok and bool(cond)

    h = (b"From: Zalando <news@zalando.de>\r\nSubject: =?utf-8?q?50%_Rabatt?=\r\n"
         b"Message-ID: <a@x>\r\nList-Unsubscribe: <mailto:u@x>\r\n"
         b"Content-Type: text/plain; charset=utf-8\r\n\r\n")
    data = [(b"1 (UID 7 BODY[HEADER] {%d}" % len(h), h), (b" BODY[TEXT]<0> {5}", b"Hallo"), b")"]
    m = build_mail(parse_fetch(data)[0])
    check("Mail lesen", m["uid"] == "7" and m["subject"] == "50% Rabatt" and m["snippet"] == "Hallo")
    check("Kategorie erkennen", categorize(m, DEFAULT_RULES)["name"] == "Newsletter & Werbung")
    check("Versionen vergleichen", vtuple("1.10.0") > vtuple("1.9.3") > vtuple("0.0.0-dev"))
    check("HTML zu Text", "Zeile 2" in html_to_text("<p>Zeile 1</p><p>Zeile 2</p>", True))
    try:
        secret_set("selftest@example.com", "geheim-Ä123")
        got = secret_get("selftest@example.com")
        secret_delete("selftest@example.com")
        check("Passwort-Speicher", got == "geheim-Ä123" and secret_get("selftest@example.com") is None)
    except Exception as e:
        print(f"HINWEIS Passwort-Speicher nicht testbar: {e}", flush=True)
        if IS_WIN:
            ok = False
    load_rules()
    check("Regeln-Datei", RULES_FILE.exists())
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f"http://127.0.0.1:{PORT}/api/status", timeout=5) as r:
        st = json.load(r)
    check("Server antwortet", st.get("version") == APP_VERSION and st.get("configured") is False)
    with opener.open(f"http://127.0.0.1:{PORT}/", timeout=5) as r:
        check("Oberfläche wird ausgeliefert", b"Mail-Sortierer" in r.read())
    srv.shutdown()
    print("Version:", APP_VERSION, "| Repo:", GITHUB_REPO, flush=True)
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if IS_WIN and FROZEN:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        log = open(DATA_DIR / "log.txt", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
    app_mode = "--app" in sys.argv               # gestartet aus der Mac-App
    after_update = "--after-update" in sys.argv
    url = f"http://127.0.0.1:{PORT}/"
    load_rules()
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        # läuft schon -> nur ein Fenster öffnen
        if not app_mode and not after_update:
            open_window(url)
        return
    if app_mode:
        threading.Thread(target=watch_parent, daemon=True).start()
    elif IS_WIN:
        threading.Thread(target=window_flow, args=(url, after_update), daemon=True).start()
        threading.Thread(target=watch_heartbeat, daemon=True).start()
    else:
        threading.Timer(0.5, lambda: open_window(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
