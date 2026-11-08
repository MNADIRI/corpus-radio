/* ================= Révision unifiée : une seule file, un élément toujours prêt =================
   Sources mélangées : erreurs de QCM et de défis d'Apprentissage (même enregistrement que Learning),
   QCM ratés sur les notes, cas ratés, cas tirés des figures des fiches, QCM générés sur les notes,
   QCM d'images Top 3. L'élément suivant est préparé pendant qu'on répond au courant. */
S.rev = { file: [], pos: 0, construit: false, fait: 0, bons: 0 };
function melanger(a) { for (let i = a.length - 1; i > 0; i--) { const k = Math.floor(Math.random() * (i + 1)); [a[i], a[k]] = [a[k], a[i]]; } return a; }
function construireFile() {
  const LR = window.LR, f = [];
  if (LR) for (const x of LR.dueMissed(null).slice(0, 15)) f.push({ type: "lr", mid: x.m.id, i: x.i, lib: "Erreur d'Apprentissage" });
  for (const q of S.casHist.qcm.slice(-8)) f.push({ type: "qcm", q, lib: "QCM raté sur tes notes", err: true });
  const rates = [...new Set(S.casHist.hist.filter((h) => h.note < 6).map((h) => h.fid))].slice(-6);
  for (const fid of rates) f.push({ type: "cas", fid, origine: "ratés", lib: "Cas à refaire" });
  const figsNotes = [];
  for (const fi of S.fiches.values()) for (const [k, r] of Object.entries(fi.refs || {})) if (k.startsWith("F") && r.id) figsNotes.push(r.id);
  for (const fid of melanger([...new Set(figsNotes)]).slice(0, 3)) f.push({ type: "cas", fid, origine: "notes", lib: "Cas sur tes notes" });
  if ([...S.fiches.values()].some((x) => x.kind === "corpus")) f.push({ type: "gen", gen: "notes", lib: "QCM sur tes notes" });
  if (S.bookById.has("top3-msk")) f.push({ type: "gen", gen: "top3", lib: "QCM d'images Top 3" });
  const lr = f.filter((x) => x.type === "lr"), autres = melanger(f.filter((x) => x.type !== "lr"));
  const file = [];                                   // erreurs d'Apprentissage en tête, puis alternance
  while (lr.length || autres.length) { if (lr.length) file.push(lr.shift()); if (lr.length) file.push(lr.shift()); if (autres.length) file.push(autres.shift()); }
  S.rev = { file, pos: 0, construit: true, fait: 0, bons: 0 };
  preparer(0); preparer(1);
}
function qcmDepuisLR(it) {
  const m = window.LR.modById[it.mid], q = m && m.quiz[it.i]; if (!q) return null;
  return { question: q.q, options: q.options, reponse: q.answer, explication: q.explain || "", lrimg: q.img || "", ref: `${m.chapter || ""}${q.ref ? " · " + q.ref : ""} · ${m.title}` };
}
function preparer(k) {
  const it = S.rev.file[k]; if (!it || it.p) return;
  if (it.type === "lr") { it.pret = qcmDepuisLR(it); it.p = Promise.resolve(); return; }
  if (it.type === "qcm") { it.pret = it.q; it.p = Promise.resolve(); return; }
  if (it.type === "cas") { it.p = preparerCas({ fid: it.fid, origine: it.origine }).then((c) => { it.pret = c; }).catch((e) => { it.err = messageErreur(e); }).finally(render); return; }
  if (it.type === "gen") {
    it.p = (it.gen === "notes" ? genQcmNotes() : genQcmTop3()).then((qs) => {
      const items = qs.map((q) => ({ type: "qcm", q, pret: q, p: Promise.resolve(), lib: it.lib }));
      const pos = S.rev.file.indexOf(it); if (pos >= 0) S.rev.file.splice(pos, 1, ...items);
    }).catch((e) => { it.err = messageErreur(e); }).finally(render);
  }
}
function itemCourant() { return S.rev.file[S.rev.pos]; }
function revSuivant() {
  S.rev.pos++; S.cas = { mode: "revision", etat: "vide" };
  preparer(S.rev.pos); preparer(S.rev.pos + 1);
  const it = itemCourant(); if (it && it.type === "cas" && it.pret) S.cas = { mode: "revision", etat: "question", ...it.pret };
  render(); window.scrollTo(0, 0);
}
function revRepondre(i) {
  const it = itemCourant(); if (!it || it.choix != null) return;
  const q = it.pret; it.choix = i; const ok = i === q.reponse;
  S.rev.fait++; if (ok) S.rev.bons++;
  if (it.type === "lr" && window.LR) window.LR.repondre(it.mid, it.i, i);
  else if (!ok && !it.err) { S.casHist.qcm.push({ ...q, at: Date.now() }); sauverCasHist(); }
  else if (ok && it.err) { S.casHist.qcm = S.casHist.qcm.filter((x) => x.question !== q.question); sauverCasHist(); }
  render();
}
function revContenu() {
  if (!S.rev.construit) construireFile();
  const R = S.rev, it = itemCourant(), total = R.file.length;
  const tete = `<div class="revhead"><span class="label">${it ? esc(it.lib) : "Révision"}</span><span class="hint">${Math.min(R.pos + 1, total)} / ${total}${R.fait ? ` · ${R.bons} / ${R.fait} réussis` : ""}</span>
    <span class="revbar"><i style="width:${total ? Math.round(100 * R.pos / total) : 0}%"></i></span></div>`;
  if (!total) return tete + `<div class="bempty"><h2>Rien à réviser</h2><p>Les erreurs de QCM et de défis d'Apprentissage, les cas ratés et des QCM sur les entités de tes notes apparaîtront ici.</p><button class="btn primary" data-casmode="alea">Faire un cas aléatoire</button></div>`;
  if (!it) return tete + `<div class="bempty"><h2>Révision terminée</h2><p>${R.bons} bonnes réponses sur ${R.fait}. Les éléments ratés reviendront dans une prochaine révision.</p><div class="row"><button class="btn primary" data-revnouv="1">Nouvelle révision</button><button class="btn small" data-casmode="alea">Cas aléatoire</button></div></div>`;
  if (it.err) return tete + `<div class="alert"><b>Élément indisponible</b><span>${esc(it.err)} <button class="btn small" data-rsuiv="1">Passer</button></span></div>`;
  if (!it.pret) { preparer(R.pos); return tete + `<div class="bempty"><h2>Préparation…</h2><p class="hint">${it.type === "cas" ? "Claude construit le cas à partir du livre." : "Claude écrit les questions."}</p></div>`; }
  if (it.type === "cas") { S.cas = { mode: "revision", etat: "question", ...it.pret }; return casContenu(); }
  const q = it.pret, c = it.choix;
  const img = q.lrimg ? `<figure class="casfig"><img data-lrimg="${esc(q.lrimg)}" alt="Image de la question"></figure>` : q.fid ? `<figure class="casfig"><img data-img="${esc(q.fid)}" data-full="1" alt="Image de la question"></figure>` : "";
  return tete + img + `<h2 class="btitle" style="font-size:20px">${esc(q.question)}</h2>
    <div class="qopts">${q.options.map((o, i) => `<button class="qopt${c == null ? "" : i === q.reponse ? " ok" : i === c ? " ko" : ""}" data-rrep="${i}" ${c == null ? "" : "disabled"}>${esc(o)}</button>`).join("")}</div>
    ${c != null ? `<div class="fb ${c === q.reponse ? "ok" : "ko"}"><h3>${c === q.reponse ? "Bonne réponse" : "Réponse attendue : " + esc(q.options[q.reponse] || "")}</h3><p>${esc(q.explication || "")}</p>${q.ref ? `<p class="hint">${esc(q.ref)}</p>` : ""}</div><div class="row"><button class="btn primary" data-rsuiv="1">Élément suivant</button></div>` : ""}`;
}
