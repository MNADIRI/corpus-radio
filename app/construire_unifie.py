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
.domwrap select{max-width:none!important}
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
window.OUTILS = { onglet(t) { S.tab = t; HOTE.classList.toggle("hors-notes", t !== "notes"); S.detail = false; $("desk").classList.toggle("cas", t === "cas");
  if (t === "biblio" && S.entState === "idle") chargerEntites();
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
L = rep(L, '<header class="top">', f'''<nav class="espaces" id="espaces" aria-label="Espaces"><div class="esp-in"><span class="esp-brand">Radiologie</span><div class="esp-tabs">{boutons}</div></div></nav>
<header class="top">''')
L = rep(L, '<main class="wrap" id="app"></main>', '<main class="wrap" id="app"></main>\n<div id="outils" hidden></div>')
ds = L.index("<script>")
tete, script = L[:ds], L[ds:]
script = script.replace('"Bibliothèque MSK"', '"Apprentissage"').replace("<h1>Bibliothèque</h1>", "<h1>Apprentissage</h1>").replace("Retour à la bibliothèque", "Retour aux ouvrages").replace(">Bibliothèque<", ">Ouvrages<").replace('"Bibliothèque"', '"Ouvrages"')
tete = tete.replace(">Bibliothèque MSK<", ">Apprentissage<").replace(">Bibliothèque<", ">Ouvrages<")
L = tete + script
L = L.replace('<button data-esp="biblio">' + ICO["biblio"] + '<span>Ouvrages</span>', '<button data-esp="biblio">' + ICO["biblio"] + '<span>Bibliothèque</span>')
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
.esp-tabs{display:flex;gap:2px;background:var(--sunk);border:1px solid var(--line);border-radius:999px;padding:3px}
.espaces button{display:inline-flex;align-items:center;gap:6px;border:0;background:none;color:var(--muted);font:500 13.5px var(--body,system-ui);padding:6px 14px;border-radius:999px;cursor:pointer}
.espaces button svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}
.espaces button:hover{color:var(--fg)}
.espaces button[aria-current="page"]{background:var(--surface);color:var(--fg);box-shadow:0 1px 2px rgba(0,0,0,.12)}
.espaces button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
body.esp-outils header.top,body.esp-outils #app,body.esp-outils #fab{display:none!important}
header.top{top:var(--esp-h,0px)}
.domh{font-family:var(--display,Georgia,serif);font-size:20px;margin:22px 0 8px;grid-column:1/-1}
@media (max-width:720px){
  .espaces{position:fixed;top:auto;bottom:0;left:0;right:0;margin:0;padding:4px 6px calc(4px + env(safe-area-inset-bottom,0px));border-top:1px solid var(--line);border-bottom:0;background:var(--surface)}
  .esp-brand{display:none}.esp-tabs{flex:1;background:none;border:0;padding:0;justify-content:space-around}
  .espaces button{flex:1;flex-direction:column;gap:2px;font-size:11px;padding:6px 2px;border-radius:10px}
  .espaces button svg{width:21px;height:21px}
  .espaces button[aria-current="page"]{background:var(--accent-soft);color:var(--accent);box-shadow:none}
  body{padding-bottom:calc(76px + env(safe-area-inset-bottom,0px))!important}
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
window.LR = { etat: () => S, sauver: save, aller: go, startReview, startRapid, rqTodo, rqAll, dueMissed, dueCards, modById, BOOKS, ALL };
function libDomaineLR(d) { return ({ msk: "Musculosquelettique", neuro: "Neuroradiologie", "tete-cou": "Tête et cou", thorax: "Thorax", "cardio-vasc": "Cardiovasculaire", "abdo-digestif": "Abdomen et digestif", "uro-genital": "Urogénital", sein: "Sein", pediatrie: "Pédiatrie", interventionnel: "Radiologie interventionnelle" })[d] || d; }
function parDomaine(books, carte) {
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
window.ESPACE = function (e) {
  const outils = e !== "apprentissage";
  document.body.classList.toggle("esp-outils", outils);
  document.getElementById("outils").hidden = !outils;
  window.OUTILS_VISIBLE = outils;
  for (const b of document.querySelectorAll("[data-esp]")) b.setAttribute("aria-current", b.dataset.esp === e ? "page" : "false");
  if (outils && window.OUTILS) window.OUTILS.onglet(e);
  if (!outils) render();
  try { localStorage.setItem("rad-espace", e); } catch (er) {}
  window.scrollTo(0, 0);
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
