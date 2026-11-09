/*API*/
/* ===== Gmail-Anbindung direkt im Browser (keine Server, keine Kosten) =====
   Ersetzt die Demo-Daten: dieselben api()-Pfade wie die Mac/Windows-App, aber über die Gmail-Schnittstelle. */
const BUILTIN_CLIENT_ID = '544129934675-180k6p2vvlkqqgq9hoqbi242643dg2fi.apps.googleusercontent.com';
const GMAIL = 'https://gmail.googleapis.com/gmail/v1/users/me';
const SCOPE = 'https://www.googleapis.com/auth/gmail.modify';
const FIRST_BATCH = 80;

function lsGet(k){ try{ return localStorage.getItem(k); }catch(e){ return null; } }
function lsSet(k, v){ try{ localStorage.setItem(k, v); }catch(e){} }
function lsDel(k){ try{ localStorage.removeItem(k); }catch(e){} }
function clientId(){ return BUILTIN_CLIENT_ID || lsGet('ms.clientId') || ''; }
function redirectUri(){ return location.origin + location.pathname; }

/* ---- Anmeldung (OAuth per Weiterleitung, funktioniert auch als Home-Bildschirm-App) ---- */
function saveToken(tok, sec){ lsSet('ms.token', JSON.stringify({tok, exp: Date.now() + (sec-60)*1000})); }
function getToken(){ try{ const t = JSON.parse(lsGet('ms.token')||'null'); return t && t.exp > Date.now() ? t.tok : null; }catch(e){ return null; } }
function login(silent){
  const state = Math.random().toString(36).slice(2);
  lsSet('ms.state', state);
  const p = new URLSearchParams({client_id: clientId(), redirect_uri: redirectUri(), response_type: 'token',
    scope: SCOPE, include_granted_scopes: 'true', state, prompt: silent ? 'none' : 'select_account'});
  const hint = lsGet('ms.email'); if(hint) p.set('login_hint', hint);
  location.href = 'https://accounts.google.com/o/oauth2/v2/auth?' + p.toString();
}
class AuthError extends Error {}
let authRetryAt = 0;
function authExpired(){
  lsDel('ms.token');
  if(Date.now() - authRetryAt > 60000 && lsGet('ms.email')){
    authRetryAt = Date.now();
    toast('Anmeldung wird erneuert …');
    setTimeout(()=>login(true), 700);
  }
}
/* Google erlaubt nur eine begrenzte Zahl Anfragen pro Minute. Deshalb: gleichmäßig drosseln
   und bei einer Sperre ("Quota exceeded") kurz für alle Anfragen pausieren. */
const MIN_GAP_MS = 45;                    // höchstens ~22 Anfragen pro Sekunde
let nextSlot = 0, cooldownUntil = 0;
const sleep = ms => new Promise(res=>setTimeout(res, ms));
async function throttle(){
  for(;;){
    const now = Date.now();
    if(cooldownUntil > now){ await sleep(cooldownUntil - now); continue; }
    const slot = Math.max(now, nextSlot);
    nextSlot = slot + MIN_GAP_MS;
    if(slot > now) await sleep(slot - now);
    if(cooldownUntil <= Date.now()) return;
  }
}
class QuotaError extends Error {}
async function gfetch(url, opts={}, attempt=0){
  const tok = getToken();
  if(!tok){ authExpired(); throw new AuthError('Bitte neu anmelden.'); }
  await throttle();
  let r;
  try{ r = await fetch(url, {...opts, headers: {...(opts.headers||{}), Authorization: 'Bearer ' + tok}}); }
  catch(e){ throw new Error('Keine Verbindung zu Gmail. Bist du online?'); }
  if(r.status === 401){ authExpired(); throw new AuthError('Anmeldung abgelaufen.'); }
  let errBody = null;
  if(!r.ok){ try{ errBody = await r.json(); }catch(e){} }
  const msg = (errBody && errBody.error && errBody.error.message) || '';
  const quota = r.status === 429 || (r.status === 403 && /quota|rate ?limit/i.test(msg + JSON.stringify(errBody||{})));
  if(quota){
    const wait = [4000, 8000, 15000, 30000, 30000, 30000][attempt] || 30000;
    cooldownUntil = Math.max(cooldownUntil, Date.now() + wait + Math.random()*1500);
    if(attempt < 6) return gfetch(url, opts, attempt+1);
    throw new QuotaError('Google bremst gerade, weil sehr viele Mails auf einmal geladen werden. Die App lädt in ein paar Minuten automatisch weiter.');
  }
  if(r.status >= 500 && attempt < 4){ await sleep(800 * (attempt+1)); return gfetch(url, opts, attempt+1); }
  if(!r.ok) throw new Error(msg || ('Gmail-Fehler ' + r.status));
  return r.status === 204 ? {} : r.json();
}
async function pool(items, n, fn){
  const out = []; let i = 0;
  await Promise.all(Array.from({length: Math.min(n, items.length)}, async ()=>{
    while(i < items.length){
      const k = i++;
      try{ out[k] = await fn(items[k]); }catch(e){ if(e instanceof AuthError) throw e; out[k] = null; }
    }
  }));
  return out.filter(Boolean);
}

/* ---- Regeln (wie in der Mac/Windows-App) ---- */
const RULES = {
  kategorien: [
    {name:'Finanzen & Rechnungen', unwichtig:false, werbung_ausschliessen:true,
     absender:['paypal','sparkasse','volksbank','ing.de','dkb','comdirect','commerzbank','deutsche-bank','n26','klarna','postbank','finanzamt','elster'],
     woerter:['rechnung','invoice','zahlung','kontoauszug','lastschrift','mahnung','überweisung','beitrag']},
    {name:'Bestellungen & Versand', unwichtig:false, werbung_ausschliessen:true,
     absender:['amazon','ebay','dhl','dpd','hermes','ups.com','gls','zalando','otto.de','kleinanzeigen','temu','aliexpress'],
     woerter:['bestellung','versand','lieferung','sendung','paket','order','shipped','zugestellt','versandbestätigung']},
    {name:'Soziale Netzwerke', unwichtig:true, gmail:'CATEGORY_SOCIAL',
     absender:['facebook','facebookmail','instagram','linkedin','twitter','x.com','tiktok','xing','pinterest','reddit','discord','youtube','snapchat','whatsapp'], woerter:[]},
    {name:'Newsletter & Werbung', unwichtig:true, abmeldelink_zaehlt:true, gmail:'CATEGORY_PROMOTIONS',
     absender:['newsletter','news@','marketing','promo','angebote','info@','mailing'],
     woerter:['newsletter','angebot','rabatt','sale','gutschein','% ','deal','nur heute','jetzt sparen','black friday']},
    {name:'Benachrichtigungen', unwichtig:true,
     absender:['noreply','no-reply','donotreply','do-not-reply','notification','benachrichtigung','alert','mailer'],
     woerter:['benachrichtigung','notification','erinnerung']},
  ],
  rest: {name:'Persönlich & Sonstiges', unwichtig:false},
};
function categorize(m){
  const sender = (m.from_addr + ' ' + m.from_name).toLowerCase(), subject = m.subject.toLowerCase();
  for(const c of RULES.kategorien){
    const wordHit = c.woerter.some(w=>subject.includes(w)), senderHit = c.absender.some(a=>sender.includes(a));
    if(c.werbung_ausschliessen && m.bulk && !wordHit) continue;
    if(wordHit || senderHit) return c;
    if(c.abmeldelink_zaehlt && m.bulk) return c;
  }
  for(const c of RULES.kategorien){ if(c.gmail && (m.labels||[]).includes(c.gmail)) return c; }
  return RULES.rest;
}

/* ---- Zwischenspeicher auf dem iPhone ---- */
let GCACHE = null, gEmail = '';
const GSYNC = {running:false, loaded:0, total:0, error:null};
const TRASHED = {};
function cacheKey(){ return 'ms.cache.' + gEmail; }
function loadCache(){ if(!GCACHE){ try{ GCACHE = JSON.parse(lsGet(cacheKey())||'null'); }catch(e){} if(!GCACHE || !GCACHE.mails) GCACHE = {mails:{}}; } return GCACHE; }
let saveTimer = null;
function saveCache(now){
  clearTimeout(saveTimer);
  const doSave = ()=>{ try{ localStorage.setItem(cacheKey(), JSON.stringify(GCACHE)); }catch(e){ /* Speicher voll: dann eben ohne */ } };
  if(now) doSave(); else saveTimer = setTimeout(doSave, 1500);
}
function keptSet(){ try{ return new Set(JSON.parse(lsGet('ms.kept.' + gEmail)||'[]')); }catch(e){ return new Set(); } }
function saveKept(s){ lsSet('ms.kept.' + gEmail, JSON.stringify([...s].slice(-5000))); }

function decodeEntities(s){ const t = document.createElement('textarea'); t.innerHTML = s || ''; return t.value; }
function parseFrom(v){
  const m = (v||'').match(/^\s*"?([^"<]*?)"?\s*<([^>]+)>\s*$/);
  return m ? {name: m[1].trim() || m[2].trim(), addr: m[2].trim()} : {name: (v||'').trim(), addr: (v||'').trim()};
}
async function fetchMeta(id){
  const q = ['From','Subject','Date','List-Unsubscribe','Message-ID'].map(h=>'metadataHeaders='+h).join('&');
  const d = await gfetch(`${GMAIL}/messages/${id}?format=metadata&${q}`);
  const H = name => ((d.payload && d.payload.headers) || []).find(h=>h.name.toLowerCase()===name.toLowerCase())?.value || '';
  const from = parseFrom(H('From')), lu = H('List-Unsubscribe'), labels = d.labelIds || [];
  const links = [...lu.matchAll(/<([^>]+)>/g)].map(x=>x[1]);
  return {uid: d.id, msgid: H('Message-ID') || d.id, from_name: from.name, from_addr: from.addr,
    subject: H('Subject') || '(kein Betreff)', ts: Number(d.internalDate||0)/1000,
    snippet: decodeEntities(d.snippet).slice(0, 400), bulk: !!lu || labels.includes('CATEGORY_PROMOTIONS'),
    unsub: links.find(u=>u.startsWith('https://')) || links[0] || null,
    link: `https://mail.google.com/mail/u/0/#all/${d.id}`, labels};
}
async function listInboxIds(){
  const ids = []; let page = '';
  do{
    const d = await gfetch(`${GMAIL}/messages?labelIds=INBOX&maxResults=500${page ? '&pageToken='+page : ''}`);
    (d.messages||[]).forEach(m=>ids.push(m.id));
    page = d.nextPageToken || '';
  } while(page);
  return ids;
}
async function syncInbox(){
  const cache = loadCache();
  const ids = await listInboxIds();                     // neueste zuerst
  const present = new Set(ids);
  Object.keys(cache.mails).forEach(id=>{ if(!present.has(id)) delete cache.mails[id]; });
  const missing = ids.filter(id=>!cache.mails[id]);
  // Mit Zwischenspeicher: nur die wirklich neuen Mails sofort holen, alles andere im Hintergrund
  const firstCached = ids.findIndex(id=>cache.mails[id]);
  const now = firstCached < 0 ? missing.slice(0, FIRST_BATCH)
            : ids.slice(0, firstCached).filter(id=>!cache.mails[id]).slice(0, 60);
  (await pool(now, 5, fetchMeta)).forEach(m=>{ cache.mails[m.uid] = m; });
  saveCache(true);
  GSYNC.total = ids.length; GSYNC.loaded = Object.keys(cache.mails).length;
  const rest = missing.filter(id=>!cache.mails[id]);
  if(rest.length && !GSYNC.running) backgroundLoad(rest);
}
async function backgroundLoad(ids){
  let rest = ids;
  GSYNC.running = true; GSYNC.error = null;
  try{
    for(let round = 0; round < 3 && rest.length; round++){
      if(round) await sleep(30000);        // Nachzügler nach einer Pause erneut versuchen
      for(let i = 0; i < rest.length; i += 100){
        (await pool(rest.slice(i, i+100), 4, async id=>{ while(fgActive > 0) await sleep(150); return fetchMeta(id); })).forEach(m=>{ GCACHE.mails[m.uid] = m; });
        GSYNC.loaded = Object.keys(GCACHE.mails).length;
        saveCache();
      }
      rest = rest.filter(id=>!GCACHE.mails[id]);
    }
  }catch(e){ GSYNC.error = e.message; }
  finally{ saveCache(true); GSYNC.running = false; }
}
function mailsResponse(){
  const kept = keptSet();
  const mails = Object.values(loadCache().mails).map(m=>{
    const c = categorize(m);
    return {...m, category: c.name, unwichtig: !!c.unwichtig, kept: kept.has(m.msgid)};
  }).sort((a,b)=>b.ts-a.ts);
  return {mails, categories: [...RULES.kategorien, RULES.rest].map(c=>({name:c.name, unwichtig:!!c.unwichtig})), sync: {...GSYNC}};
}

/* ---- Volltext ---- */
function b64u(data, charset){
  const bin = atob(data.replace(/-/g,'+').replace(/_/g,'/'));
  const bytes = Uint8Array.from(bin, c=>c.charCodeAt(0));
  try{ return new TextDecoder(charset || 'utf-8').decode(bytes); }catch(e){ return new TextDecoder('utf-8').decode(bytes); }
}
function findPart(p, type){
  if(!p) return null;
  if(p.mimeType === type && p.body && p.body.data) return p;
  for(const c of p.parts || []){ const r = findPart(c, type); if(r) return r; }
  return null;
}
function partCharset(p){ const ct = (p.headers||[]).find(h=>h.name.toLowerCase()==='content-type')?.value || ''; return (ct.match(/charset="?([^";]+)/i)||[])[1]; }
function htmlToPlain(html){
  const doc = new DOMParser().parseFromString(html, 'text/html');
  doc.querySelectorAll('script,style,head').forEach(e=>e.remove());
  doc.querySelectorAll('br,p,div,tr,li,h1,h2,h3,h4,h5,table,blockquote').forEach(e=>e.append('\n'));
  return doc.body ? doc.body.textContent : '';
}
async function getBody(id){
  const d = await gfetch(`${GMAIL}/messages/${id}?format=full`);
  const plain = findPart(d.payload, 'text/plain'), html = findPart(d.payload, 'text/html');
  let text = plain ? b64u(plain.body.data, partCharset(plain)) : html ? htmlToPlain(b64u(html.body.data, partCharset(html))) : decodeEntities(d.snippet);
  text = text.replace(/\r/g,'').split('\n').map(l=>l.replace(/[ \t ]+/g,' ').trim()).join('\n').replace(/\n{3,}/g,'\n\n').trim();
  return text.slice(0, 30000) || '(Diese Mail enthält keinen lesbaren Text.)';
}

/* ---- dieselben Pfade wie die Mac/Windows-App ---- */
let fgActive = 0;
async function api(path, body){
  const fg = /^\/api\/(body|delete|restore|status)/.test(path);
  if(fg) fgActive++;
  try{ return await apiInner(path, body); } finally { if(fg) fgActive--; }
}
async function apiInner(path, body){
  const [p, q] = path.split('?');
  const qs = new URLSearchParams(q || '');
  if(p === '/api/status'){
    if(!getToken()) return {configured:false};
    if(!gEmail){
      const prof = await gfetch(`${GMAIL}/profile`);
      gEmail = prof.emailAddress; lsSet('ms.email', gEmail);
    }
    return {configured:true, email:gEmail, platform:'iphone'};
  }
  if(p === '/api/mails'){
    if(qs.get('cached') !== '1') await syncInbox();
    return mailsResponse();
  }
  if(p === '/api/sync') return {...GSYNC};
  if(p === '/api/body') return {text: await getBody(qs.get('uid'))};
  if(p === '/api/delete'){
    await gfetch(`${GMAIL}/messages/${body.uid}/trash`, {method:'POST'});
    const m = loadCache().mails[body.uid];
    if(m){ TRASHED[m.msgid] = m; delete GCACHE.mails[body.uid]; saveCache(); }
    return {ok:true};
  }
  if(p === '/api/restore'){
    const m = TRASHED[body.msgid];
    if(!m) throw new Error('Mail nicht mehr im Papierkorb gefunden.');
    await gfetch(`${GMAIL}/messages/${m.uid}/untrash`, {method:'POST'});
    loadCache().mails[m.uid] = m; delete TRASHED[body.msgid]; saveCache();
    return {ok:true};
  }
  if(p === '/api/keep'){ const s = keptSet(); s.add(body.msgid); saveKept(s); return {ok:true}; }
  if(p === '/api/unkeep'){ const s = keptSet(); s.delete(body.msgid); saveKept(s); return {ok:true}; }
  throw new Error('Unbekannte Aktion');
}
function signOut(){
  const tok = getToken();
  if(tok) fetch('https://oauth2.googleapis.com/revoke?token=' + encodeURIComponent(tok), {method:'POST', mode:'no-cors'}).catch(()=>{});
  lsDel('ms.token'); lsDel(cacheKey()); lsDel('ms.email');
  GCACHE = null; gEmail = '';
}
/*END-API*/