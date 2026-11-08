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
  if (!S.manifest) return `<div class="alert"><b>Aucun corpus dans la base</b><span>${S.metaErr ? "La base n'a pas répondu à temps." : "Le corpus n'a pas encore été importé."} ${S.owner ? `<button class="btn small" data-imp="1">Ouvrir l'import</button>` : ""}</span></div>`;
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
  if (!e) return `<div class="bempty"><h2>Bibliothèque</h2><p>Choisis une entité à gauche pour voir ses passages, ses figures et sa fiche. La recherche accepte les synonymes français et anglais et les sigles.</p>${S.owner ? `<p class="hint">Corpus : ${S.manifest ? `version ${esc(S.manifest.version)} · lectures depuis l'ouverture : ${S.lus.docs} documents, ${(S.lus.octets / 1024).toFixed(0)} Ko` : "non importé"}.</p><button class="btn small" data-imp="1">Importer un livre</button>` : ""}</div>`;
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

/* Import d'un paquet publié (propriétaire) */
S.imp = null;
async function lireFichier(path, type = "json") {
  const r = await avecDelai(fetch(path, { cache: "no-store" }), 60000);
  if (!r.ok) throw { code: "absent", message: path };
  return type === "json" ? r.json() : r.arrayBuffer();
}
async function ouvrirImport() {
  S.tab = "import"; S.detail = true; S.imp = { state: "lecture" }; render();
  try { const m = await lireFichier("import/manifeste.json"); const st = await lireDb("corpus/import").catch(() => null); S.imp = { state: "pret", m, st: st || {} }; }
  catch { S.imp = { state: "vide" }; }
  render();
}
async function deposer(data) {
  const blob = new Blob([JSON.stringify(data)], { type: "application/json" });
  for (let k = 0; k < 4; k++) { try { return (await avecDelai(S.assets.upload(blob), 60000)).id; } catch (e) { if (k === 3 || (e && e.code !== "rate_limited" && e.code !== "timeout")) throw e; await new Promise((r) => setTimeout(r, (e.retryAfterMs || 1500) * (k + 1))); } }
}
async function ecrireDoc(path, data) { for (let k = 0; k < 4; k++) { try { await avecDelai(S.db.doc(path).set(data), 30000); docCache.set(path, Promise.resolve(data)); return; } catch (e) { if (k === 3) throw e; await new Promise((r) => setTimeout(r, 1500 * (k + 1))); } } }
async function enParallele(items, n, fn) { let i = 0; await Promise.all(Array.from({ length: n }, async () => { while (i < items.length) { const it = items[i++]; await fn(it); } })); }
function impLog(t) { S.imp.log = t; render(); }
async function lancerImport() {
  const m = S.imp.m, avant = S.manifest;
  if (!S.assets) { S.imp.err = "Le stockage de fichiers de l'artefact n'est pas disponible dans cette vue."; render(); return; }
  S.imp.state = "import"; S.imp.err = null; render();
  try {
    const etat = (await lireDb("corpus/import").catch(() => null)) || {};
    // 1. livres publiés : passages, figures, images (fichiers assets), carte du livre (db)
    for (const lid of m.publies) {
      const b = m.livres.find((x) => x.id === lid), pk = b.paquet; if (!pk) continue;
      const neuf = !(etat[lid] && etat[lid].v === m.version);
      const carte = (!neuf && (await lireDb("corpus/livre-" + lid).catch(() => null))) || { pb: {}, fm: {}, fx: null, v: m.version };
      const fait = new Set(neuf ? [] : etat[lid].ch || []);
      if (neuf || !etat[lid].p) {
        impLog(`${b.court} : passages`);
        const tous = (await Promise.all(pk.passages.map((f) => lireFichier(`import/${lid}/${f}`)))).flat();
        const blocs = new Map();
        for (const p of tous) { const k = Math.floor((Number(p.id.split(":p")[1]) - 1) / m.bloc); if (!blocs.has(k)) blocs.set(k, []); blocs.get(k).push(p); }
        let n = 0;
        await enParallele([...blocs.entries()], 4, async ([k, p]) => { carte.pb[k] = await deposer({ p }); n++; if (n % 20 === 0) impLog(`${b.court} : passages ${n} / ${blocs.size}`); });
        carte.fx = await deposer(await lireFichier(`import/${lid}/${pk.fx}`));
        await ecrireDoc("corpus/livre-" + lid, carte);
        etat[lid] = { v: m.version, p: true, ch: [] }; await ecrireDoc("corpus/import", etat);
      }
      for (const c of pk.figures) {
        if (fait.has(c.ch)) continue;
        const meta = await lireFichier(`import/${lid}/${c.fichier}`);
        const parts = await Promise.all(meta.parts.map((f) => lireFichier(`import/${lid}/${f}`)));
        let n = 0;
        await enParallele(meta.figs, 4, async (g) => {
          for (const k of ["v", "l"]) {
            const pi = g.pos[k]; if (pi == null) continue;
            const b64 = parts[pi][g.id][k], bin = atob(b64), u8 = new Uint8Array(bin.length);
            for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
            const blob = new Blob([u8], { type: "image/webp" });
            if (!S.imp.sansAssets) {
              try { g[k] = (await S.assets.upload(blob)).id; continue; }
              catch (e) { if (!e || e.code !== "rate_limited") S.imp.sansAssets = true; }
            }
            const path = `im/${g.id.replace(/[^A-Za-z0-9_.-]/g, "_")}-${k}`;
            await ecrireDoc(path, { data: "data:image/webp;base64," + b64 }); g[k + "d"] = path;
          }
          delete g.pos; n++; if (n % 10 === 0) impLog(`${b.court} : chapitre ${c.ch}, images ${n} / ${meta.figs.length}`);
        });
        carte.fm[c.ch] = await deposer({ figs: meta.figs });
        await ecrireDoc("corpus/livre-" + lid, carte);
        etat[lid].ch.push(c.ch); await ecrireDoc("corpus/import", etat);
        impLog(`${b.court} : chapitre ${c.ch} terminé`);
      }
    }
    // 2. index et catalogue, toujours reconstruits sur tout le corpus
    const carte = { ix: [], lx: [], ent: {}, ed: {} };
    for (const cle of ["ix", "lx"]) {
      const seaux = (await Promise.all(m[cle].fichiers.map((f) => lireFichier(`import/${f}`)))).flat();
      let n = 0;
      await enParallele(seaux.map((s, i) => [i, s]), 4, async ([i, s]) => { carte[cle][i] = await deposer(s); n++; if (n % 20 === 0) impLog(`Index ${cle} : ${n} / ${seaux.length}`); });
    }
    impLog("Catalogue d'entités");
    const ent = await lireFichier("import/entites.json");
    await enParallele(Object.entries(ent.listes), 4, async ([k, e]) => { carte.ent[k] = await deposer({ e }); });
    await enParallele(Object.entries(ent.details), 4, async ([k, d]) => { carte.ed[k] = await deposer({ d }); });
    // 3. manifeste en dernier : l'application bascule d'un coup sur la nouvelle version
    const man = JSON.parse(JSON.stringify(m)); for (const b of man.livres) delete b.paquet; delete man.publies;
    man.ix = { n: m.ix.n, N: m.ix.N, avgdl: m.ix.avgdl }; man.lx = { n: m.lx.n, N: m.lx.N, avgdl: m.lx.avgdl };
    man.carte = carte; man.importe = Date.now();
    await ecrireDoc("corpus/manifeste", man);
    // anciens fichiers d'index devenus inutiles
    const vieux = avant && avant.carte ? [...avant.carte.ix, ...avant.carte.lx, ...Object.values(avant.carte.ent), ...Object.values(avant.carte.ed)] : [];
    for (const id of vieux) await S.assets.delete(id).catch(() => {});
    docCache.clear(); S.ent.clear(); S.figById.clear();
    S.imp.state = "fini"; S.imp.log = S.imp.sansAssets ? "Import terminé (stockage d'images plein : les images restantes sont dans la base)." : "Import terminé.";
    await loadCorpusMeta();
  } catch (e) { S.imp.state = "pret"; S.imp.err = (e && (e.message || e.code)) || "erreur"; }
  render();
}
function importDroite() {
  const I = S.imp || {};
  const head = `<button class="btn small bback" data-back="1">‹ Retour</button><span class="label">Corpus</span><h1 class="btitle">Importer des livres</h1>`;
  if (!S.owner) return head + `<p>Réservé au propriétaire.</p>`;
  if (I.state === "lecture") return head + `<p class="hint">Recherche d'un paquet publié…</p>`;
  if (I.state === "vide") return head + `<p>Aucun paquet en attente. Pour ajouter un livre, lance <span class="mono">/ajouter-livre</span> dans Claude Code : il publie le paquet ici, puis tu reviens cliquer sur Importer.</p>`;
  const m = I.m;
  return head + `<p>Paquet version <b>${esc(m.version)}</b>, tour ${esc(m.tour || "unique")} : ${plural(m.publies.length, "livre")} à importer, puis l'index (${m.ix.n + m.lx.n} seaux) et ${plural(Object.values(m.entites.docs).reduce((a, b) => a + b, 0), "liste")} d'entités. L'import reprend où il s'est arrêté si tu fermes la page.</p>
    <ul class="lines">${m.publies.map((id) => { const b = m.livres.find((x) => x.id === id); const st = I.st[id]; const n = st && st.v === m.version ? (st.ch || []).length : 0; return `<li><b>${esc(b.court)}</b> · ${b.passages} passages · ${b.figures} figures · chapitres importés ${n} / ${b.paquet.figures.length}</li>`; }).join("")}</ul>
    ${I.err ? `<div class="alert"><b>Import interrompu</b><span>${esc(String(I.err))}. Relance : il reprendra au dernier chapitre terminé.</span></div>` : ""}
    ${I.state === "import" ? `<p class="hint">${esc(I.log || "Démarrage…")}</p>` : I.state === "fini" ? `<p><b>${esc(I.log)}</b> Tu peux demander à Claude Code de retirer le paquet publié.</p>` : `<button class="btn primary" data-runimp="1">Importer</button>`}`;
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
  const html = S.tab === "import" ? importDroite() : biblioDroite();
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
    const figs = await figsParId(manque).catch(() => []);
    const ajout = Object.fromEntries(figs.filter((g) => g.l || g.v).map((g) => [g.id, g.l || g.v]));
    if (!Object.keys(ajout).length) continue;
    const next = { ...f, imgAssets: { ...(f.imgAssets || {}), ...ajout } };
    try { await S.db.collection("fiches").doc(f.slug).set(JSON.parse(JSON.stringify(next))); S.fiches.set(f.slug, next); } catch {}
  }
  render();
}
