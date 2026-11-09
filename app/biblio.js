/* Bibliothèque : ce à quoi l'application a accès dans l'index (ouvrages, chapitres, entités) */
S.bib = { vue: "ouvrages", cat: "", reg: "", livre: null, ch: null };
function entitesFiltrees() {
  const q = norm(S.bq).trim();
  let l = entitesVisibles();
  if (S.bib.cat) l = l.filter((e) => e.c === S.bib.cat);
  if (S.bib.reg) l = l.filter((e) => e.r.includes(S.bib.reg));
  if (q) l = l.filter((e) => norm(e.n).includes(q) || e.s.some((s) => norm(s).includes(q)) || e.a.some((a) => norm(a) === q));
  return l.sort((a, b) => (q && norm(a.n).startsWith(q) ? 0 : 1) - (q && norm(b.n).startsWith(q) ? 0 : 1) || (b.np + b.nf) - (a.np + a.nf) || a.n.localeCompare(b.n, "fr"));
}
function livresVisibles() { return S.books.filter((b) => S.dom === "tous" || b.domaines.includes(S.dom)); }
function biblioGauche() {
  if (!S.owner) return `<div class="alert"><b>Index réservé</b><span>La bibliothèque lit l'index dans le dépôt GitHub corpus-radio. Ajoute le connecteur GitHub dans claude.ai pour y accéder.</span></div>`;
  if (S.manifest === undefined) return `<p class="hint">Lecture du sommaire de l'index…</p>`;
  if (!S.manifest) return `<div class="alert"><b>Index indisponible</b><span>${esc(messageCorpus())} <button class="btn small" data-retry-meta="1">Réessayer</button></span></div>`;
  const lv = livresVisibles(), tot = lv.reduce((a, b) => [a[0] + b.passages, a[1] + b.figures], [0, 0]);
  const seg = `<div class="seg" role="tablist"><button role="tab" aria-selected="${S.bib.vue === "ouvrages"}" data-bvue="ouvrages">Ouvrages</button><button role="tab" aria-selected="${S.bib.vue === "entites"}" data-bvue="entites">Entités</button></div>`;
  const stats = `<div class="bstats"><span><b>${lv.length}</b> ouvrages</span><span><b>${tot[0].toLocaleString("fr-BE")}</b> passages</span><span><b>${tot[1].toLocaleString("fr-BE")}</b> figures</span><span><b>${entitesVisibles().length.toLocaleString("fr-BE")}</b> entités</span></div>`;
  if (S.bib.vue === "ouvrages" && S.bib.livre && S.bookById.get(S.bib.livre)) return tocLivreGauche(S.bookById.get(S.bib.livre));
  if (S.bib.vue === "ouvrages") {
    const g = {}; for (const b of lv) (g[b.domaine] = g[b.domaine] || []).push(b);
    return seg + stats + Object.entries(g).map(([d, bs]) => `<h3 class="grp">${esc(libDomaine(d))}</h3><ul class="entlist">${bs.map((b) => `<li><button class="item${S.bib.livre === b.id ? " on" : ""}" data-livre="${esc(b.id)}"><b>${esc(b.court)}</b><span>${esc(b.titre)}</span><span class="mono">${b.chapitres.length} chapitres · ${b.passages.toLocaleString("fr-BE")} passages · ${b.figures.toLocaleString("fr-BE")} figures${b.id === "top3-msk" ? " · banque de cas" : ""}</span></button></li>`).join("")}</ul>`).join("");
  }
  const cats = Object.keys(CAT), regs = [...new Set(entitesVisibles().flatMap((e) => e.r))].sort((a, b) => libRegion(a).localeCompare(libRegion(b), "fr"));
  const l = entitesFiltrees(), vis = l.slice(0, 250);
  return seg + stats + `<div class="filtres">
    <div class="chips">${["", ...cats].map((c) => `<button class="chip${S.bib.cat === c ? " on" : ""}" data-bcat="${c}">${c ? esc(CAT[c]) : "Toutes"}</button>`).join("")}</div>
    <label class="sr" for="bReg">Région</label><select id="bReg"><option value="">Toutes les régions</option>${regs.map((r) => `<option value="${esc(r)}" ${S.bib.reg === r ? "selected" : ""}>${esc(libRegion(r))}</option>`).join("")}</select></div>
  ${S.entState === "loading" ? `<p class="hint">Chargement du catalogue…</p>` : S.entState === "error" ? `<div class="alert"><b>Catalogue indisponible</b><span><button class="btn small" data-retry-ent="1">Réessayer</button></span></div>` : ""}
  <p class="hint">${plural(l.length, "entité")}${S.bq ? ` pour « ${esc(S.bq)} »` : ""}</p>
  <ul class="entlist">${vis.map((e) => `<li><button class="item${S.entSel === e.i ? " on" : ""}" data-ent="${esc(e.i)}"><b>${esc(e.n)}</b><span>${esc(CAT[e.c] || e.c)}${e.r.length ? " · " + esc(e.r.slice(0, 2).map(libRegion).join(", ")) : ""}</span><span class="mono">${e.np} passages · ${e.nf} figures</span></button></li>`).join("")}</ul>
  ${l.length > vis.length ? `<p class="hint">${l.length - vis.length} autres : affine la recherche.</p>` : ""}`;
}
async function ouvrirLivre(id, ch) {
  S.bib.livre = id; S.bib.ch = ch ?? null; S.entSel = null; S.detail = true;
  S.entView = ch == null ? { type: "livre", id } : { type: "chap", id, ch, state: "loading" }; render();
  if (ch == null) return;
  const b = S.bookById.get(id);
  try {
    const [figs, ps] = await Promise.all([figsChapitre(b, ch), passagesChapitre(id, ch)]);
    if (S.bib.ch !== ch || S.bib.livre !== id) return;
    S.entView = { type: "chap", id, ch, state: "ok", figs, ps };
  } catch (e) { S.entView = { type: "chap", id, ch, state: "err", err: messageErreur(e) }; }
  render();
}
async function ouvrirEntite(id) {
  S.entSel = id; S.bib.livre = null; S.entView = { type: "ent", id, state: "loading" }; S.detail = true; render();
  try {
    const d = await detailEntite(id);
    const pids = (d?.p || []).slice(0, 12), fids = (d?.f || []).slice(0, 30);
    const [ps, figs] = await Promise.all([Promise.all(pids.map((p) => lirePassage(p).catch(() => null))), figsParId(fids)]);
    if (S.entSel !== id) return;
    S.entView = { type: "ent", id, state: "ok", d, ps: ps.filter(Boolean), figs, totP: (d?.p || []).length, totF: (d?.f || []).length };
  } catch (e) { S.entView = { type: "ent", id, state: "err", err: messageErreur(e) }; }
  render();
}
function ficheDeEntite(e) {
  const slugs = new Set([slugify(e.n), ...e.s.map(slugify)]);
  return [...S.fiches.values()].find((f) => slugs.has(f.slug) || (f.alias || []).some((a) => slugs.has(a)));
}
function grilleFigures(figs, ent) {
  S.lb = { list: figs.map((g) => ({ id: g.id, cap: g.cap, src: `${bookShort(g.b)}, fig. ${g.fig}${g.pa || ""}${g.pg ? `, p. ${g.pg}` : ""}`, dd: "", slug: null, ent })), i: 0 };
  return figs.length ? `<div class="bthumbs">${figs.map((g, i) => `<button class="bthumb" data-lb="${i}" title="${esc(g.cap.slice(0, 160))}"><img data-img="${esc(g.id)}" alt="${esc(g.cap.slice(0, 120))}"><span>${esc(bookShort(g.b))} · fig. ${esc(g.fig)}${esc(g.pa || "")}</span></button>`).join("")}</div>` : `<p class="hint">Aucune figure.</p>`;
}
function listePassages(ps) {
  return ps.map((p) => `<article class="psg"><span class="mono">${esc(srcLabel(p))}</span><p>${esc(p.t.length > 700 ? p.t.slice(0, 700) + " …" : p.t)}</p><button class="btn small" data-ref="${esc(p.id)}">Lire en entier</button></article>`).join("") || `<p class="hint">Aucun passage.</p>`;
}
function filAriane(v) {
  const parts = [`<button data-bretour="1">Bibliothèque</button>`];
  const b = v && v.id && S.bookById.get(v.id);
  if (v && (v.type === "livre" || v.type === "lecture" || v.type === "chap") && b) {
    parts.push(v.type === "livre" ? `<span>${esc(b.court)}</span>` : `<button data-livre="${esc(b.id)}">${esc(b.court)}</button>`);
    if (v.ch != null) { const c = chapitre(b, v.ch); parts.push(`<span>Chapitre ${v.ch}${c ? " · " + esc(c.t) : ""}</span>`); }
  } else if (v && v.type === "ent") { const e = S.ent.get(v.id); parts.push(`<button data-bvue="entites">Entités</button>`, `<span>${esc(e ? e.n : "")}</span>`); }
  return `<nav class="ariane" aria-label="Fil d'Ariane">${parts.join('<i aria-hidden="true">›</i>')}</nav>`;
}
function biblioDroite() {
  const v = S.entView;
  if (v) return filAriane(v) + biblioDroiteCorps(v);
  return biblioDroiteCorps(v);
}
function biblioDroiteCorps(v) {
  if (!v) return `<div class="bempty"><h2>Bibliothèque</h2><p>Tout ce que l'application peut lire dans l'index : les ouvrages et leurs chapitres, les figures avec leur légende, et le catalogue des entités pathologiques. Choisis un ouvrage ou une entité à gauche.</p>${S.manifest ? `<p class="hint">Index version ${esc(S.manifest.version)} · lu depuis l'ouverture : ${S.lus.docs} fichiers, ${(S.lus.octets / 1024).toFixed(0)} Ko.</p>` : ""}</div>`;
  const back = `<button class="btn small bback" data-back="1">‹ Liste</button>`;
  if (v.type === "livre") {
    const b = S.bookById.get(v.id); if (!b) return "";
    return back + `<span class="label">${esc(libDomaine(b.domaine))}${b.id === "top3-msk" ? " · banque de cas" : ""}</span><h1 class="btitle">${esc(b.titre)}</h1>
      <p class="hint">${esc(b.auteurs.join(", "))}${b.annee ? ` · ${b.annee}` : ""} · ${b.langue === "fr" ? "français" : "anglais"} · ${b.passages.toLocaleString("fr-BE")} passages · ${b.figures.toLocaleString("fr-BE")} figures</p>
      <div class="row"><button class="btn primary small" data-livre="${esc(b.id)}" data-lire="${(() => { try { return +localStorage.getItem("rad-lecture-" + b.id) || b.chapitres[0].n; } catch { return b.chapitres[0].n; } })()}">Lire le livre</button></div>
      <ol class="chaps">${b.chapitres.filter((c) => S.dom === "tous" || c.d.includes(S.dom)).map((c) => `<li><button data-livre="${esc(b.id)}" data-lire="${c.n}"><span class="n">${c.n}</span><span class="t">${esc(c.t)}</span><span class="p mono">${c.p && c.p[0] ? `p. ${esc(c.p[0])}–${esc(c.p[1])}` : ""}</span>${c.d.length > 1 ? `<span class="d">${esc(c.d.filter((x) => x !== b.domaine).map(libDomaine).join(", "))}</span>` : ""}</button></li>`).join("")}</ol>`;
  }
  if (v.type === "lecture") return lectureHtml(v);
  if (v.type === "chap") {
    const b = S.bookById.get(v.id), c = chapitre(b, v.ch);
    const head = back + `<button class="btn small" data-livre="${esc(b.id)}">‹ ${esc(b.court)}</button><span class="label">${esc(b.court)} · chapitre ${v.ch}</span><h1 class="btitle">${esc(c ? c.t : "")}</h1>`;
    if (v.state === "loading") return head + `<p class="hint">Lecture du chapitre dans l'index…</p>`;
    if (v.state === "err") return head + `<div class="alert"><b>Lecture impossible</b><span>${esc(v.err)} <button class="btn small" data-livre="${esc(b.id)}" data-chap="${v.ch}">Réessayer</button></span></div>`;
    return head + `<h2 class="bsech">Figures <span class="hint">${v.figs.length}</span></h2>${grilleFigures(v.figs, c ? c.t : "")}
      <h2 class="bsech">Passages <span class="hint">${v.ps.length}</span></h2>${listePassages(v.ps.slice(0, 40))}${v.ps.length > 40 ? `<p class="hint">${v.ps.length - 40} autres passages dans ce chapitre.</p>` : ""}`;
  }
  const e = S.ent.get(v.id); if (!e) return "";
  const f = ficheDeEntite(e);
  const head = back + `<span class="label">${esc(CAT[e.c] || e.c)} · ${esc(e.d.map(libDomaine).join(", "))}</span><h1 class="btitle">${esc(e.n)}</h1>
    ${e.s.length || e.a.length ? `<p class="hint">Aussi : ${esc([...e.a, ...e.s].slice(0, 12).join(" · "))}</p>` : ""}
    ${e.r.length ? `<p class="hint">Régions : ${esc(e.r.map(libRegion).join(", "))}</p>` : ""}
    <div class="row">${f ? `<button class="btn primary small" data-fiche="${esc(f.slug)}">Ouvrir la fiche</button>` : S.sample ? `<button class="btn primary small" data-genent="${esc(e.i)}">Créer la fiche</button>` : ""}</div>`;
  if (v.state === "loading") return head + `<p class="hint">Lecture des passages et des figures…</p>`;
  if (v.state === "err") return head + `<div class="alert"><b>Lecture impossible</b><span>${esc(v.err)} <button class="btn small" data-ent="${esc(e.i)}">Réessayer</button></span></div>`;
  const liees = (v.d?.l || []).map((x) => S.ent.get(x)).filter(Boolean);
  return head + `${liees.length ? `<h2 class="bsech">Entités liées</h2><div class="chips">${liees.map((x) => `<button class="chip" data-ent="${esc(x.i)}">${esc(x.n)}</button>`).join("")}</div>` : ""}
    <h2 class="bsech">Figures <span class="hint">${v.totF > v.figs.length ? `${v.figs.length} sur ${v.totF}` : v.figs.length}</span></h2>${grilleFigures(v.figs, e.n)}
    <h2 class="bsech">Passages <span class="hint">${v.totP > v.ps.length ? `${v.ps.length} sur ${v.totP}` : v.ps.length}</span></h2>${listePassages(v.ps)}`;
}
function clicBiblio(t) {
  const d = t.dataset;
  if (d.bretour) { S.bib.vue = "ouvrages"; S.bib.livre = null; S.bib.ch = null; S.entView = null; S.detail = false; render(); window.scrollTo(0, 0); return true; }
  if (d.bvue) { S.bib.vue = d.bvue; S.bib.livre = null; S.bib.ch = null; if (S.entView && S.entView.type !== "ent") S.entView = null; if (d.bvue === "entites" && S.entState === "idle") chargerEntites(); render(); return true; }
  if (d.bcat !== undefined && t.matches("[data-bcat]")) { S.bib.cat = d.bcat; render(); return true; }
  if (d.livre && d.lire != null) { ouvrirLecture(d.livre, +d.lire); return true; }
  if (d.livre) { ouvrirLivre(d.livre, d.chap != null ? +d.chap : null); return true; }
  return false;
}
