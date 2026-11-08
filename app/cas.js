/* ================= Cas : entraînement en conditions de vacation ================= */
S.cas = { mode: "alea", etat: "vide" };
S.casHist = { hist: [], qcm: [] };
const POIDS_TOP3 = 3;   // Top 3 MSK est une banque de cas : tiré plus souvent
async function chargerCasHist() {
  if (!S.uid || !S.db) return;
  try { const d = await S.db.doc(`data/users/${S.uid}/cas`).get(); if (d.exists) S.casHist = { hist: [], qcm: [], ...d.data() }; } catch {}
}
function sauverCasHist() {
  if (!S.uid || !S.db) return;
  S.casHist.hist = S.casHist.hist.slice(-300); S.casHist.qcm = S.casHist.qcm.slice(-200);
  S.db.doc(`data/users/${S.uid}/cas`).set(JSON.parse(JSON.stringify(S.casHist))).catch(() => {});
}
function livrePondere() {
  const ls = S.books.filter((b) => S.dom === "tous" || b.domaines.includes(S.dom));
  const w = ls.map((b) => (b.id === "top3-msk" ? POIDS_TOP3 : 1) * Math.max(1, b.figures));
  let r = Math.random() * w.reduce((a, b) => a + b, 0);
  for (let i = 0; i < ls.length; i++) { r -= w[i]; if (r <= 0) return ls[i]; }
  return ls[ls.length - 1];
}
async function contexteLivre(f) {
  const cp = await lireDoc("cp/" + f.b).catch(() => null);
  const ids = (cp && cp[f.id]) || [];
  const ps = (await Promise.all(ids.slice(0, 2).map((id) => lirePassage(id).catch(() => null)))).filter(Boolean);
  return ps.map((p) => ({ id: p.id, src: srcLabel(p), t: p.t.length > 1600 ? p.t.slice(0, 1600) + " …" : p.t }));
}
async function tirerCas(source) {
  if (!S.manifest) { toast("Le corpus n'est pas accessible : vérifie le connecteur GitHub."); return; }
  if (!S.sample) { toast("Claude n'est pas disponible dans cette vue."); return; }
  S.cas = { mode: S.cas.mode, etat: "tirage" }; render();
  try {
    let f = null;
    if (source && source.fid) f = (await figsParId([source.fid]))[0] || null;
    for (let essai = 0; !f && essai < 8; essai++) {
      const b = livrePondere(); if (!b) break;
      const chs = b.chapitres.filter((c) => S.dom === "tous" || c.d.includes(S.dom)).map((c) => c.n);
      const ch = chs[Math.floor(Math.random() * chs.length)];
      const figs = (await figsChapitre(b, ch)).filter((g) => (g.il || g.iv) && (g.capo || g.cap).length > 60 && g.role !== "schema" && !(g.m || []).includes("schema"));
      if (figs.length) f = figs[Math.floor(Math.random() * figs.length)];
    }
    if (!f) throw { message: "Aucune figure exploitable dans ce domaine." };
    const extraits = await contexteLivre(f);
    const ctx = await S.sample.json(`Tu prépares un cas d'entraînement en radiologie pour un interne, comme à la vacation.
À partir de la légende d'une figure et des extraits du livre qui la citent, rédige en français :
- "contexte" : la présentation clinique (âge, sexe, symptômes, antécédents utiles) en 1 à 3 phrases, en reprenant les éléments cliniques des extraits quand ils existent ;
- "examen" : la modalité, la région et l'incidence ou la séquence montrées.
Ne révèle NI le diagnostic, NI la sémiologie décrite dans la légende. Développe chaque acronyme entre parenthèses à sa première occurrence.
Réponds uniquement par {"contexte":"…","examen":"…"}.

Légende (${bookShort(f.b)}) : ${f.capo || f.cap}
${extraits.map((x) => `Extrait (${x.src}) : ${x.t}`).join("\n")}`, { modelTier: "quick", cache: false });
    S.cas = { mode: S.cas.mode, etat: "question", f, extraits, ctx: ctx || {}, source: source && source.origine };
  } catch (e) { S.cas = { mode: S.cas.mode, etat: "erreur", err: (e && (e.message || e.code)) || "erreur" }; }
  render();
}
async function corrigerCas() {
  const c = S.cas, rep = (casRoot().querySelector("#casRep")?.value || "").trim();
  if (!rep) { toast("Décris d'abord la sémiologie et ton diagnostic."); return; }
  c.rep = rep; c.etat = "correction"; render();
  try {
    const r = await S.sample.json(`Tu corriges un interne en radiologie sur un cas tiré d'un livre de référence.
Cas : ${c.ctx.contexte || ""} Examen : ${c.ctx.examen || ""}
Légende d'origine de la figure (référence, ${bookShort(c.f.b)}) : ${c.f.capo || c.f.cap}
${(c.extraits || []).map((x) => `Extrait du livre (${x.src}) : ${x.t}`).join("\n")}
Réponse de l'interne : ${rep}

Évalue la sémiologie et le diagnostic. Appuie-toi uniquement sur la légende et les extraits ; n'invente rien. Rédige en français et développe chaque acronyme entre parenthèses à sa première occurrence.
Réponds uniquement par {"note":0-10,"diagnostic":"diagnostic du livre","semiologie":["signes attendus"],"justes":["ce que l'interne a bien vu"],"manques":["ce qui manque ou est faux"],"explication":"4 à 6 phrases : pourquoi ce diagnostic, quels signes le portent, quel diagnostic différentiel écarter"}`, { modelTier: "default", cache: false });
    c.corr = r || {}; c.etat = "corrige";
    S.casHist.hist.push({ fid: c.f.id, note: Number(r?.note) || 0, at: Date.now(), dx: r?.diagnostic || "" });
    sauverCasHist();
  } catch (e) { c.etat = "question"; toast(sampleCopy(e), 6000); }
  render();
}

/* QCM générés sur les entités des notes */
async function qcmNotes() {
  const fs = [...S.fiches.values()].filter((f) => f.kind === "corpus" && f.fiche);
  if (!fs.length) { toast("Aucune fiche issue du corpus pour l'instant : crée d'abord des notes."); return; }
  if (!S.sample) { toast("Claude n'est pas disponible dans cette vue."); return; }
  S.cas = { mode: "revision", etat: "qcm-gen" }; render();
  const choix = fs.sort(() => Math.random() - 0.5).slice(0, 3);
  try {
    const r = await S.sample.json(`Tu écris des QCM de radiologie pour un interne, en français, à partir de fiches de révision sourcées.
Écris 6 QCM au total, répartis sur les fiches. Chaque QCM : un énoncé clinique ou sémiologique court, 4 propositions plausibles, une seule bonne réponse, une explication de 2 à 3 phrases qui cite la ou les références de la fiche ([P1], [F2]…). Développe chaque acronyme entre parenthèses à sa première occurrence. N'utilise que le contenu des fiches.
Réponds uniquement par {"qcm":[{"slug":"…","question":"…","options":["…","…","…","…"],"reponse":0,"explication":"…"}]}

${choix.map((f) => `### Fiche ${f.slug} — ${f.entite}\n${flatLines(f.fiche).map((l) => `- ${l.t || l.text || ""} ${(l.refs || []).map((x) => "[" + x + "]").join("")}`).join("\n").slice(0, 3500)}`).join("\n\n")}`, { modelTier: "default", cache: false });
    const q = (r?.qcm || []).filter((x) => x && Array.isArray(x.options) && x.options.length >= 2);
    if (!q.length) throw { message: "Claude n'a pas renvoyé de QCM exploitable." };
    S.cas = { mode: "revision", etat: "qcm", items: q, pos: 0, choix: null, score: 0 };
  } catch (e) { S.cas = { mode: "revision", etat: "erreur", err: (e && (e.message || e.code)) || "erreur" }; }
  render();
}
function repondreQcm(i) {
  const c = S.cas, q = c.items[c.pos]; if (c.choix != null) return;
  c.choix = i; if (i === q.reponse) c.score++;
  else { S.casHist.qcm.push({ ...q, at: Date.now() }); sauverCasHist(); }
  render();
}
function qcmErreurs() {
  const q = S.casHist.qcm.slice(-12).sort(() => Math.random() - 0.5).slice(0, 6);
  if (!q.length) { toast("Aucune erreur de QCM sur tes notes à refaire."); return; }
  S.casHist.qcm = S.casHist.qcm.filter((x) => !q.includes(x)); sauverCasHist();
  S.cas = { mode: "revision", etat: "qcm", items: q, pos: 0, choix: null, score: 0 };
  render();
}
function casSurNotes() {
  const figs = [];
  for (const f of S.fiches.values()) for (const [k, r] of Object.entries(f.refs || {})) if (k.startsWith("F") && r.id) figs.push(r.id);
  if (!figs.length) { toast("Tes fiches ne contiennent pas encore de figures."); return; }
  tirerCas({ fid: figs[Math.floor(Math.random() * figs.length)], origine: "notes" });
}
function casRates() {
  const rates = S.casHist.hist.filter((h) => h.note < 6);
  if (!rates.length) { toast("Aucun cas raté à refaire."); return; }
  const h = rates[Math.floor(Math.random() * rates.length)];
  tirerCas({ fid: h.fid, origine: "ratés" });
}

/* rendu */
function casRoot() { return $("right"); }
function casGauche() {
  const LR = window.LR, m = LR ? LR.dueMissed(null).length : 0, r = LR ? LR.rqTodo().length : 0;
  const rates = S.casHist.hist.filter((h) => h.note < 6).length, moy = S.casHist.hist.slice(-20);
  const nf = [...S.fiches.values()].filter((f) => f.kind === "corpus").length;
  return `<div class="libhead"><span class="label">Cas</span><span class="hint">${esc(libDomaine(S.dom))}</span></div>
  <div class="casmodes">
    <button class="item${S.cas.mode === "alea" ? " on" : ""}" data-casmode="alea"><b>Aléatoire</b><span>Une image et son contexte tirés des livres, à décrire et diagnostiquer</span></button>
    <button class="item${S.cas.mode === "revision" ? " on" : ""}" data-casmode="revision"><b>Révision</b><span>${m + r} erreurs d'Apprentissage · ${rates} cas ratés · ${nf} fiches</span></button>
  </div>
  ${moy.length ? `<p class="hint">Moyenne des 20 derniers cas : <b>${(moy.reduce((a, h) => a + h.note, 0) / moy.length).toFixed(1)} / 10</b> sur ${S.casHist.hist.length} cas.</p>` : ""}`;
}
function carteRev(titre, n, txt, attr, actif) {
  return `<article class="revcard"><div><b>${esc(titre)}</b> <span class="pill plain">${n}</span></div><p class="hint">${esc(txt)}</p><button class="btn ${actif ? "primary" : ""} small" ${attr} ${n ? "" : "disabled"}>Commencer</button></article>`;
}
function casDroite() {
  const c = S.cas;
  if (!S.owner && !S.manifest && c.mode === "alea") return `<div class="bempty"><h2>Cas aléatoires</h2><p>Les cas sont tirés des livres de l'index, lus dans le dépôt GitHub corpus-radio. Ce compte n'y a pas accès : ajoute le connecteur GitHub dans claude.ai.</p></div>`;
  if (c.mode === "revision" && !["qcm", "qcm-gen", "question", "correction", "corrige", "tirage", "erreur"].includes(c.etat)) {
    const LR = window.LR, m = LR ? LR.dueMissed(null).length : 0, r = LR ? LR.rqTodo().length : 0;
    const rates = S.casHist.hist.filter((h) => h.note < 6).length, nf = [...S.fiches.values()].filter((f) => f.kind === "corpus").length;
    return `<div class="bempty"><h2>Révision</h2><p>Tout ce qui est à revoir, au même endroit : les erreurs des QCM et des défis du jour d'Apprentissage, les cas ratés, et des QCM et cas créés par Claude sur les entités de tes notes.</p></div>
    <div class="revgrid">
      ${carteRev("Erreurs de QCM et de défis", m, "Les questions ratées d'Apprentissage, puis les cas ratés en question ouverte.", 'data-rev="erreurs"', true)}
      ${carteRev("Cas ouverts à reprendre", r, "Image seule et « Quel est votre diagnostic ? », tous modules mélangés.", 'data-rev="rapide"')}
      ${carteRev("QCM sur mes notes", nf, "Six QCM écrits par Claude à partir de tes fiches, avec leurs références.", 'data-rev="qcm"')}
      ${carteRev("Cas sur mes notes", nf, "Une figure d'une de tes fiches, à décrire et diagnostiquer.", 'data-rev="casnotes"')}
      ${carteRev("Cas aléatoires ratés", rates, "Les cas notés moins de 6 / 10, à refaire.", 'data-rev="casrates"')}
      ${carteRev("Erreurs de QCM sur mes notes", S.casHist.qcm.length, "Les QCM générés que tu as ratés.", 'data-rev="qcmerr"')}
    </div>`;
  }
  if (c.etat === "vide") return `<div class="bempty"><h2>Cas aléatoire</h2><p>Une image tirée au hasard dans les livres${S.dom !== "tous" ? ` du domaine ${esc(libDomaine(S.dom))}` : ""}, avec son contexte clinique. Décris la sémiologie, donne ton diagnostic, puis Claude te corrige d'après la légende du livre.</p><button class="btn primary" data-tirer="1">Tirer un cas</button></div>`;
  if (c.etat === "tirage") return `<p class="hint">Tirage d'un cas dans les livres…</p>`;
  if (c.etat === "qcm-gen") return `<p class="hint">Claude écrit des QCM à partir de tes fiches…</p>`;
  if (c.etat === "erreur") return `<div class="alert"><b>Cas indisponible</b><span>${esc(String(c.err))} <button class="btn small" data-tirer="1">Réessayer</button></span></div>`;
  if (c.etat === "qcm") {
    const q = c.items[c.pos];
    if (!q) return `<div class="bempty"><h2>Série terminée</h2><p>${c.score} / ${c.items.length} bonnes réponses. Les erreurs reviendront dans « Erreurs de QCM sur mes notes ».</p><button class="btn primary" data-casmode="revision">Retour à la révision</button></div>`;
    return `<span class="label">QCM ${c.pos + 1} / ${c.items.length}${q.slug ? ` · fiche ${esc((S.fiches.get(q.slug) || {}).entite || q.slug)}` : ""}</span>
      <h2 class="btitle" style="font-size:20px">${esc(q.question)}</h2>
      <div class="qopts">${q.options.map((o, i) => `<button class="qopt${c.choix == null ? "" : i === q.reponse ? " ok" : i === c.choix ? " ko" : ""}" data-qrep="${i}" ${c.choix == null ? "" : "disabled"}>${esc(o)}</button>`).join("")}</div>
      ${c.choix != null ? `<p class="expl">${esc(q.explication || "")}</p><button class="btn primary" data-qnext="1">${c.pos + 1 < c.items.length ? "Question suivante" : "Terminer"}</button>` : ""}`;
  }
  const f = c.f;
  const fig = `<figure class="casfig"><img data-img="${esc(f.id)}" data-full="1" alt="Image du cas"></figure>`;
  const head = `<span class="label">${c.source === "notes" ? "Cas sur mes notes" : c.source === "ratés" ? "Cas à refaire" : "Cas aléatoire"} · ${esc(bookShort(f.b))}</span>
    <p class="casctx"><b>Contexte.</b> ${esc(c.ctx.contexte || "")}</p><p class="casctx"><b>Examen.</b> ${esc(c.ctx.examen || "")}</p>`;
  if (c.etat === "question" || c.etat === "correction") return head + fig + `
    <label class="label" for="casRep">Ta réponse : sémiologie, puis diagnostic</label>
    <textarea id="casRep" rows="5" placeholder="Décris ce que tu vois, puis donne ton diagnostic et ton différentiel.">${esc(c.rep || "")}</textarea>
    <div class="row"><button class="btn primary" data-corriger="1" ${c.etat === "correction" ? "disabled" : ""}>${c.etat === "correction" ? "Correction en cours…" : "Soumettre à Claude"}</button><button class="btn small" data-tirer="1">Autre cas</button></div>`;
  const r = c.corr || {};
  return head + fig + `
    <div class="corr"><div class="note">${esc(String(r.note ?? "?"))}<small>/10</small></div><div><span class="label">Diagnostic du livre</span><h2 class="btitle" style="font-size:20px">${esc(r.diagnostic || "")}</h2></div></div>
    <p class="hint"><b>Ta réponse :</b> ${esc(c.rep)}</p>
    ${(r.justes || []).length ? `<h3 class="bsech">Bien vu</h3><ul class="lines">${r.justes.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
    ${(r.manques || []).length ? `<h3 class="bsech">À revoir</h3><ul class="lines">${r.manques.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
    ${(r.semiologie || []).length ? `<h3 class="bsech">Sémiologie attendue</h3><ul class="lines">${r.semiologie.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
    <h3 class="bsech">Explication</h3><p class="expl">${esc(r.explication || "")}</p>
    <h3 class="bsech">Légende du livre</h3><p class="expl">${esc(f.capo || f.cap)}</p><p class="hint">${esc(bookShort(f.b))}, fig. ${esc(f.fig)}${esc(f.pa || "")}${f.pg ? `, p. ${esc(f.pg)}` : ""}</p>
    <div class="row"><button class="btn primary" data-tirer="1">Cas suivant</button>${c.mode === "revision" ? `<button class="btn small" data-casmode="revision">Retour à la révision</button>` : ""}</div>`;
}
function clicCas(t) {
  const d = t.dataset;
  if (d.casmode) { S.cas = { mode: d.casmode, etat: "vide" }; render(); return true; }
  if (d.tirer) { tirerCas(S.cas.mode === "revision" && S.cas.f && S.cas.source ? null : null); return true; }
  if (d.corriger) { corrigerCas(); return true; }
  if (d.qrep != null && d.qrep !== undefined && t.matches("[data-qrep]")) { repondreQcm(+d.qrep); return true; }
  if (d.qnext) { S.cas.pos++; S.cas.choix = null; render(); return true; }
  if (d.rev) {
    if (d.rev === "erreurs" || d.rev === "rapide") { if (window.ESPACE) window.ESPACE("apprentissage"); if (window.LR) (d.rev === "erreurs" ? window.LR.startReview(null) : window.LR.startRapid(false)); }
    else if (d.rev === "qcm") qcmNotes();
    else if (d.rev === "qcmerr") qcmErreurs();
    else if (d.rev === "casnotes") casSurNotes();
    else if (d.rev === "casrates") casRates();
    return true;
  }
  return false;
}
