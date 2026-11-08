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
function groupesFigures(figs) {
  const g = new Map();
  for (const f of figs) { const k = f.fig; if (!g.has(k)) g.set(k, []); g.get(k).push(f); }
  const out = [];
  for (const panels of g.values()) {
    panels.sort((x, y) => String(x.pa || "").localeCompare(String(y.pa || "")));
    const f0 = panels[0], cap = f0.capo || f0.cap || "";
    if (cap.length < 60 || f0.role === "schema" || (f0.m || []).includes("schema")) continue;
    if (!panels.every((p) => p.il || p.iv)) continue;
    const attendus = (f0.pn || []).length;
    if (attendus && panels.length < attendus) continue;               // un panneau cité sans image : cas incomplet
    if (panels.length > 8) continue;
    out.push(panels);
  }
  return out;
}
async function panneauxDe(f) {
  const b = S.bookById.get(f.b), tous = await figsChapitre(b, f.ch);
  const g = groupesFigures(tous.filter((x) => x.fig === f.fig));
  return g[0] || null;
}
async function tirerCas(source) {
  if (!S.manifest) { toast("L'index n'est pas accessible : vérifie le connecteur GitHub."); return; }
  if (!S.sample) { toast("Claude n'est pas disponible dans cette vue."); return; }
  S.cas = { mode: S.cas.mode, etat: "tirage", etape: "Choix d'une figure dans les livres" }; render();
  const etape = (t) => { S.cas.etape = t; render(); };
  try {
    let panels = null;
    if (source && source.fid) { const f = (await figsParId([source.fid]))[0]; if (f) panels = await panneauxDe(f); }
    for (let essai = 0; !panels && essai < 10; essai++) {
      const b = livrePondere(); if (!b) break;
      const chs = b.chapitres.filter((c) => S.dom === "tous" || c.d.includes(S.dom)).map((c) => c.n);
      const ch = chs[Math.floor(Math.random() * chs.length)];
      etape(`Lecture des figures : ${b.court}, chapitre ${ch}`);
      const gs = groupesFigures(await figsChapitre(b, ch));
      if (gs.length) panels = gs[Math.floor(Math.random() * gs.length)];
    }
    if (!panels) throw { message: "Aucune figure complète et exploitable trouvée dans ce domaine." };
    const f = panels[0], lettres = panels.map((p) => p.pa).filter(Boolean);
    etape("Lecture des passages qui citent la figure");
    const extraits = await contexteLivre(f).catch(() => []);
    etape("Claude construit le cas");
    const r = await avecDelai(S.sample.json(`Tu construis un cas d'entraînement de radiologie pour un interne de 4e année, comme une vacation de lecture.

DONNÉES DU LIVRE (${bookShort(f.b)})
Légende de la figure : ${f.capo || f.cap}
${lettres.length ? `Images affichées à l'interne : ${lettres.map((l) => "(" + l + ")").join(", ")} — et AUCUNE autre.` : "Une seule image est affichée à l'interne."}
${extraits.map((x) => `Extrait qui cite la figure (${x.src}) : ${x.t}`).join("\n")}

CONSIGNES
- "contexte" : la présentation clinique en 2 à 4 phrases (âge, sexe, motif, durée, antécédents ou biologie utiles). Reprends les éléments cliniques des extraits et de la légende quand ils existent ; sinon, propose une présentation typique et cohérente avec le diagnostic, sans le nommer.
- "images" : une entrée par image affichée, avec la lettre ("" s'il n'y en a qu'une) et sa description technique seulement : modalité, région, plan ou incidence, séquence IRM (T1, T2, STIR, T1 après injection de gadolinium…), fenêtre TDM, avec ou sans injection. Ne décris aucune anomalie.
- Ne mentionne aucune image, séquence ou incidence qui ne fait pas partie des images affichées.
- Ne révèle ni le diagnostic, ni la sémiologie, ni un indice qui les donne (pas de nom d'entité, pas de « lésion de… »).
- "question" : la consigne posée à l'interne, adaptée au cas.
- Français, chaque acronyme développé entre parenthèses à sa première occurrence.

Réponds uniquement par {"titre":"motif neutre en 3 à 6 mots","contexte":"…","images":[{"panneau":"a","description":"…"}],"question":"…","difficulte":"facile|moyen|difficile"}`, { modelTier: "default", cache: false }), 90000);
    const desc = new Map(((r && r.images) || []).map((x) => [String(x.panneau || "").toLowerCase().replace(/[^a-z]/g, ""), x.description || ""]));
    const images = panels.map((p, i) => ({ id: p.id, lettre: p.pa || "", description: desc.get(String(p.pa || "").toLowerCase()) || (panels.length === 1 ? desc.get("") || [...desc.values()][0] || "" : "") }));
    S.cas = { mode: S.cas.mode, etat: "question", f, panels, images, extraits, ctx: r || {}, source: source && source.origine };
  } catch (e) { S.cas = { mode: S.cas.mode, etat: "erreur", err: messageErreur(e) }; }
  render();
}
function messageErreur(e) {
  const c = e && e.code;
  if (c === "timeout") return "Pas de réponse en temps voulu (GitHub ou Claude).";
  if (c === "not_granted") return "L'accès a été refusé pour cette page : autorise le connecteur GitHub et Claude.";
  if (c === "server_not_connected" || c === "server_not_found") return "Le connecteur GitHub n'est pas connecté sur ce compte.";
  if (c === "rate_limited") return "Trop de demandes d'un coup : réessaie dans un instant.";
  return (e && (e.message || c)) || "Erreur inconnue.";
}
async function corrigerCas() {
  const c = S.cas, rep = (casRoot().querySelector("#casRep")?.value || "").trim();
  if (rep.length < 10) { toast("Décris la sémiologie et donne ton diagnostic avant de soumettre."); return; }
  c.rep = rep; c.etat = "correction"; render();
  try {
    const r = await avecDelai(S.sample.json(`Tu es un radiologue senior qui corrige un interne de 4e année après une vacation de lecture. Sois exigeant, précis et bienveillant.

CAS
Contexte : ${c.ctx.contexte || ""}
Images : ${c.images.map((x) => `${x.lettre ? "(" + x.lettre + ") " : ""}${x.description}`).join(" ; ")}

RÉFÉRENCE (seule source autorisée)
Légende du livre (${bookShort(c.f.b)}) : ${c.f.capo || c.f.cap}
${(c.extraits || []).map((x) => `Extrait du livre (${x.src}) : ${x.t}`).join("\n")}

RÉPONSE DE L'INTERNE
${rep}

CONSIGNES
- Note sur 10 = sémiologie /4 + diagnostic /4 + diagnostic différentiel /2. Ne donne pas de points pour un élément vague ou non argumenté.
- Compare la réponse à la référence élément par élément. Classe chaque élément de l'interne en "justes" ou "erreurs" (affirmation fausse ou non soutenue par la référence) ; liste dans "manques" ce que la référence décrit et que l'interne n'a pas dit.
- "semiologie_par_image" : pour chaque image affichée, les signes attendus d'après la légende ; si la légende ne précise rien pour une image, écris « non précisé par la légende ».
- "differentiels" : 2 à 4 diagnostics à discuter, chacun avec l'élément de la référence qui l'écarte ; si la référence ne permet pas d'écarter, dis-le.
- N'invente aucune donnée absente de la référence. Français, chaque acronyme développé entre parenthèses à sa première occurrence, phrases courtes.

Réponds uniquement par {"note":0,"bareme":{"semiologie":0,"diagnostic":0,"differentiel":0},"verdict":"une phrase de synthèse","diagnostic":"diagnostic de référence","arguments":["signe ou donnée qui porte le diagnostic"],"semiologie_par_image":[{"panneau":"a","signes":["…"]}],"justes":["…"],"erreurs":["…"],"manques":["…"],"differentiels":[{"diagnostic":"…","contre":"…"}],"piege":"le piège classique de ce cas","a_retenir":"une phrase"}`, { modelTier: "complex", cache: false }), 120000);
    const B = (r && r.bareme) || {}, borne = (x, m) => Math.max(0, Math.min(m, Number(x) || 0));
    r.bareme = { semiologie: borne(B.semiologie, 4), diagnostic: borne(B.diagnostic, 4), differentiel: borne(B.differentiel, 2) };
    r.note = Math.round((r.bareme.semiologie + r.bareme.diagnostic + r.bareme.differentiel) * 10) / 10;
    c.corr = r; c.etat = "corrige";
    S.casHist.hist.push({ fid: c.f.id, note: r.note, at: Date.now(), dx: r.diagnostic || "" });
    sauverCasHist();
  } catch (e) { c.etat = "question"; toast(messageErreur(e), 6000); }
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
  const rates0 = S.casHist.hist.filter((h) => h.note < 6).length, moy0 = S.casHist.hist.slice(-20);
  const barre = `<div class="cas-top"><div class="seg" role="tablist"><button role="tab" aria-selected="${c.mode === "alea"}" data-casmode="alea">Aléatoire</button><button role="tab" aria-selected="${c.mode === "revision"}" data-casmode="revision">Révision</button></div>
    <span class="hint">${esc(libDomaine(S.dom))}${moy0.length ? ` · moyenne ${(moy0.reduce((a, h) => a + h.note, 0) / moy0.length).toFixed(1)} / 10 sur les ${moy0.length} derniers cas` : ""}${rates0 ? ` · ${rates0} à refaire` : ""}</span></div>`;
  return barre + casContenu();
}
function casContenu() {
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
      ${carteRev("QCM d'images Top 3", S.bookById.has("top3-msk") ? 5 : 0, "Cinq cas de Top 3 Differentials en QCM : image, énoncé, quatre diagnostics.", 'data-rev="top3"')}
      ${carteRev("Erreurs de QCM sur mes notes", S.casHist.qcm.length, "Les QCM générés que tu as ratés.", 'data-rev="qcmerr"')}
    </div>`;
  }
  if (c.etat === "vide") return `<div class="bempty"><h2>Cas aléatoire</h2><p>Une image tirée au hasard dans les livres${S.dom !== "tous" ? ` du domaine ${esc(libDomaine(S.dom))}` : ""}, avec son contexte clinique. Décris la sémiologie, donne ton diagnostic, puis Claude te corrige d'après la légende du livre.</p><button class="btn primary" data-tirer="1">Tirer un cas</button></div>`;
  if (c.etat === "tirage") return `<div class="bempty"><h2>Préparation du cas…</h2><p class="hint">${esc(c.etape || "")}</p></div>`;
  if (c.etat === "qcm-gen") return `<p class="hint">Claude écrit des QCM à partir de tes fiches…</p>`;
  if (c.etat === "erreur") return `<div class="alert"><b>Cas indisponible</b><span>${esc(String(c.err))} <button class="btn small" data-tirer="1">Réessayer</button></span></div>`;
  if (c.etat === "qcm") {
    const q = c.items[c.pos];
    if (!q) return `<div class="bempty"><h2>Série terminée</h2><p>${c.score} / ${c.items.length} bonnes réponses. Les erreurs reviendront dans « Erreurs de QCM sur mes notes ».</p><button class="btn primary" data-casmode="revision">Retour à la révision</button></div>`;
    return `<span class="label">QCM ${c.pos + 1} / ${c.items.length}${q.slug ? ` · fiche ${esc((S.fiches.get(q.slug) || {}).entite || q.slug)}` : ""}</span>
      ${q.fid ? `<figure class="casfig"><img data-img="${esc(q.fid)}" data-full="1" alt="Image du cas"></figure>` : ""}
      <h2 class="btitle" style="font-size:20px">${esc(q.question)}</h2>
      <div class="qopts">${q.options.map((o, i) => `<button class="qopt${c.choix == null ? "" : i === q.reponse ? " ok" : i === c.choix ? " ko" : ""}" data-qrep="${i}" ${c.choix == null ? "" : "disabled"}>${esc(o)}</button>`).join("")}</div>
      ${c.choix != null ? `<p class="expl">${esc(q.explication || "")}</p><button class="btn primary" data-qnext="1">${c.pos + 1 < c.items.length ? "Question suivante" : "Terminer"}</button>` : ""}`;
  }
  const f = c.f;
  S.lb = { list: c.images.map((x) => ({ id: x.id, cap: x.description || "", src: `${bookShort(f.b)}${x.lettre ? ` · image ${x.lettre}` : ""}`, dd: "", slug: null, ent: "Cas" })), i: 0 };
  const galerie = `<div class="casgal n${Math.min(c.images.length, 4)}">${c.images.map((x, i) => `<figure><button class="casimg" data-lb="${i}" aria-label="Agrandir l'image ${esc(x.lettre)}"><img data-img="${esc(x.id)}" data-full="1" alt="Image ${esc(x.lettre)} du cas"></button><figcaption>${x.lettre ? `<b>${esc(x.lettre)}</b> ` : ""}${esc(x.description || "")}</figcaption></figure>`).join("")}</div>`;
  const tete = `<div class="cashead"><span class="label">${c.source === "notes" ? "Cas sur mes notes" : c.source === "ratés" ? "Cas à refaire" : "Cas aléatoire"} · ${esc(bookShort(f.b))}${c.ctx.difficulte ? ` · ${esc(c.ctx.difficulte)}` : ""}</span><h2 class="btitle">${esc(c.ctx.titre || "Cas clinique")}</h2></div>
    <div class="casctx"><p><b>Clinique.</b> ${esc(c.ctx.contexte || "")}</p></div>${galerie}`;
  if (c.etat === "question" || c.etat === "correction") return tete + `
    <div class="casform"><label class="label" for="casRep">${esc(c.ctx.question || "Décris la sémiologie, puis donne ton diagnostic et ton diagnostic différentiel.")}</label>
    <textarea id="casRep" rows="6" placeholder="Sémiologie : …&#10;Diagnostic : …&#10;Différentiel : …">${esc(c.rep || "")}</textarea>
    <div class="row"><button class="btn primary" data-corriger="1" ${c.etat === "correction" ? "disabled" : ""}>${c.etat === "correction" ? "Correction en cours…" : "Soumettre"}</button><button class="btn small" data-tirer="1">Passer ce cas</button></div></div>`;
  const r = c.corr || {}, B = r.bareme || {};
  const barre = (lib, v, m) => `<div class="bar-l"><span>${lib}</span><span class="bar"><i style="width:${Math.round(100 * (v || 0) / m)}%"></i></span><b>${v ?? 0} / ${m}</b></div>`;
  const liste = (t, xs, cls) => (xs || []).length ? `<div class="fb ${cls}"><h3>${t}</h3><ul>${xs.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>` : "";
  return tete + `
    <section class="feedback">
      <div class="fb-score"><div class="note ${r.note >= 7 ? "ok" : r.note >= 5 ? "moy" : "ko"}">${esc(String(r.note ?? "?"))}<small>/10</small></div>
        <div class="fb-bars">${barre("Sémiologie", B.semiologie, 4)}${barre("Diagnostic", B.diagnostic, 4)}${barre("Différentiel", B.differentiel, 2)}</div></div>
      <p class="verdict">${esc(r.verdict || "")}</p>
      <div class="fb-dx"><span class="label">Diagnostic</span><h3>${esc(r.diagnostic || "")}</h3>${(r.arguments || []).length ? `<ul>${r.arguments.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}</div>
      <div class="fb-cols">${liste("Bien vu", r.justes, "ok")}${liste("Erreurs", r.erreurs, "ko")}${liste("Manques", r.manques, "moy")}</div>
      ${(r.semiologie_par_image || []).length ? `<div class="fb"><h3>Sémiologie attendue</h3><dl class="semio">${r.semiologie_par_image.map((x) => `<dt>${x.panneau ? "Image " + esc(x.panneau) : "Image"}</dt><dd>${esc((x.signes || []).join(" · "))}</dd>`).join("")}</dl></div>` : ""}
      ${(r.differentiels || []).length ? `<div class="fb"><h3>Diagnostic différentiel</h3><table class="ddx"><tbody>${r.differentiels.map((x) => `<tr><th>${esc(x.diagnostic || "")}</th><td>${esc(x.contre || "")}</td></tr>`).join("")}</tbody></table></div>` : ""}
      ${r.piege ? `<div class="fb moy"><h3>Piège</h3><p>${esc(r.piege)}</p></div>` : ""}
      ${r.a_retenir ? `<div class="fb cle"><h3>À retenir</h3><p>${esc(r.a_retenir)}</p></div>` : ""}
      <details class="fb src"><summary>Ta réponse et la source du livre</summary><p><b>Ta réponse :</b> ${esc(c.rep)}</p><p><b>Légende (${esc(bookShort(f.b))}, fig. ${esc(f.fig)}${f.pg ? `, p. ${esc(f.pg)}` : ""}) :</b> ${esc(f.capo || f.cap)}</p>${(c.extraits || []).map((x) => `<p class="hint">${esc(x.src)}</p>`).join("")}</details>
    </section>
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
    else if (d.rev === "top3") qcmTop3();
    return true;
  }
  return false;
}
