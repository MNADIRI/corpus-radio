/* ================= Bibliothèque : lecture du livre, chapitre par chapitre =================
   Texte des passages remis en ordre et en forme (sections, paragraphes, listes), figures insérées
   après le premier passage qui les cite, images chargées au défilement. */
function nettoyerTexte(t) {
  return String(t || "").replace(/(\p{Ll})-\s+(\p{Ll})/gu, "$1$2").replace(/\s+/g, " ").trim();
}
function estPlanBrut(t) { return (t.match(/\.\s\.\s\./g) || []).length > 3 || /P\s?L\s?A\s?N\s+D\s?U/.test(t); }
function lienFigures(html) {
  return html.replace(/\b(fig(?:ure)?s?\.?\s*\d+(?:[.\-]\d+)?[a-z]?(?:\s*(?:,|et|à|-)\s*\d*(?:[.\-]\d+)?[a-z]?)*)/gi, '<span class="figref">$1</span>');
}
function blocsTexte(t) {
  const morceaux = nettoyerTexte(t).split(/\s*(?=[■•▪●]\s)/);
  const out = [];
  for (const m of morceaux) {
    if (/^[■•▪●]\s/.test(m)) { out.push({ li: m.replace(/^[■•▪●]\s*/, "") }); continue; }
    const phrases = m.split(/(?<=[.!?…»])\s+(?=[«A-ZÀ-ÖØ-Þ0-9(])/);
    let cur = [], n = 0;
    for (const ph of phrases) { cur.push(ph); n += ph.split(" ").length; if (n > 110) { out.push({ p: cur.join(" ") }); cur = []; n = 0; } }
    if (cur.length) out.push({ p: cur.join(" ") });
  }
  return out;
}
function htmlBlocs(blocs) {
  let h = "", liste = false;
  for (const b of blocs) {
    if (b.li) { if (!liste) { h += "<ul>"; liste = true; } h += `<li>${lienFigures(esc(b.li))}</li>`; }
    else { if (liste) { h += "</ul>"; liste = false; } h += `<p>${lienFigures(esc(b.p))}</p>`; }
  }
  return h + (liste ? "</ul>" : "");
}
function groupeFigure(figs, i0) {
  const f = figs[i0], g = figs.map((x, i) => [x, i]).filter(([x]) => x.fig === f.fig);
  const cap = f.cap || "";
  return `<figure class="fig-l" id="fig-${esc(f.fig.replace(/[^0-9A-Za-z]/g, "-"))}"><div class="fig-pan n${Math.min(g.length, 4)}">${g.map(([x, i]) => `<button class="fig-img" data-lb="${i}" aria-label="Agrandir la figure ${esc(x.fig)}${esc(x.pa || "")}"><img data-limg="${esc(x.id)}" alt="Figure ${esc(x.fig)}${esc(x.pa || "")}">${g.length > 1 && x.pa ? `<span>${esc(x.pa)}</span>` : ""}</button>`).join("")}</div>
    <figcaption><b>Figure ${esc(f.fig)}</b> ${esc(nettoyerTexte(cap.replace(/^fig(?:ure)?\.?\s*[\d.]+\s*/i, "")))}</figcaption></figure>`;
}
async function ouvrirLecture(id, ch) {
  S.bib.livre = id; S.bib.ch = ch; S.entSel = null; S.detail = true;
  S.entView = { type: "lecture", id, ch, state: "loading" }; render();
  try { localStorage.setItem("rad-lecture-" + id, String(ch)); } catch {}
  const b = S.bookById.get(id);
  try {
    const [ps, figs] = await Promise.all([passagesChapitre(id, ch), figsChapitre(b, ch)]);
    if (S.bib.ch !== ch || S.bib.livre !== id) return;
    S.entView = { type: "lecture", id, ch, state: "ok", ps: ps.filter((p) => !estPlanBrut(p.t)), figs };
  } catch (e) { S.entView = { type: "lecture", id, ch, state: "err", err: messageErreur(e) }; }
  render();
  const r = $("right"); if (r) r.scrollIntoView({ block: "start" }); window.scrollTo(0, 0);
}
function lectureHtml(v) {
  const b = S.bookById.get(v.id), c = chapitre(b, v.ch);
  const chs = b.chapitres.filter((x) => S.dom === "tous" || x.d.includes(S.dom)), k = chs.findIndex((x) => x.n === v.ch);
  const prev = chs[k - 1], next = chs[k + 1];
  const tete = `<button class="btn small bback" data-livre="${esc(b.id)}">‹ Sommaire</button>
    <header class="lect-tete"><span class="label">${esc(b.court)} · chapitre ${v.ch}${c && c.p && c.p[0] ? ` · p. ${esc(c.p[0])}–${esc(c.p[1])}` : ""}</span><h1 class="lect-titre">${esc(c ? c.t : "")}</h1></header>`;
  const pied = `<nav class="lect-pied">${prev ? `<button data-livre="${esc(b.id)}" data-lire="${prev.n}">‹ ${esc(prev.t)}</button>` : "<span></span>"}${next ? `<button data-livre="${esc(b.id)}" data-lire="${next.n}">${esc(next.t)} ›</button>` : "<span></span>"}</nav>`;
  if (v.state === "loading") return tete + `<p class="hint">Lecture du chapitre dans l'index…</p>`;
  if (v.state === "err") return tete + `<div class="alert"><b>Lecture impossible</b><span>${esc(v.err)} <button class="btn small" data-livre="${esc(b.id)}" data-lire="${v.ch}">Réessayer</button></span></div>`;
  S.lb = { list: v.figs.map((g) => ({ id: g.id, cap: g.cap, src: `${bookShort(g.b)}, fig. ${g.fig}${g.pa || ""}${g.pg ? `, p. ${g.pg}` : ""}`, dd: "", slug: null, ent: c ? c.t : "" })), i: 0 };
  const idx = new Map(v.figs.map((g, i) => [g.id, i])), placees = new Set();
  let corps = "", secCour = null, sections = [];
  for (const p of v.ps) {
    const sec = p.sec && p.sec !== (c && c.t) ? p.sec : null;
    if (sec && sec !== secCour) { secCour = sec; const ancre = "sec-" + sections.length; sections.push({ ancre, t: sec }); corps += `<h2 class="lect-sec" id="${ancre}">${esc(sec)}</h2>`; }
    if (p.ss) corps += `<h3 class="lect-ss">${esc(p.ss)}</h3>`;
    corps += htmlBlocs(blocsTexte(p.t));
    for (const fid of p.f || []) {
      const i = idx.get(fid); if (i == null) continue;
      const num = v.figs[i].fig; if (placees.has(num)) continue;
      placees.add(num); corps += groupeFigure(v.figs, i);
    }
  }
  const restes = [];
  v.figs.forEach((g, i) => { if (!placees.has(g.fig)) { placees.add(g.fig); restes.push(groupeFigure(v.figs, i)); } });
  if (restes.length) { sections.push({ ancre: "sec-figs", t: "Autres figures du chapitre" }); corps += `<h2 class="lect-sec" id="sec-figs">Autres figures du chapitre</h2>${restes.join("")}`; }
  const toc = sections.length > 1 ? `<details class="lect-toc" ${sections.length <= 12 ? "open" : ""}><summary>Dans ce chapitre · ${sections.length} sections</summary><ol>${sections.map((s) => `<li><button data-goto="${s.ancre}">${esc(s.t)}</button></li>`).join("")}</ol></details>` : "";
  return tete + toc + `<article class="lect">${corps || `<p class="hint">Aucun texte pour ce chapitre.</p>`}</article>` + pied;
}
function tocLivreGauche(b) {
  const lu = (() => { try { return +localStorage.getItem("rad-lecture-" + b.id); } catch { return 0; } })();
  return `<button class="btn small" data-bvue="ouvrages" data-bretour="1">‹ Tous les ouvrages</button>
    <h3 class="grp">${esc(b.court)} · table des matières</h3>
    <ol class="toc-livre">${b.chapitres.filter((c) => S.dom === "tous" || c.d.includes(S.dom)).map((c) => `<li><button class="${S.bib.ch === c.n ? "on" : ""}" data-livre="${esc(b.id)}" data-lire="${c.n}"><span class="n">${c.n}</span><span>${esc(c.t)}</span>${lu === c.n && S.bib.ch !== c.n ? `<span class="hint">reprendre</span>` : ""}</button></li>`).join("")}</ol>`;
}
let obsImages = null;
function observerImages() {
  const r = $("right"); if (!r) return;
  if (!obsImages) obsImages = new IntersectionObserver((es) => {
    for (const e of es) if (e.isIntersecting) { const img = e.target; obsImages.unobserve(img); imageProgressive(img, img.dataset.limg, 1); }
  }, { rootMargin: "600px 0px" });
  const imgs = [...r.querySelectorAll("img[data-limg]:not([src])")];
  imgs.forEach((img, k) => { if (k < 6) imageProgressive(img, img.dataset.limg, 1); else obsImages.observe(img); });
}
