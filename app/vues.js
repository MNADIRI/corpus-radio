/* ================= onglets, domaine, Bibliothèque, import ================= */
S.tab = "notes"; S.bq = ""; S.entSel = null; S.entView = null; S.prog = undefined;
const CAT = { tumeur: "Tumeur", infection: "Infection", inflammatoire: "Inflammatoire", traumatique: "Traumatique", degeneratif: "Dégénératif", congenital: "Congénital", vasculaire: "Vasculaire", metabolique: "Métabolique", autre: "Autre" };
function libDomaine(id) { return id === "tous" ? "Tous les domaines" : ((S.manifest?.domaines || []).find((d) => d.id === id) || {}).libelle || id; }
function libRegion(id) { return ((S.manifest?.regions || []).find((r) => r.id === id) || {}).libelle || id; }
function domainesDisponibles() {
  const n = new Map();
  for (const b of S.books) for (const c of b.chapitres) for (const d of c.d) n.set(d, (n.get(d) || 0) + 1);
  return [...n.entries()].sort((a, b) => b[1] - a[1]).map(([id, k]) => ({ id, lib: libDomaine(id), n: k }));
}
function majDomaines() {
  const ds = S.manifest ? domainesDisponibles() : [];
  if (S.dom !== "tous" && S.manifest && !ds.some((d) => d.id === S.dom)) S.dom = "tous";
  const opts = `<option value="tous">Tous les domaines</option>` + ds.map((d) => `<option value="${esc(d.id)}">${esc(d.lib)} · ${d.n} chap.</option>`).join("");
  for (const sel of [$("domSel"), document.getElementById("domGlobal")]) {
    if (!sel) continue;
    if (sel.dataset.sig !== opts) { sel.dataset.sig = opts; sel.innerHTML = opts; }
    sel.value = S.dom; sel.disabled = !S.manifest;
  }
}
function changerDomaine(d) {
  if (d === S.dom) return;
  S.dom = d; try { localStorage.setItem("rad-dom", d); } catch {}
  S.entView = null; S.entSel = null; S.bib.livre = null; S.bib.ch = null; S.detail = false;
  if (S.manifest) chargerEntites();
  S.rev.construit = false;
  const mode = S.cas.mode; S.cas = { mode, etat: "vide" };
  if (S.tab === "cas" && mode === "alea") tirerCas();
  remplirReserve();
  if (window.LR) window.LR.domaine(d);
  render();
}
function majOnglets() {
  for (const b of document.querySelectorAll("[data-tab]")) b.setAttribute("aria-current", b.dataset.tab === S.tab ? "page" : "false");
  $("q").placeholder = S.tab === "biblio" ? "Chercher une entité, un synonyme, un sigle…" : "Chercher dans les fiches et les notes…";
}

/* Progression de Learning Radiology */
async function chargerProgression() {
  if (!S.uid) { S.prog = null; return; }
  try { const d = await S.db.doc(`data/users/${S.uid}/progress`).get(); S.prog = d.exists ? d.data() : null; } catch { S.prog = null; }
  render();
}
function resumeProgression(p) {
  try { const s = JSON.parse(p.json); return `${Object.keys(s.quiz || {}).length} quiz répondus, ${Object.keys(s.read || {}).length} sections lues, ${Object.keys(s.cards || {}).length} cartes suivies${s.pseudo ? `, pseudo « ${s.pseudo} »` : ""}`; } catch { return "format illisible"; }
}
function progressionHtml() {
  if (!S.uid) return "";
  if (S.prog) return `<div class="note-ok"><span class="label">Progression Learning Radiology</span><span>Conservée : ${esc(resumeProgression(S.prog))}. Elle sera reprise dans Apprendre et Réviser.</span></div>`;
  return `<details class="imp-prog"><summary>Reprendre ma progression de Learning Radiology</summary><p class="hint">Colle ici le code copié depuis Learning Radiology.</p><textarea id="progCode" rows="3"></textarea><button class="btn small" data-progimp="1">Importer</button></details>`;
}
async function importerProgression() {
  const v = ($("progCode")?.value || "").trim(); if (!v) return;
  let s; try { s = JSON.parse(v.startsWith("{") ? v : decodeURIComponent(escape(atob(v)))); } catch { toast("Ce code n'est pas lisible : recopie-le en entier."); return; }
  if (!s || s.v !== 1) { toast("Ce code ne vient pas de Learning Radiology."); return; }
  const doc = { json: JSON.stringify(s), at: Date.now(), source: "learning-radiology" };
  try { await S.db.doc(`data/users/${S.uid}/progress`).set(doc); S.prog = doc; toast("Progression importée."); render(); } catch { toast("Enregistrement impossible : réessaie."); }
}

/* rendu des onglets */
let biblioSig = "";
function renderBiblio() {
  const sig = JSON.stringify([S.tab, S.dom, S.bq, S.entSel, S.entState, S.ent.size, !!S.manifest, S.owner, S.bib]);
  if (S.tab === "cas") {
    const g = casGauche(); if ($("left").dataset.h !== g) { $("left").dataset.h = g; $("left").innerHTML = g; } biblioSig = "";
    const h = casDroite(); if ($("right").dataset.h !== h) { const keep = $("right").querySelector("#casRep")?.value; $("right").dataset.h = h; $("right").innerHTML = h; const ta = $("right").querySelector("#casRep"); if (ta && keep != null && !ta.value) ta.value = keep; chargerImagesVisibles(); }
    return;
  }
  $("left").dataset.h = "";
  if (sig !== biblioSig) { biblioSig = sig; $("left").innerHTML = biblioGauche(); }
  const html = biblioDroite();
  if ($("right").dataset.h !== html) { $("right").dataset.h = html; $("right").innerHTML = html; chargerImagesVisibles(); }
}
async function chargerImagesVisibles() {
  for (const img of $("right").querySelectorAll("img[data-lrimg]")) { if (img.src || !window.LR) continue; window.LR.image(img.dataset.lrimg).then((s) => { if (s) img.src = s; }).catch(() => {}); }
  for (const img of $("right").querySelectorAll("img[data-img]")) {
    if (img.src) continue;
    figImage(img.dataset.img, img.dataset.slug || null, !!img.dataset.full).then((src) => { if (src) img.src = src; }).catch(() => {});
  }
}

/* Fiches reprises de Notes radiologiques : rattacher leurs images aux fichiers du corpus importé,
   pour que les personnes avec qui l'application est partagée les voient. */
async function reparerImagesFiches() {
  if (!S.owner || !S.manifest || reparerImagesFiches.fait) return;
  reparerImagesFiches.fait = true;
  for (const f of [...S.fiches.values()]) {
    if (f.kind !== "corpus" || !f.fiche || !f.refs) continue;
    const ids = [...new Set((f.fiche.images || []).map((im) => f.refs[im.ref]?.id).filter(Boolean))];
    const manque = ids.filter((id) => !(f.imgAssets || {})[id]); if (!manque.length) continue;
    if (!S.assets) return;
    const ajout = {};
    for (const fid of manque) {
      try { const src = await figImage(fid, null, true); if (src) ajout[fid] = (await S.assets.upload(await blobDe(src))).id; } catch {}
    }
    if (!Object.keys(ajout).length) continue;
    const next = { ...f, imgAssets: { ...(f.imgAssets || {}), ...ajout } };
    try { await S.db.collection("fiches").doc(f.slug).set(JSON.parse(JSON.stringify(next))); S.fiches.set(f.slug, next); } catch {}
  }
  render();
}

function messageCorpus() {
  return { mcp: "Les connecteurs ne sont pas disponibles dans cette vue.", server_not_connected: "Le connecteur GitHub n'est pas connecté sur ce compte claude.ai.",
    server_not_found: "Aucun connecteur nommé « GitHub » sur ce compte claude.ai.", not_granted: "L'accès au connecteur GitHub a été refusé pour cette page.",
    needs_reauth: "Le connecteur GitHub demande une nouvelle connexion dans claude.ai.", tool_error: "GitHub n'a pas trouvé le dépôt corpus-radio : vérifie l'accès du connecteur aux dépôts privés.",
    timeout: "GitHub n'a pas répondu en 15 s." }[S.metaErr] || "Le corpus n'a pas pu être lu dans le dépôt GitHub.";
}
