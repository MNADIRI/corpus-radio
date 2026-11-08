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
css += "\n.tabs{display:none!important}\n.top{top:var(--esp-h,0px)!important}\n"
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
js = rep(js, 'history.replaceState(null, "", d.tab === "biblio" ? "#bibliotheque" : location.pathname + location.search); ', '')
js += '''
window.OUTILS = { onglet(t) { S.tab = t; S.detail = false; $("desk").classList.toggle("cas", t === "cas");
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
L = rep(L, '<header class="top">', '''<nav class="espaces" id="espaces" aria-label="Espaces">
  <span class="esp-brand">Radiologie</span><button data-esp="apprentissage" aria-current="page">Apprentissage</button><button data-esp="notes">Notes</button><button data-esp="cas">Cas</button><button data-esp="biblio">Bibliothèque</button>
</nav>
<header class="top">''')
L = rep(L, '<main class="wrap" id="app"></main>', '<main class="wrap" id="app"></main>\n<div id="outils" hidden></div>')
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
.espaces{position:sticky;top:env(safe-area-inset-top,0px);z-index:12;display:flex;gap:2px;justify-content:center;flex-wrap:wrap;padding:6px max(16px,env(safe-area-inset-right,0px)) 6px max(16px,env(safe-area-inset-left,0px));background:var(--surface);border-bottom:1px solid var(--line)}
.esp-brand{font-family:var(--display,Georgia,serif);font-weight:650;font-size:16px;margin-right:auto;align-self:center;color:var(--fg)}
.espaces{justify-content:flex-start!important;align-items:center}
@media (max-width:560px){.esp-brand{display:none}.espaces{justify-content:center!important}}
.espaces button{border:0;background:none;color:var(--muted);font:500 14px var(--body,system-ui);padding:7px 14px;border-radius:999px;cursor:pointer}
.espaces button[aria-current="page"]{background:var(--accent-soft,rgba(35,80,168,.12));color:var(--accent);font-weight:600}
.espaces button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
body.esp-outils header.top,body.esp-outils #app,body.esp-outils #fab{display:none!important}
header.top{top:var(--esp-h,0px)}
.domh{font-family:var(--display,Georgia,serif);font-size:20px;margin:18px 0 6px;grid-column:1/-1}
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
if ("ResizeObserver" in window) new ResizeObserver(() => document.documentElement.style.setProperty("--esp-h", document.getElementById("espaces").offsetHeight + "px")).observe(document.getElementById("espaces"));
'''
last = L.rindex("</script>")
L = L[:last] + pont + L[last:]
L += "\n<script>\n" + outils_js + '''
(function(){ let e = "apprentissage"; try { e = localStorage.getItem("rad-espace") || e; } catch (er) {} if (e !== "apprentissage") setTimeout(() => window.ESPACE(e), 0); })();
</script>
'''
sortie.write_text(L, encoding="utf-8")
print(f"{sortie} : {len(L) / 1024:.0f} Ko")
