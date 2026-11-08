/* ================= onglets, domaine, Bibliothèque, import ================= */
S.tab = "notes"; S.bq = ""; S.entSel = null; S.entView = null; S.prog = undefined;
const CAT = { tumeur: "Tumeur", infection: "Infection", inflammatoire: "Inflammatoire", traumatique: "Traumatique", degeneratif: "Dégénératif", congenital: "Congénital", vasculaire: "Vasculaire", metabolique: "Métabolique", autre: "Autre" };
function libDomaine(id) { return id === "tous" ? "Tous les domaines" : ((S.manifest?.domaines || []).find((d) => d.id === id) || {}).libelle || id; }
function libRegion(id) { return ((S.manifest?.regions || []).find((r) => r.id === id) || {}).libelle || id; }
function majDomaines() {
  const sel = $("domSel"); if (!sel) return;
  const ids = S.manifest ? ["tous", ...Object.keys(S.manifest.entites?.docs || {}).sort((a, b) => libDomaine(a).localeCompare(libDomaine(b), "fr"))] : ["tous"];
  const sig = ids.join();
  if (sel.dataset.sig !== sig) { sel.dataset.sig = sig; sel.innerHTML = ids.map((d) => `<option value="${esc(d)}">${esc(libDomaine(d))}</option>`).join(""); }
  sel.value = ids.includes(S.dom) ? S.dom : "tous";
  sel.disabled = !S.manifest;
}
function majOnglets() {
  for (const b of document.querySelectorAll("[data-tab]")) b.setAttribute("aria-current", b.dataset.tab === S.tab ? "page" : "false");
  $("q").placeholder = S.tab === "biblio" ? "Chercher une entité, un synonyme, un sigle…" : "Chercher dans les fiches et les notes…";
}

/* Bibliothèque : colonne de gauche */
function entitesFiltrees() {
  const q = norm(S.bq).trim();
  let l = entitesVisibles();
  if (q) l = l.filter((e) => norm(e.n).includes(q) || e.s.some((s) => norm(s).includes(q)) || e.a.some((a) => norm(a) === q));
  return l.sort((a, b) => (q && norm(a.n).startsWith(q) ? 0 : 1) - (q && norm(b.n).startsWith(q) ? 0 : 1) || a.n.localeCompare(b.n, "fr"));
}
function biblioGauche() {
  if (!S.owner) return `<div class="alert"><b>Corpus réservé</b><span>La bibliothèque des livres est réservée au propriétaire. Les fiches et les modules restent consultables dans l'onglet Notes.</span></div>`;
  if (S.manifest === undefined) return `<p class="hint">Connexion à la base…</p>`;
  if (!S.manifest) return `<div class="alert"><b>Livres indisponibles</b><span>${esc(messageCorpus())} <button class="btn small" data-retry-meta="1">Réessayer</button></span></div>`;
  const livres = S.books.filter((b) => S.dom === "tous" || b.domaines.includes(S.dom));
  const l = entitesFiltrees(), vis = l.slice(0, 300);
  return `<div class="libhead"><span class="label">${esc(libDomaine(S.dom))}</span><span class="hint">${plural(livres.length, "livre")} · ${plural(l.length, "entité")}</span></div>
  <div class="booklist">${livres.map((b) => `<div class="bookrow"><b>${esc(b.court)}</b><span>${esc(b.titre)}</span><span class="mono">${b.passages.toLocaleString("fr-BE")} passages · ${b.figures.toLocaleString("fr-BE")} figures · ${b.langue.toUpperCase()}</span></div>`).join("")}</div>
  ${S.entState === "loading" ? `<p class="hint">Chargement du catalogue…</p>` : S.entState === "error" ? `<div class="alert"><b>Catalogue indisponible</b><span>La base n'a pas répondu. <button class="btn small" data-retry-ent="1">Réessayer</button></span></div>` : ""}
  <ul class="entlist">${vis.map((e) => `<li><button class="item${S.entSel === e.i ? " on" : ""}" data-ent="${esc(e.i)}"><b>${esc(e.n)}</b><span>${esc(CAT[e.c] || e.c)}${e.r.length ? " · " + esc(e.r.slice(0, 2).map(libRegion).join(", ")) : ""} · ${e.np} p · ${e.nf} fig.</span></button></li>`).join("")}</ul>
  ${l.length > vis.length ? `<p class="hint">${l.length - vis.length} autres : affine la recherche.</p>` : ""}`;
}

/* Bibliothèque : fiche d'entité à droite */
async function ouvrirEntite(id) {
  S.entSel = id; S.entView = { id, state: "loading" }; S.detail = true; render();
  try {
    const d = await detailEntite(id);
    const pids = (d?.p || []).slice(0, 14), fids = (d?.f || []).slice(0, 24);
    const [ps, figs] = await Promise.all([Promise.all(pids.map((p) => lirePassage(p).catch(() => null))), figsParId(fids)]);
    if (S.entSel !== id) return;
    S.entView = { id, state: "ok", d, ps: ps.filter(Boolean), figs, totP: (d?.p || []).length, totF: (d?.f || []).length };
  } catch { S.entView = { id, state: "err" }; }
  render();
}
function ficheDeEntite(e) {
  const slugs = new Set([slugify(e.n), ...e.s.map(slugify)]);
  return [...S.fiches.values()].find((f) => slugs.has(f.slug) || (f.alias || []).some((a) => slugs.has(a)));
}
function biblioDroite() {
  const v = S.entView, e = v && S.ent.get(v.id);
  if (!e) return `<div class="bempty"><h2>Bibliothèque</h2><p>Choisis une entité à gauche pour voir ses passages, ses figures et sa fiche. La recherche accepte les synonymes français et anglais et les sigles.</p>${S.owner && S.manifest ? `<p class="hint">Corpus version ${esc(S.manifest.version)} · lu depuis l'ouverture : ${S.lus.docs} morceaux, ${(S.lus.octets / 1024).toFixed(0)} Ko.</p>` : ""}</div>`;
  const f = ficheDeEntite(e);
  const head = `<button class="btn small bback" data-back="1">‹ Liste</button><span class="label">${esc(CAT[e.c] || e.c)}${e.d.length ? " · " + esc(e.d.map(libDomaine).join(", ")) : ""}</span><h1 class="btitle">${esc(e.n)}</h1>
    ${e.s.length || e.a.length ? `<p class="hint">Aussi : ${esc([...e.a, ...e.s].slice(0, 12).join(" · "))}</p>` : ""}
    ${e.r.length ? `<p class="hint">Régions : ${esc(e.r.map(libRegion).join(", "))}</p>` : ""}
    <div class="row">${f ? `<button class="btn primary small" data-fiche="${esc(f.slug)}">Ouvrir la fiche</button>` : S.sample ? `<button class="btn primary small" data-genent="${esc(e.i)}">Générer la fiche</button>` : ""}</div>`;
  if (v.state === "loading") return head + `<p class="hint">Lecture des passages et des figures…</p>`;
  if (v.state === "err") return head + `<div class="alert"><b>Lecture impossible</b><span>La base n'a pas répondu à temps. <button class="btn small" data-ent="${esc(e.i)}">Réessayer</button></span></div>`;
  S.lb = { list: v.figs.map((g) => ({ id: g.id, cap: g.cap, src: `${bookShort(g.b)}, fig. ${g.fig}${g.pa ? g.pa : ""}${g.pg ? `, p. ${g.pg}` : ""}`, dd: "" , slug: null, ent: e.n })), i: 0 };
  return head + `
    <h2 class="bsech">Figures <span class="hint">${v.totF > v.figs.length ? `${v.figs.length} sur ${v.totF}` : v.figs.length}</span></h2>
    ${v.figs.length ? `<div class="bthumbs">${v.figs.map((g, i) => `<button class="bthumb" data-lb="${i}" title="${esc(g.cap.slice(0, 140))}"><img data-img="${esc(g.id)}" alt="${esc(g.cap.slice(0, 120))}"><span>${esc(bookShort(g.b))} · fig. ${esc(g.fig)}${esc(g.pa || "")}</span></button>`).join("")}</div>` : `<p class="hint">Aucune figure rattachée.</p>`}
    <h2 class="bsech">Passages <span class="hint">${v.totP > v.ps.length ? `${v.ps.length} sur ${v.totP}` : v.ps.length}</span></h2>
    ${v.ps.map((p) => `<article class="psg"><span class="mono">${esc(srcLabel(p))}</span><p>${esc(p.t.length > 900 ? p.t.slice(0, 900) + " …" : p.t)}</p><button class="btn small" data-ref="${esc(p.id)}">Lire en entier</button></article>`).join("") || `<p class="hint">Aucun passage rattaché.</p>`}`;
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
  const sig = JSON.stringify([S.tab, S.dom, S.bq, S.entSel, S.entState, S.ent.size, !!S.manifest, S.owner]);
  if (sig !== biblioSig) { biblioSig = sig; $("left").innerHTML = biblioGauche(); }
  const html = biblioDroite();
  if ($("right").dataset.h !== html) { $("right").dataset.h = html; $("right").innerHTML = html; chargerImagesVisibles(); }
}
async function chargerImagesVisibles() {
  for (const img of $("right").querySelectorAll("img[data-img]")) {
    if (img.src) continue;
    figImage(img.dataset.img, img.dataset.slug || null).then((src) => { if (src) img.src = src; }).catch(() => {});
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
