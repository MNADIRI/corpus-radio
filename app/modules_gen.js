/* ================= Leçons générées à la demande (chapitres pas encore traités) =================
   Lecture du chapitre dans l'index GitHub (passages + figures), rédaction par Claude au format des
   modules d'Apprentissage, enregistrement dans modules_generes (visible par tous les lecteurs). */
async function passagesChapitre(lid, ch) {
  const chb = await lireDoc("chb/" + lid); const r = chb && chb[ch]; if (!r) return [];
  const blocs = await Promise.all(Array.from({ length: r[1] - r[0] + 1 }, (_, k) => lireDoc(`pb/${lid}-${r[0] + k}`).catch(() => null)));
  return blocs.flatMap((d) => (d && d.p) || []).filter((p) => p.ch === ch);
}
function decouperEtapes(m) {
  const n = m.lesson.length, q = m.quiz.length, parts = Math.max(1, Math.min(3, Math.round(n / 3)));
  const subs = [];
  for (let k = 0; k < parts; k++) {
    const s0 = Math.floor(k * n / parts), s1 = Math.floor((k + 1) * n / parts), q0 = Math.floor(k * q / parts), q1 = Math.floor((k + 1) * q / parts);
    const secs = Array.from({ length: s1 - s0 }, (_, i) => s0 + i);
    subs.push({ hs: secs.map((i) => m.lesson[i].h), secs, qs: Array.from({ length: q1 - q0 }, (_, i) => q0 + i) });
  }
  return subs;
}
async function genererModule(src, mid, onEtape) {
  if (!S.sample) throw { message: "Claude n'est pas disponible dans cette vue." };
  if (!S.manifest) await loadCorpusMeta();
  if (!S.manifest) throw { message: "L'index des livres n'est pas accessible (connecteur GitHub)." };
  const b = S.bookById.get(src.livre), c = chapitre(b, src.ch);
  onEtape && onEtape("Lecture du chapitre dans l'index");
  const [ps, figs] = await Promise.all([passagesChapitre(src.livre, src.ch), figsChapitre(b, src.ch)]);
  if (!ps.length) throw { message: "Aucun passage trouvé pour ce chapitre dans l'index." };
  let texte = "", pages = new Set();
  for (const p of ps) { if (texte.length > 60000) break; texte += `\n[${p.id}${p.pg && p.pg.length ? `, p. ${p.pg[0]}` : ""}] ${p.sec ? p.sec + " — " : ""}${p.t}`; (p.pg || []).forEach((x) => pages.add(+x)); }
  const lfig = figs.filter((g) => g.il || g.iv).slice(0, 45).map((g) => `${g.id} : ${(g.capo || g.cap).slice(0, 260)}`).join("\n");
  const regles = `Écris en français, pour un interne en radiologie. Développe chaque acronyme entre parenthèses à sa première occurrence. N'affirme rien qui ne soit dans les passages. Mets en gras (**…**) les notions clés.`;
  onEtape && onEtape("Claude rédige la leçon");
  const lec = await avecDelai(S.sample.json(`Tu transformes un chapitre de livre de radiologie en leçon illustrée.
${regles}
Chapitre : « ${c ? c.t : "Chapitre " + src.ch} » (${b.court}).
Réponds uniquement par {"title":"…","goals":["3 à 4 objectifs"],"essentials":["6 à 8 points essentiels"],"intro":"2 à 3 phrases","lesson":[{"h":"titre de section","p":["2 à 3 paragraphes"],"key":"la phrase à retenir","check":{"q":"question de vérification","a":"réponse"},"figs":[{"img":"identifiant exact d'une figure de la liste","cap":"légende courte en français"}]}]}
Écris 6 à 8 sections, chacune avec 0 à 2 figures choisies uniquement dans la liste.

FIGURES DU CHAPITRE
${lfig}

PASSAGES
${texte}`, { modelTier: "complex", cache: false }), 180000);
  if (!lec || !Array.isArray(lec.lesson) || !lec.lesson.length) throw { message: "Claude n'a pas renvoyé de leçon exploitable." };
  onEtape && onEtape("Claude rédige le quiz");
  const qz = await avecDelai(S.sample.json(`Tu écris le quiz d'une leçon de radiologie, à partir des passages du livre.
${regles}
Écris 10 QCM : énoncé clinique ou sémiologique, 4 propositions plausibles, une seule bonne réponse, une explication de 2 à 3 phrases, la page du livre. Quand une figure de la liste illustre la question, mets son identifiant exact dans "img" et décris le cas sans donner la réponse ; sinon "img":"".
Réponds uniquement par {"quiz":[{"q":"…","img":"","options":["…","…","…","…"],"answer":0,"explain":"…","ref":"p. …"}]}

FIGURES DU CHAPITRE
${lfig}

PASSAGES
${texte.slice(0, 45000)}`, { modelTier: "default", cache: false }), 150000);
  const ids = new Set(figs.map((g) => g.id));
  const lesson = lec.lesson.map((s) => ({ h: String(s.h || ""), p: (Array.isArray(s.p) ? s.p : [s.p]).filter(Boolean).map(String), key: s.key || "", check: s.check && s.check.q ? s.check : undefined,
    figs: (s.figs || []).filter((f) => f && ids.has(f.img)).map((f) => ({ img: f.img, cap: f.cap || "" })) }));
  const quiz = ((qz && qz.quiz) || []).filter((q) => q && Array.isArray(q.options) && q.options.length >= 2 && Number.isInteger(q.answer))
    .map((q, k) => ({ q: q.q, img: ids.has(q.img) ? q.img : "", options: q.options, answer: q.answer, explain: q.explain || "", ref: q.ref || "", qn: k }));
  const pg = [...pages].filter((x) => x > 0).sort((a, b) => a - b);
  const m = { id: mid, title: lec.title || (c ? c.t : ""), chapter: `Chapitre ${src.ch}`, pages: pg.length ? `${pg[0]}–${pg[pg.length - 1]}` : "",
    goals: lec.goals || [], essentials: lec.essentials || [], intro: lec.intro || "", lesson, cards: [], quiz, src, genere: { at: Date.now(), par: S.uid || null } };
  m.subs = decouperEtapes(m);
  onEtape && onEtape("Enregistrement");
  await S.db.doc("modules_generes/" + mid).set(JSON.parse(JSON.stringify(m)));
  return m;
}
async function chargerModulesGeneres() {
  try { const snap = await S.db.collection("modules_generes").get(); return snap.docs.map((d) => ({ id: d.id, ...d.data() })); } catch { return []; }
}

/* QCM d'images tirés de Top 3 MSK (banque de cas) */
async function genQcmTop3() {
  const b = S.manifest && S.bookById.get("top3-msk"); if (!b || !S.sample) return [];
  {
    const chs = b.chapitres.map((c) => c.n).sort(() => Math.random() - 0.5).slice(0, 3);
    const figs = (await Promise.all(chs.map((ch) => figsChapitre(b, ch)))).flat().filter((g) => g.il || g.iv).sort(() => Math.random() - 0.5).slice(0, 5);
    const r = await avecDelai(S.sample.json(`Tu écris des QCM d'imagerie à partir de cas d'un livre de diagnostic différentiel (Top 3 Differentials in Musculoskeletal Imaging).
Pour chaque cas ci-dessous, écris un QCM en français : un court énoncé clinique et d'imagerie qui ne donne pas la réponse, 4 propositions (le diagnostic retenu, deux autres diagnostics du « top 3 » et un distracteur plausible), une seule bonne réponse, une explication de 2 à 3 phrases fondée sur la légende. Développe chaque acronyme entre parenthèses à sa première occurrence.
Réponds uniquement par {"qcm":[{"fid":"identifiant","question":"…","options":["…","…","…","…"],"reponse":0,"explication":"…"}]}

${figs.map((g) => `${g.id} : ${g.capo || g.cap}`).join("\n")}`, { modelTier: "default", cache: false }), 120000);
    return JSON.parse(JSON.stringify((r && r.qcm) || [])).filter((x) => x && Array.isArray(x.options) && x.options.length >= 2 && Number.isInteger(x.reponse));
  }
}

window.OUTILS_IMG = (id) => figImage(id, null, true).catch(() => null);
window.OUTILS_GEN = { genererModule, chargerModulesGeneres, pret: () => !!(S.db) };
