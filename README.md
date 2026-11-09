# ✉️ Mail-Sortierer

Ein kostenloses Programm für **Mac und Windows**, das deine Gmail-Mails nach Kategorien sortiert und dich unwichtige Mails wie bei Tinder wegwischen lässt. Alles läuft lokal auf deinem Computer – ohne KI, ohne Abo, ohne Server.

- Startseite mit Kurz-Zusammenfassung („Was ist neu“)
- Posteingang nach Kategorien und Datum, mit Suche
- Sortieren mit Wischkarten: **Löschen** (in den Gmail-Papierkorb) oder **Behalten**
- Hell/Dunkel, eigene Akzentfarbe, Neon-Effekte
- Aktualisiert sich selbst, sobald es eine neue Version gibt

---

## Installieren

### Mac

**Variante A – ohne Sicherheitswarnung (empfohlen):** Terminal öffnen (⌘ + Leertaste, „Terminal“) und einfügen:

```bash
curl -fsSL https://raw.githubusercontent.com/felixwrk/mail-sortierer/main/install/mac.sh | bash
```

**Variante B – zum Doppelklicken:** Unter [Releases](https://github.com/felixwrk/mail-sortierer/releases/latest) die Datei `Mail-Sortierer-installieren-Mac.command` laden, dann **Rechtsklick → Öffnen**.

Beim allerersten Mal fragt der Mac evtl. nach den kostenlosen *Apple-Entwicklerwerkzeugen* (für Python). Auf „Installieren“ klicken und die Installation danach nochmal starten.

### Windows

**Variante A – ohne Sicherheitswarnung (empfohlen):** Startmenü → „PowerShell“ öffnen und einfügen:

```powershell
irm https://raw.githubusercontent.com/felixwrk/mail-sortierer/main/install/windows.ps1 | iex
```

**Variante B – zum Doppelklicken:** Unter [Releases](https://github.com/felixwrk/mail-sortierer/releases/latest) die Datei `Mail-Sortierer-installieren-Windows.cmd` laden und öffnen. Falls Windows warnt: „Weitere Informationen“ → „Trotzdem ausführen“.

Der Mail-Sortierer landet im Startmenü und auf dem Desktop und öffnet sich in einem eigenen Fenster.

### iPhone

Die iPhone-Version läuft als Web-App direkt im Browser: **https://felixwrk.github.io/mail-sortierer/**

In Safari öffnen → **Teilen** → **Zum Home-Bildschirm**. Beim ersten Start führt die App durch die einmalige, kostenlose Einrichtung bei Google (Gmail-Zugang) und meldet sich dann mit deinem Google-Konto an.

---

## Erster Start

1. Im Google-Konto die **Bestätigung in zwei Schritten** einschalten.
2. Auf [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) ein **App-Passwort** „Mail-Sortierer“ erstellen.
3. Gmail-Adresse und App-Passwort im Mail-Sortierer eingeben – fertig.

Das Passwort wird im Mac-Schlüsselbund bzw. in der Windows-Anmeldeinformationsverwaltung gespeichert, nicht in einer Datei.

## Updates

Beim Start prüft die App, ob es eine neue Version gibt. Dann erscheint oben **„Update verfügbar“** – ein Klick genügt, die App lädt die neue Version und startet neu. Anmeldung und Einstellungen bleiben erhalten. Manuell: ⚙️ Einstellungen → „Nach Updates suchen“.

## Kategorien anpassen

Account-Menü (oben rechts) → **Regeln bearbeiten**. Dort kannst du Absender und Betreff-Wörter ergänzen. Danach „Mails neu laden“.

---

## Für Entwickler

| Ordner | Inhalt |
|---|---|
| `app/` | Mail-Dienst (`mailsortierer.py`, nur Python-Standardbibliothek) und Oberfläche (`index.html`) |
| `mac/` | Fenster-Programm für den Mac (Swift/WebKit) |
| `install/` | Installationsskripte |
| `docs/` | iPhone-Web-App (GitHub Pages), gebaut mit `web/mkpwa.py` aus der Oberfläche + `web/gmail-backend.js` |
| `.github/workflows/` | Baut bei jeder neuen Nummer in `VERSION` automatisch Mac-App und Windows-EXE und veröffentlicht sie |

Neue Version veröffentlichen: Nummer in der Datei `VERSION` erhöhen und auf `main` hochladen – GitHub baut und veröffentlicht dann automatisch.

Selbsttest: `python3 app/mailsortierer.py --selftest`
