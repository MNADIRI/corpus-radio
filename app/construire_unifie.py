#!/usr/bin/env python3
"""Assemble l'application unique « Radiologie » :
  - base : la page Learning Radiology (Apprentissage), inchangée sauf les entrées de révision, qui renvoient vers Cas ;
  - outils : app/radiologie.html (Notes, Bibliothèque, Cas), monté dans un composant isolé (shadow DOM)
    pour que styles et identifiants ne se mélangent pas ; les couleurs suivent les mêmes jetons ;
  - une barre « espaces » en tête et un pont window.LR vers la progression d'Apprentissage.
Usage : python3 app/construire_unifie.py <learning.html> <radiologie.html> <sortie.html>"""
import json
import re
import sys
from pathlib import Path

learning, outils, sortie = (Path(a) for a in sys.argv[1:4])
L = learning.read_text(encoding="utf-8")
O = outils.read_text(encoding="utf-8")


def rep(s, old, new, count=1):
    n = s.count(old)
    if n != count:
        sys.exit(f"Remplacement introuvable ({n}×) : {old[:90]!r}")
    return s.replace(old, new)


# ---------------------------------------------------------------- outils : CSS, balisage, script
css = "".join(re.findall(r"<style>(.*?)</style>", O, re.S))
css = css.replace(':root:not([data-theme="light"])', ":host").replace(':root[data-theme="dark"]', ':host-context([data-theme="dark"])')
css = css.replace(":root", ":host").replace("html,body{", ":host{").replace("body::before{", ".jamais{").replace("\nbody{", "\n:host{display:block;")
css += """
.tabs{display:none!important}
:host{padding:0!important;display:block}
.top{top:var(--esp-h,0px)!important;background:var(--bg)!important}
.topin,.desk{max-width:1180px!important}
.domwrap{display:none!important}
.desk.cas{grid-template-columns:minmax(0,1fr)!important}
.desk.cas .pane-left{display:none!important}
.desk.cas .pane-right{display:grid!important;max-width:980px;width:100%;margin:0 auto}
:host(.hors-notes) #newBtn{display:none!important}
@media (max-width:720px){#newBtn{display:none!important}.topin{gap:8px!important}}
"""
corps = O[O.rindex("</style>") + len("</style>"):O.rindex("<script>")]
js = O[O.rindex("<script>") + len("<script>"):O.rindex("</script>")]
js = rep(js, 'const $ = (id) => document.getElementById(id);', 'const $ = (id) => ROOT.getElementById(id);')
js = rep(js, 'if (location.hash.slice(1) !== h) { try { location.hash = h; } catch {} }', '')
js = rep(js, 'window.addEventListener("hashchange", routeFromHash);', '')
js = rep(js, '\nrouteFromHash();\n', '\n')
js = rep(js, 'document.addEventListener("click"', 'ROOT.addEventListener("click"', 2)
js = rep(js, 'document.addEventListener("keydown", (e) => {', 'document.addEventListener("keydown", (e) => { if (!window.OUTILS_VISIBLE) return;')
js = rep(js, 'document.querySelectorAll("[data-tab]")', 'ROOT.querySelectorAll("[data-tab]")')
js = rep(js, 'if (location.hash === "#bibliotheque") S.tab = "biblio";', '')
js = rep(js, 'html = progressionHtml() + homeHtml();', 'html = homeHtml();')
js = rep(js, 'history.replaceState(null, "", d.tab === "biblio" ? "#bibliotheque" : location.pathname + location.search); ', '')
js += '''
window.OUTILS = { domaine: (d) => changerDomaine(d), domaines: () => (S.manifest ? domainesDisponibles() : []), livreDomaines: (id) => { const b = S.bookById.get(id); return b ? b.domaines : null; }, onglet(t) { S.tab = t; HOTE.classList.toggle("hors-notes", t !== "notes"); S.detail = false; $("desk").classList.toggle("cas", t === "cas");
  if (t === "biblio" && S.entState === "idle") chargerEntites();
  if (t === "cas" && S.cas.mode === "alea" && S.cas.etat === "vide" && S.manifest) tirerCas();
  $("q").value = t === "biblio" ? S.bq : t === "notes" ? S.query : ""; $("q").closest(".searchwrap").hidden = t === "cas"; render(); } };
'''
outils_js = ("(function(){\n\"use strict\";\nconst HOTE = document.getElementById(\"outils\");\nconst ROOT = HOTE.attachShadow({ mode: \"open\" });\n"
             f"ROOT.innerHTML = {json.dumps('<style>' + css + '</style>' + corps)};\n" + js.replace('"use strict";', "", 1) + "\n})();")
outils_js = outils_js.replace("</script", "<\\/script")

# ---------------------------------------------------------------- base Learning
L = L[L.index("<title>"):]
L = re.sub(r"</body></html>\s*$", "", L)
L = rep(L, "<title>Learning Radiology</title>", '<title>Radiologie</title>\n<meta name="claude:viewport-fit-sides" content="cover">' if 'claude:viewport-fit-sides' not in L else "<title>Radiologie</title>")
ICO = {
  "apprentissage": '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 4.5h5.5a2 2 0 0 1 2 2V16a1.6 1.6 0 0 0-1.6-1.6H3zM17 4.5h-5.5a2 2 0 0 0-2 2V16a1.6 1.6 0 0 1 1.6-1.6H17z"/></svg>',
  "notes": '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 3h7l3 3v11H5z"/><path d="M8 9h5M8 12h5"/></svg>',
  "cas": '<svg viewBox="0 0 20 20" aria-hidden="true"><rect x="3" y="3" width="14" height="14" rx="2"/><circle cx="10" cy="9" r="3"/><path d="M6 16c.8-2 2.2-3 4-3s3.2 1 4 3"/></svg>',
  "biblio": '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 3v14M8 3v14M12 4l3.5 12.5"/></svg>',
}
LIB = {"apprentissage": "Apprentissage", "notes": "Notes", "cas": "Cas", "biblio": "Bibliothèque"}
boutons = "".join(f'<button data-esp="{k}"{" aria-current=\"page\"" if k == "apprentissage" else ""}>{ICO[k]}<span>{v}</span></button>' for k, v in LIB.items())
L = rep(L, '<header class="top">', f'''<nav class="espaces" id="espaces" aria-label="Espaces"><div class="esp-in"><span class="esp-brand">Radiologie</span><div class="esp-tabs">{boutons}</div><label class="esp-dom"><span class="sr">Domaine</span><select id="domGlobal" aria-label="Domaine"><option value="tous">Tous les domaines</option></select></label></div></nav>
<header class="top">''')
L = rep(L, '<main class="wrap" id="app"></main>', '<main class="wrap" id="app"></main>\n<div id="outils" hidden></div>')
ds = L.index("<script>")
tete, script = L[:ds], L[ds:]
script = script.replace('"Bibliothèque MSK"', '"Apprentissage"').replace("<h1>Bibliothèque</h1>", "<h1>Apprentissage</h1>").replace("Retour à la bibliothèque", "Retour aux ouvrages").replace(">Bibliothèque<", ">Ouvrages<").replace('"Bibliothèque"', '"Ouvrages"')
tete = tete.replace(">Bibliothèque MSK<", ">Apprentissage<").replace(">Bibliothèque<", ">Ouvrages<")
L = tete + script
L = L.replace('<button data-esp="biblio">' + ICO["biblio"] + '<span>Ouvrages</span>', '<button data-esp="biblio">' + ICO["biblio"] + '<span>Bibliothèque</span>')
# classement : progression calculée sur les modules qui ont une leçon (les chapitres « à créer » ne pèsent pas)
L = rep(L, """function playerSummary(){
  const all=Math.round(ALL.reduce((s,m)=>s+prog(m).all,0)/ALL.length);
  const books={}; BOOKS.forEach(b=>books[b.id]=bookProg(b).all);
  return {pseudo:(S.pseudo||"").slice(0,40), all, books, done:ALL.filter(isDone).length, nmod:ALL.length,
    ans:ALL.reduce((s,m)=>s+quizAns(m),0), nq:ALL.reduce((s,m)=>s+m.quiz.length,0),
    steps:ALL.reduce((s,m)=>s+stepsDone(m),0), nsteps:ALL.reduce((s,m)=>s+steps(m).length,0),""", """function playerSummary(){
  const AR=ALL.filter(m=>!m.stub);
  const all=Math.round(AR.reduce((s,m)=>s+prog(m).all,0)/Math.max(1,AR.length));
  const books={}; BOOKS.filter(b=>b.modules.some(m=>!m.stub)).forEach(b=>books[b.id]=bookProg(b).all);
  return {pseudo:(S.pseudo||"").slice(0,40), all, books, done:AR.filter(isDone).length, nmod:AR.length,
    ans:AR.reduce((s,m)=>s+quizAns(m),0), nq:AR.reduce((s,m)=>s+m.quiz.length,0),
    steps:AR.reduce((s,m)=>s+stepsDone(m),0), nsteps:AR.reduce((s,m)=>s+steps(m).length,0),""")
# révision : déplacée dans Cas
i = L.index("function rapidSection(){")
j = L.index("\nfunction ", i + 10)
L = L[:i] + '''function rapidSection(){
  const n=rqTodo().length+dueMissed().length;
  return `<section class="today rapidsec"><div class="label">Révision</div><h2>${n?`${n} éléments à revoir`:"Rien à revoir pour l'instant"}</h2>
  <p class="muted">Les erreurs de QCM et de défis du jour, les cas ratés et les révisions sur tes notes sont regroupés dans l'espace Cas.</p>
  <div class="row"><button class="btn primary" data-vers-cas="1">Ouvrir la révision</button></div></section>`;
}''' + L[j:]
L = re.sub(r'<button class="btn primary" id="revBtn">[^<]*</button>', '<button class="btn primary" data-vers-cas="1">Réviser dans Cas</button>', L)

css_esp = '''
.espaces{position:sticky;top:0;z-index:12;margin-inline:-16px;padding:8px 16px;padding-top:calc(8px + env(safe-area-inset-top,0px));background:var(--bg);border-bottom:1px solid var(--line)}
.esp-in{max-width:1180px;margin:0 auto;display:flex;align-items:center;gap:16px}
.esp-brand{font-family:var(--display,Georgia,serif);font-weight:650;font-size:17px;color:var(--fg);margin-right:auto}
.esp-tabs{order:2}.esp-dom{order:3}
.esp-tabs{display:flex;gap:2px;background:var(--sunk);border:1px solid var(--line);border-radius:999px;padding:3px}
.espaces button{display:inline-flex;align-items:center;gap:6px;border:0;background:none;color:var(--muted);font:500 13.5px var(--body,system-ui);padding:6px 14px;border-radius:999px;cursor:pointer}
.espaces button svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}
.espaces button:hover{color:var(--fg)}
.espaces button[aria-current="page"]{background:var(--surface);color:var(--fg);box-shadow:0 1px 2px rgba(0,0,0,.12)}
.espaces button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
body.esp-outils header.top,body.esp-outils #app,body.esp-outils #fab{display:none!important}
header.top{top:var(--esp-h,0px)}
.domh{font-family:var(--display,Georgia,serif);font-size:20px;margin:22px 0 8px;grid-column:1/-1}
.esp-dom select{font:500 13px var(--body,system-ui);color:var(--fg);background:var(--surface);border:1px solid var(--line);border-radius:999px;padding:6px 30px 6px 12px;max-width:260px}
header.top{background:var(--bg)!important;padding-block:8px!important}
header.top .brand b{font-family:var(--display,Georgia,serif);font-size:16px}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.navlivre{display:grid;grid-template-columns:1fr;gap:8px;align-items:center;margin:28px 0 8px;padding-top:14px;border-top:1px solid var(--line)}
.navlivre button{font:500 13.5px var(--body,system-ui);color:var(--fg);background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:9px 12px;cursor:pointer;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.navlivre button{text-align:center}.navlivre button[data-som]{color:var(--accent);font-weight:600}
.navlivre button:disabled{opacity:.4;cursor:default}.navlivre button:not(:disabled):hover{border-color:var(--accent)}
.somm{position:fixed;inset:0;z-index:40;display:grid;grid-template-columns:1fr min(420px,92vw);background:rgba(5,8,12,.45)}
.somm>div{background:var(--bg);border-left:1px solid var(--line);overflow:auto;padding:calc(16px + env(safe-area-inset-top,0px)) 16px calc(24px + env(safe-area-inset-bottom,0px))}
.somm h2{font-family:var(--display,Georgia,serif);font-size:20px;margin:4px 0 2px}.somm ol{list-style:none;margin:12px 0 0;padding:0;display:grid;gap:4px}
.somm li button{width:100%;display:grid;grid-template-columns:2em 1fr auto;gap:8px;align-items:center;text-align:left;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--fg);font:13.5px var(--body,system-ui);cursor:pointer}
.somm li button.cur{border-color:var(--accent);background:var(--accent-soft)}.somm li button:disabled{opacity:.55;cursor:default}
.somm .st{font-size:11.5px;color:var(--muted);font-variant-numeric:tabular-nums}.somm .ok{color:var(--good)}.somm .n{font-family:var(--mono,monospace);color:var(--muted)}
@media (max-width:720px){
  .esp-in{gap:10px}.esp-brand{font-size:16px}.esp-dom{margin-left:auto}.esp-dom select{max-width:52vw}
  .esp-tabs{position:fixed;left:0;right:0;bottom:0;z-index:30;display:flex;justify-content:space-around;margin:0;padding:4px 6px calc(4px + env(safe-area-inset-bottom,0px));background:var(--surface);border:0;border-top:1px solid var(--line);border-radius:0}
  .espaces button{flex:1;flex-direction:column;gap:2px;font-size:11px;padding:6px 2px;border-radius:10px}
  .espaces button svg{width:21px;height:21px}
  .espaces button[aria-current="page"]{background:var(--accent-soft);color:var(--accent);box-shadow:none}
  body{padding-bottom:calc(76px + env(safe-area-inset-bottom,0px))!important}
  .navlivre button[data-som]{text-align:center}
}
'''
L = rep(L, "</style>", css_esp + "</style>", L.count("</style>")) if False else L
k = L.rindex("</style>", 0, L.index("<header") if "<header" in L else len(L))
L = L[:k] + css_esp + L[k:]

# ---------------------------------------------------------------- nouveaux ouvrages : un module par chapitre, leçon créée à la demande
RAC = Path(__file__).resolve().parent.parent
SUPP = [("cotten-t2", "cotten2", "d", "Cotten t2", "A. Cotten", "Imagerie musculosquelettique,", "Pathologies locorégionales"),
        ("laredo-t5", "laredo5", "e", "Laredo t5", "J.-D. Laredo", "Imagerie rhumatologique et orthopédique,", "Tumeurs et pseudotumeurs des tissus mous")]
livres_supp = []
for lid, bid, pre, court, aut, sub, titre in SUPP:
    Lj = json.loads((RAC / "livres" / lid / "livre.json").read_text())
    mods = [{"id": f"{pre}{c['n']:02d}", "title": c["titre"], "chapter": f"Chapitre {c['n']}", "pages": "", "goals": [], "essentials": [],
             "intro": "", "lesson": None, "cards": [], "quiz": [], "book": bid, "subs": [], "stub": True, "src": {"livre": lid, "ch": c["n"]}}
            for c in Lj["chapitres"] if c["n"] > 0]
    livres_supp.append({"id": bid, "title": titre, "short": court, "author": aut, "sub": sub, "domaine": "msk", "modules": mods})
L = rep(L, "const BOOKS = DATA.books;", "DATA.books.forEach(b=>{ b.domaine=b.domaine||\"msk\"; });\nconst BOOKS = DATA.books.concat(" + json.dumps(livres_supp, ensure_ascii=False) + ");")
L = rep(L, "function renderModule(app){", "function renderModule(app){ { const m0=modById[view.id]; if(m0&&m0.stub) return renderStub(app,m0); }")
L = rep(L, "function loadBundle(mid){", "function loadBundle(mid){ if(String(mid).includes(\":\")){ if(!BUN[mid]) BUN[mid]=(window.OUTILS_IMG?window.OUTILS_IMG(mid):Promise.resolve(null)).then(u=>{ if(!u) throw 0; IMG[mid]=u; }).catch(()=>{ setTimeout(()=>{ delete BUN[mid]; },5000); }); return BUN[mid]; }")
L = rep(L, "const cards=BOOKS.map(b=>{", "const cards=parDomaine(BOOKS,b=>{")
L = rep(L, "</div></article>`;}).join(\"\");", "</div></article>`;});")

pont = '''
/* ---------- pont vers les outils (Notes, Cas, Bibliothèque) ---------- */
window.LR = { etat: () => S, sauver: save, aller: go, startReview, startRapid, rqTodo, rqAll, dueMissed, dueCards, modById, BOOKS, ALL,
  repondre(mid, i, oi) { const m = modById[mid], q = m.quiz[i], qid = quizId(m, i); S.ans[qid] = 1; if (oi === q.answer) delete S.missed[qid]; else { S.missed[qid] = today() + DAY; S.wrong[qid] = { at: now() }; } S.log[today()] = (S.log[today()] || 0) + 1; save(); return oi === q.answer; },
  image(k) { if (!k) return Promise.resolve(null); if (IMG[k]) return Promise.resolve(IMG[k]); return Promise.resolve(loadBundle(String(k).includes(":") ? k : k.split("/")[0])).then(() => IMG[k] || null); } };
function libDomaineLR(d) { return ({ msk: "Musculosquelettique", neuro: "Neuroradiologie", "tete-cou": "Tête et cou", thorax: "Thorax", "cardio-vasc": "Cardiovasculaire", "abdo-digestif": "Abdomen et digestif", "uro-genital": "Urogénital", sein: "Sein", pediatrie: "Pédiatrie", interventionnel: "Radiologie interventionnelle" })[d] || d; }
function parDomaine(books, carte) {
  const vis = books.filter(livreDansDomaine);
  if (!vis.length) return `<p class="muted" style="grid-column:1/-1">Aucun ouvrage d'apprentissage dans ce domaine pour l'instant. Choisis « Tous les domaines » dans la barre du haut.</p>`;
  books = vis;
  const g = {}; for (const b of books) (g[b.domaine || "msk"] = g[b.domaine || "msk"] || []).push(b);
  return Object.entries(g).map(([d, bs]) => `<h2 class="domh">${esc(libDomaineLR(d))}</h2>` + bs.map(carte).join("")).join("");
}
function renderStub(app, m) {
  const bk = BOOK[m.book];
  app.innerHTML = `<div class="crumbs"><button data-lib>Bibliothèque</button><span>›</span><button data-home>${esc(bk.short)}</button></div>
  <section class="card" style="margin-top:16px"><div class="label">${esc(m.chapter)} · ${esc(bk.short)} · leçon à créer</div><h1>${esc(m.title)}</h1>
  <p class="muted">Ce chapitre n'a pas encore de leçon. Claude peut la créer maintenant à partir des passages et des figures du livre, lus dans l'index : 6 à 8 sections illustrées, puis 10 questions. Compte une à trois minutes. La leçon est ensuite enregistrée dans l'application et disponible pour tous ses lecteurs.</p>
  <div class="row"><button class="btn primary" id="genBtn">Créer la leçon</button></div><p class="muted" id="genEtape"></p></section>`;
  app.querySelector("[data-lib]").onclick = () => go({ name: "lib" });
  app.querySelector("[data-home]").onclick = () => go({ name: "home", book: m.book });
  const btn = document.getElementById("genBtn"), et = document.getElementById("genEtape");
  if (!window.OUTILS_GEN) { btn.disabled = true; et.textContent = "La création de leçon n'est pas disponible dans cette vue."; return; }
  btn.onclick = async () => {
    btn.disabled = true; btn.textContent = "Création en cours…";
    try { const g = await window.OUTILS_GEN.genererModule(m.src, m.id, (t) => { et.textContent = t + "…"; }); Object.assign(m, g, { stub: false }); toast("Leçon créée."); render(); }
    catch (er) { btn.disabled = false; btn.textContent = "Réessayer"; et.textContent = "Échec : " + ((er && (er.message || er.code)) || "erreur inconnue"); }
  };
}
(function chargerGeneres(k) {
  if (!window.OUTILS_GEN || !window.OUTILS_GEN.pret()) { if (k < 60) setTimeout(() => chargerGeneres(k + 1), 500); return; }
  window.OUTILS_GEN.chargerModulesGeneres().then((lst) => { let n = 0; for (const g of lst) { const m = modById[g.id]; if (m && m.stub) { Object.assign(m, g, { stub: false }); n++; } } if (n) render(); });
})(0);
var DOM_LR = "tous"; try { DOM_LR = localStorage.getItem("rad-dom") || "tous"; } catch (er) {}
var SRC_LR = { cotten: "cotten-t1", laredo: "laredo-t4", cotten2: "cotten-t2", laredo5: "laredo-t5" };
function livreDansDomaine(b) {
  if (!DOM_LR || DOM_LR === "tous") return true;
  const ds = (window.OUTILS && window.OUTILS.livreDomaines((SRC_LR && SRC_LR[b.id]) || b.id)) || [b.domaine];
  return ds.includes(DOM_LR);
}
window.LR.domaine = (d) => { DOM_LR = d; if (view.name === "lib") render(); };
document.getElementById("domGlobal").addEventListener("change", (ev) => { if (window.OUTILS) window.OUTILS.domaine(ev.target.value); });
const _renderLR = render;
render = function () { _renderLR(); try { navLivre(); } catch (er) {} };
function etatModule(m) { if (m.stub) return "Leçon à créer"; if (isDone(m)) return "Validé"; if (!isOpenM(m)) return "Verrouillé"; const p = prog(m).all; return p ? p + " %" : "À commencer"; }
function navLivre() {
  document.querySelectorAll(".navlivre").forEach((x) => x.remove());
  if (!["module", "cards", "quiz"].includes(view.name) || view.daily || view.review) return;
  const m = modOf(view); if (!m) return;
  const L = BOOK[m.book].modules, i = L.indexOf(m), prev = L[i - 1], next = L[i + 1];
  const bar = document.createElement("nav"); bar.className = "navlivre"; bar.setAttribute("aria-label", "Navigation dans le livre");
  bar.innerHTML = `<button data-som="${esc(m.book)}">Sommaire du livre · module ${i + 1} sur ${L.length}</button>`;
  document.getElementById("app").appendChild(bar);
}
function sommaire(bid) {
  const bk = BOOK[bid], cur = modOf(view);
  const el = document.createElement("div"); el.className = "somm"; el.id = "somm";
  el.innerHTML = `<button aria-label="Fermer le sommaire" data-somclose="1" style="border:0;background:none"></button><div role="dialog" aria-label="Sommaire du livre"><div class="label">${esc(bk.author)}</div><h2>${esc(bk.title)}</h2><p class="muted" style="margin:0">${bk.modules.filter(isDone).length} / ${bk.modules.length} modules validés</p>
    <ol>${bk.modules.map((m, k) => `<li><button data-nl="${m.id}" class="${cur === m ? "cur" : ""}" ${isOpenM(m) || m.stub ? "" : "disabled"}><span class="n">${k + 1}</span><span>${esc(m.title)}</span><span class="st ${isDone(m) ? "ok" : ""}">${etatModule(m)}</span></button></li>`).join("")}</ol>
    <div class="row" style="margin-top:14px"><button class="btn" data-somhome="${esc(bid)}">Page du livre</button><button class="btn" data-somclose="1">Fermer</button></div></div>`;
  document.body.appendChild(el);
}
document.addEventListener("click", (ev) => {
  const t = ev.target.closest("[data-nl],[data-som],[data-somclose],[data-somhome]"); if (!t || t.disabled) return;
  const s = document.getElementById("somm");
  if (t.dataset.som) { if (s) s.remove(); else sommaire(t.dataset.som); return; }
  if (s) s.remove();
  if (t.dataset.nl) go({ name: "module", id: t.dataset.nl });
  else if (t.dataset.somhome) go({ name: "home", book: t.dataset.somhome });
});
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") { const s = document.getElementById("somm"); if (s) s.remove(); } });
var ESP_COUR = "apprentissage", ESP_Y = {};
window.ESPACE = function (e) {
  ESP_Y[ESP_COUR] = window.scrollY; const memeEspace = e === ESP_COUR; ESP_COUR = e;
  const outils = e !== "apprentissage";
  document.body.classList.toggle("esp-outils", outils);
  document.getElementById("outils").hidden = !outils;
  window.OUTILS_VISIBLE = outils;
  for (const b of document.querySelectorAll("[data-esp]")) b.setAttribute("aria-current", b.dataset.esp === e ? "page" : "false");
  if (outils && window.OUTILS) window.OUTILS.onglet(e);
  if (!outils) render();
  try { localStorage.setItem("rad-espace", e); } catch (er) {}
  const y = memeEspace ? 0 : (ESP_Y[e] || 0);
  setTimeout(() => window.scrollTo(0, y), 30);
};
document.getElementById("espaces").addEventListener("click", (ev) => { const b = ev.target.closest("[data-esp]"); if (b) window.ESPACE(b.dataset.esp); });
document.addEventListener("click", (ev) => { if (ev.target.closest("[data-vers-cas]")) { window.ESPACE("cas"); if (window.OUTILS) { window.OUTILS.onglet("cas"); } } });
if ("ResizeObserver" in window) new ResizeObserver(() => { const n = document.getElementById("espaces"); document.documentElement.style.setProperty("--esp-h", (getComputedStyle(n).position === "fixed" ? 0 : n.offsetHeight) + "px"); }).observe(document.getElementById("espaces"));
'''
last = L.rindex("</script>")
L = L[:last] + pont + L[last:]
L += "\n<script>\n" + outils_js + '''
(function(){ let e = "apprentissage"; try { e = localStorage.getItem("rad-espace") || e; } catch (er) {} if (e !== "apprentissage") setTimeout(() => window.ESPACE(e), 0); })();
</script>
'''
sortie.write_text(L, encoding="utf-8")
print(f"{sortie} : {len(L) / 1024:.0f} Ko")
