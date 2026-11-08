#!/usr/bin/env python3
"""Assemble app/radiologie.html à partir de la page « Notes radiologiques » (fonctionnement des fiches
conservé tel quel) en remplaçant la couche de données et en ajoutant onglets, domaine, Bibliothèque,
import et reprise de progression. Chaque remplacement doit s'appliquer exactement une fois."""
import re
import sys
from pathlib import Path

ICI = Path(__file__).parent
src = Path(sys.argv[1]).read_text(encoding="utf-8")


def rep(old, new, count=1):
    global src
    n = src.count(old)
    if n != count:
        sys.exit(f"Remplacement introuvable ({n}×) : {old[:90]!r}")
    src = src.replace(old, new)


# 1. squelette de publication retiré
src = src[src.index("<title>"):]
src = re.sub(r"</body></html>\s*$", "", src)

# 2. nom
rep("<title>Notes radiologiques</title>", "<title>Radiologie</title>")
rep('<b>Notes radiologiques</b>', '<b>Radiologie</b>')

# 3. en-tête : onglets et domaine
rep('<div class="searchwrap">', '''<nav class="tabs" aria-label="Espaces"><button data-tab="notes" aria-current="page">Notes</button><button data-tab="biblio">Bibliothèque</button></nav>
  <label class="domwrap"><span class="sr">Domaine</span><select id="domSel" aria-label="Domaine"><option value="tous">Tous les domaines</option></select></label>
  <div class="searchwrap">''')

# 4. couche de données
a = src.index("/* ================= corpus (owner-only store) ================= */")
b = src.index("/* ================= fiche model ================= */")
src = src[:a] + (ICI / "couche_donnees.js").read_text(encoding="utf-8") + "\n" + src[b:]

# 5. génération de fiche : recherche asynchrone dans le magasin
rep('''      const ps = searchTexts(terms, 3).filter((h) => h.score > 2).map((h) => h.p);
      for (const f of mergeFigs(searchFigures(terms, 8), figsCitedIn(ps, 8)).slice(0, 12)) {''',
    '''      const ps = (await searchTexts(terms, 3)).filter((h) => h.score > 2).map((h) => h.p);
      for (const f of mergeFigs(await searchFigures(terms, 8), await figsCitedIn(ps, 8)).slice(0, 12)) {''')
rep('''    if (S.owner) loadTexts().catch(() => {});\n''', "")
rep('''    step(job, 1, "on", S.idx ? "Recherche dans les livres" : "Chargement des livres (une seule fois)");
    await loadTexts();
    const hits = searchTexts(id.termes.concat(id.question ? [id.question] : []), 9).filter((h) => h.score > 2);''',
    '''    step(job, 1, "on", "Recherche dans les livres");
    const hits = (await searchTexts(id.termes.concat(id.question ? [id.question] : []), 9)).filter((h) => h.score > 2);''')
rep('''const figs = mergeFigs(figsCitedIn(hits.map((h) => h.p), 30), searchFigures(id.termes, 24)).slice(0, 45);''',
    '''const figs = mergeFigs(await figsCitedIn(hits.map((h) => h.p), 30), await searchFigures(id.termes, 24)).slice(0, 45);''')

# 6. images des fiches : les figures sont déjà dans assets, on réutilise leur identifiant
rep('''        const data = await figImage(fid); if (!data) continue;
        try { out[fid] = (await S.assets.upload(dataUrlBlob(data))).id; }''',
    '''        const data = await figImage(fid, null, true); if (!data) continue;
        if (data.startsWith("/_blob/")) { out[fid] = data.slice(7); done++; continue; }
        try { out[fid] = (await S.assets.upload(await blobDe(data))).id; }''')

# 7. références et accueil
rep('return S.owner && !m.fig && S.idx ?', 'return S.owner && !m.fig && S.manifest ?')
rep('S.figIndex.length.toLocaleString', 'S.books.reduce((a, b) => a + (b.figures || 0), 0).toLocaleString')
rep('!!S.manifest, S.figIndex.length, !!S.sample]); if (sig !== rightSig) html = homeHtml();',
    '!!S.manifest, S.books.length, !!S.sample, !!S.prog]); if (sig !== rightSig) html = progressionHtml() + homeHtml();')

# 8. passage complet lu à la demande
rep('''function showPassage(id) {
  const p = S.texts && S.texts.find((x) => x.id === id); if (!p) return;''',
    '''async function showPassage(id) {
  const p = await lirePassage(id).catch(() => null); if (!p) { toast("Passage introuvable dans la base."); return; }''')

# 9. visionneuse : pleine résolution
rep('src = await figImage(it.id, it.slug || null).catch(() => null);', 'src = await figImage(it.id, it.slug || null, true).catch(() => null);')
rep('`<span class="lbtag">${esc(S.fiches.get(it.slug)?.entite || "Entité de la fiche")}</span>`',
    '`<span class="lbtag">${esc(S.fiches.get(it.slug)?.entite || it.ent || "Entité de la fiche")}</span>`')

# 10. rendu : onglets
rep('''function renderHeader() {''', '''function renderHeader() {
  majDomaines(); majOnglets();''')
rep('''  renderHeader();
  $("desk").classList.toggle("detail", S.detail);''', '''  renderHeader();
  $("desk").classList.toggle("detail", S.detail);
  if (S.tab !== "notes") { leftSig = ""; rightSig = ""; renderBiblio(); return; }
  biblioSig = ""; $("right").dataset.h = "";''')

# 11. recherche selon l'onglet
rep('''$("q").oninput = () => { S.query = $("q").value;''', '''$("q").oninput = () => { if (S.tab === "biblio") { S.bq = $("q").value; render(); return; } S.query = $("q").value;''')

# 12. démarrage : droits, progression, route
rep('''  if (user) { try { S.owner = !!(await user.isOwner()); } catch {} try { S.uid = await user.id(); } catch {} }''',
    '''  if (user) { try { S.owner = !!(await user.isOwner()) || !!(await user.canEdit()); } catch {} try { S.uid = await user.id(); } catch {} }''')
rep('''  loadCorpusMeta();
})();''', '''  loadCorpusMeta().then(() => setTimeout(reparerImagesFiches, 3000));
  chargerProgression();
})();''')

# 13. nouveaux éléments et événements, styles
css = (ICI / "styles.css").read_text(encoding="utf-8")
rep("</style>\n\n<header", css + "\n</style>\n\n<header")
vues = (ICI / "vues.js").read_text(encoding="utf-8")
evts = '''
document.addEventListener("click", (e) => {
  const t = e.target.closest("[data-tab],[data-ent],[data-progimp],[data-genent],[data-retry-ent],[data-retry-meta],[data-fiche]");
  if (!t) return;
  const d = t.dataset;
  if (d.tab) { S.tab = d.tab; S.detail = false; $("q").value = d.tab === "biblio" ? S.bq : S.query; if (d.tab === "biblio" && S.entState === "idle") chargerEntites(); history.replaceState(null, "", d.tab === "biblio" ? "#bibliotheque" : location.pathname + location.search); render(); }
  else if (d.ent) ouvrirEntite(d.ent);
  else if (d.retryMeta) { S.manifest = undefined; render(); loadCorpusMeta(); }
  else if (d.progimp) importerProgression();
  else if (d.retryEnt) { S.entState = "idle"; chargerEntites(); }
  else if (d.genent) {
    const en = S.ent.get(d.genent); if (!en) return;
    const id = "n" + Date.now().toString(36), note = { kind: "note", text: en.n, at: Date.now(), status: "run" };
    S.tab = "notes"; S.notes.unshift({ id, ...note }); openView({ type: "note", id });
    if (S.uid) notesCol().doc(id).set(note).catch(() => {});
    runNote(id);
  } else if (d.fiche) { S.tab = "notes"; }
});
$("domSel").onchange = () => { S.dom = $("domSel").value; try { localStorage.setItem("rad-dom", S.dom); } catch {} S.entView = null; S.entSel = null; chargerEntites(); render(); };
if (location.hash === "#bibliotheque") S.tab = "biblio";
'''
rep("/* ================= boot ================= */", vues + evts + "\n/* ================= boot ================= */")

Path(sys.argv[2]).write_text(src, encoding="utf-8")
print(f"{sys.argv[2]} : {len(src) / 1024:.0f} Ko")
