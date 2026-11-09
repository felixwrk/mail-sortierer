#!/usr/bin/env python3
"""Baut die iPhone-Web-App (docs/index.html) aus der iPhone-Oberfläche + Gmail-Anbindung."""
import sys, re
src, backend, out = sys.argv[1], sys.argv[2], sys.argv[3]
s = open(src, encoding='utf-8').read()
def rep(old, new, count=1):
    global s
    n = s.count(old)
    assert n == count, f"{n}x: {old[:90]!r}"
    s = s.replace(old, new)

HEAD = '''<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Mail-Sortierer</title>
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Mail-Sortierer">
<meta name="theme-color" content="#0b0d12">
<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="icon" type="image/png" href="icon-192.png">
'''
rep('<title>Mail-Sortierer iPhone</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n', HEAD)
rep('</style>\n', '''html,body{height:100%;margin:0}
[hidden]{display:none !important}
:root{padding:0}
/* Einrichtung */
.setup-g{flex-direction:column;gap:14px;overflow:auto;padding-block:8px 24px}
.setup-g h1{margin:4px 0 0;font:800 24px var(--display);letter-spacing:-.02em}
.setup-g p{margin:0;color:var(--muted);font-size:14px}
.steps{display:flex;flex-direction:column;gap:10px;margin:0;padding:0;list-style:none;counter-reset:st}
.steps li{position:relative;padding:12px 14px 12px 48px;border-radius:16px;background:var(--surface);border:1px solid var(--line);font-size:14px;line-height:1.5;counter-increment:st}
.steps li::before{content:counter(st);position:absolute;left:14px;top:12px;width:24px;height:24px;border-radius:50%;display:grid;place-items:center;background:var(--accent);color:var(--accent-ink);font:800 12px var(--display);box-shadow:0 0 12px var(--glow)}
.steps a{color:var(--accent-text);font-weight:700}
.steps code{font:600 12.5px ui-monospace,Menlo,monospace;background:var(--surface-2);padding:2px 6px;border-radius:6px;word-break:break-all}
.cid{display:flex;flex-direction:column;gap:8px;padding:14px;border-radius:16px;background:var(--surface);border:1px solid color-mix(in srgb,var(--accent) 45%,transparent);box-shadow:0 0 22px var(--glow)}
.cid label{font-weight:700;font-size:14px}
.cid input{width:100%;padding:12px;border-radius:12px;border:1px solid var(--line);background:var(--surface-2);color:var(--ink);font:14px ui-monospace,Menlo,monospace}
.cid .gbtn{max-width:none}
.cid .err{color:var(--del-text);font-size:13px;min-height:1em}
.signin .err{color:var(--del-text);font-size:13.5px;max-width:32ch}
</style>
</head>
<body>
''')
s = s.rstrip() + '\n</body>\n</html>\n'

# Demo-Hinweise raus
rep(' (In dieser Demo wird die Anmeldung nur simuliert.)', '')
rep('<p class="frame-cap">iPhone-Vorschau mit Beispiel-Mails · hier wird nichts wirklich gelöscht</p>\n', '')
s = re.sub(r'\s*<button type="button" id="resetBtn">.*?Demo zurücksetzen</button>', '', s, count=1, flags=re.S)
rep("$('#resetBtn').onclick = ()=>{ $('#drop').hidden=true; resetDemo(); load('home'); toast('Demo zurückgesetzt'); };\n", '')
rep('const IS_DEMO = true;', 'const IS_DEMO = false;')
rep('''<small>Beim ersten Mal zeigt Google''', '''<div class="err" id="signinErr"></div>
    <small>Beim ersten Mal zeigt Google''')

# Volltext im Mail-Fenster nachladen
rep("""    <div class="mm-body">${esc(m.body || m.snippet)}</div>""","""    <div class="mm-body${m.body ? '' : ' loading'}">${esc(m.body || m.snippet)}</div>""")
rep("""  setTimeout(()=>modal.querySelector('[data-a="close"]').focus({preventScroll:true}), 60);
}""","""  setTimeout(()=>modal.querySelector('[data-a="close"]').focus({preventScroll:true}), 60);
  if(!m.body){
    api('/api/body?uid=' + encodeURIComponent(m.uid)).then(r=>{
      m.body = r.text;
      if(modalMail === m){ const el = modal.querySelector('.mm-body'); el.textContent = r.text; el.classList.remove('loading'); }
    }).catch(()=>{ const el = modal.querySelector('.mm-body'); if(el) el.classList.remove('loading'); });
  }
}""")
s = s.replace('.signin .err{', '.mm-body.loading{color:var(--muted)}\n.signin .err{', 1)

# Einrichtungs-Ansicht
rep('''  <section class="view signin" id="v-signin" hidden>''','''  <section class="view setup-g" id="v-setup" hidden>
    <div><h1>Einmal einrichten</h1><p>Damit die App direkt mit Gmail sprechen darf, braucht sie einen kostenlosen Zugang bei Google. Das dauert etwa 10 Minuten und ist nur einmal nötig.</p></div>
    <ol class="steps">
      <li>Öffne <a href="https://console.cloud.google.com/projectcreate" target="_blank" rel="noopener">console.cloud.google.com</a> und erstelle ein Projekt namens <b>Mail-Sortierer</b>.</li>
      <li>Suche oben nach <b>Gmail API</b> und klicke auf <b>Aktivieren</b>.</li>
      <li>Öffne <b>Google Auth Platform</b> → <b>Branding</b>: App-Name „Mail-Sortierer“, deine Mail als Support-Adresse. Bei <b>Zielgruppe</b> „Extern“ wählen und unter <b>Testnutzer</b> deine Gmail-Adresse hinzufügen.</li>
      <li>Unter <b>Clients</b> → <b>Client erstellen</b> → Typ <b>Webanwendung</b>. Bei „Autorisierte JavaScript-Quellen“ eintragen: <code id="originTxt"></code> und bei „Autorisierte Weiterleitungs-URIs“: <code id="redirectTxt"></code></li>
      <li>Die angezeigte <b>Client-ID</b> kopieren und hier einfügen:</li>
    </ol>
    <form class="cid" id="cidForm">
      <label for="cidInput">Client-ID</label>
      <input id="cidInput" type="text" placeholder="123456-abc.apps.googleusercontent.com" autocomplete="off" spellcheck="false" autocapitalize="off">
      <div class="err" id="cidErr"></div>
      <button class="gbtn" type="submit">Speichern und anmelden</button>
    </form>
  </section>

  <section class="view signin" id="v-signin" hidden>''')

# Gmail statt Demo-Daten
a = s.index('/*API*/'); b = s.index('/*END-API*/') + len('/*END-API*/')
s = s[:a] + open(backend, encoding='utf-8').read().strip() + s[b:]

# Start-Ablauf
a = s.index("$('#gSignIn').onclick = ()=>{")
b = s.index("\nshow('signin');", a) + len("\nshow('signin');")
s = s[:a] + '''$('#gSignIn').onclick = ()=>{ if(!clientId()){ show('setup'); return; } login(false); };
$('#signOutBtn').onclick = ()=>{ $('#drop').hidden = true; $('#account').hidden = true; signOut(); show('signin'); toast('Abgemeldet'); };
$('#originTxt').textContent = location.origin;
$('#redirectTxt').textContent = location.origin + location.pathname;
$('#cidForm').addEventListener('submit', e=>{
  e.preventDefault();
  const v = $('#cidInput').value.trim();
  if(!/\\.apps\\.googleusercontent\\.com$/.test(v)){ $('#cidErr').textContent = 'Das sieht nicht nach einer Client-ID aus. Sie endet auf .apps.googleusercontent.com'; return; }
  lsSet('ms.clientId', v); login(false);
});
function tick(){ const el = $('#sbTime'); if(el) el.textContent = new Date().toLocaleTimeString('de-DE',{hour:'2-digit', minute:'2-digit'}); }
function boot(){
  const h = new URLSearchParams(location.hash.slice(1));
  if(h.get('access_token') || h.get('error')) window.history.replaceState(null, '', location.pathname);
  if(h.get('access_token') && h.get('state') === lsGet('ms.state')){
    saveToken(h.get('access_token'), Number(h.get('expires_in')) || 3600);
    try{ sessionStorage.removeItem('ms.silent'); }catch(e){}
  }
  if(!clientId()){ show('setup'); return; }
  if(getToken()){
    start().catch(e=>{ if(e instanceof AuthError) return; show('signin'); $('#signinErr').textContent = e.message; });
    return;
  }
  let tried = false; try{ tried = sessionStorage.getItem('ms.silent') === '1'; }catch(e){}
  if(lsGet('ms.email') && !tried && !h.get('error')){ try{ sessionStorage.setItem('ms.silent','1'); }catch(e){} login(true); return; }
  if(h.get('error') && h.get('error') !== 'interaction_required' && h.get('error') !== 'login_required')
    $('#signinErr').textContent = h.get('error') === 'access_denied' ? 'Anmeldung abgebrochen. Du musst den Zugriff auf Gmail erlauben.' : 'Anmeldung fehlgeschlagen (' + h.get('error') + ').';
  show('signin');
}
boot();
// Falls Google ohne Neuladen der Seite zurückleitet (nur der #-Teil ändert sich)
addEventListener('hashchange', ()=>{ if(/access_token=|error=/.test(location.hash)) boot(); });
if('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(()=>{});''' + s[b:]

# kein iPhone-Rahmen in der echten App
assert 'applyFrame' not in s and 'resetDemo' not in s and 'DEMO_STATE' not in s, 'Demo-Reste gefunden'
open(out, 'w', encoding='utf-8').write(s)
print('ok', len(s))
