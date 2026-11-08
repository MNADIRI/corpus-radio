/* ================= corpus : magasin indexé (base db de l'artefact) =================
   Rien n'est chargé en bloc. Au démarrage : corpus/manifeste et la liste d'entités du domaine.
   Recherche : seuls les seaux d'index des termes demandés (ix/<n>, ≤ 60 Ko chacun), puis les blocs
   de 16 passages retenus (pb/<livre>-<bloc>). Figures : fm/<livre>-<chapitre>. Images : assets. */
const DELAI = 10000;
function avecDelai(p, ms = DELAI) { let t; return Promise.race([p, new Promise((_, r) => { t = setTimeout(() => r({ code: "timeout" }), ms); })]).finally(() => clearTimeout(t)); }
const docCache = new Map();
S.lus = { docs: 0, octets: 0 };
/* Deux magasins : la base db pour les petites cartes (corpus/…, im/…), assets pour le contenu du corpus,
   en fichiers JSON immuables lus par identifiant et mis en cache par le navigateur. */
function lireDb(path) {
  if (!docCache.has(path)) {
    const p = avecDelai(S.db.doc(path).get()).then((d) => { S.lus.docs++; return d.exists ? d.data() : null; });
    p.catch(() => docCache.delete(path)); docCache.set(path, p);
  }
  return docCache.get(path);
}
/* Corpus : lu à distance dans le dépôt privé GitHub corpus-radio via le connecteur « GitHub »,
   comme PubMed. Un appel = un petit fichier de index/artefact/ (≤ 180 Ko) ; rien n'est stocké dans l'artefact. */
const DEPOT = { owner: "MNADIRI", repo: "corpus-radio", base: "index/artefact/" };
S.gh = null;
function blocRessource(res) {
  for (const b of (res && res.content) || []) if (b && b.resource) return b.resource;
  return null;
}
async function lireGitHub(path) {
  for (let k = 0; ; k++) {
    try {
      const res = await avecDelai(S.mcp.callTool("GitHub", "get_file_contents", { owner: DEPOT.owner, repo: DEPOT.repo, path }), 15000);
      const r = blocRessource(res); if (!r) throw { code: "vide", message: path };
      S.lus.docs++; S.lus.octets += (r.text || r.blob || "").length;
      return r;
    } catch (e) { if (k < 2 && e && (e.code === "rate_limited" || e.code === "upstream_error" || e.code === "timeout")) { await new Promise((r) => setTimeout(r, 900 * (k + 1))); continue; } throw e; }
  }
}
function cheminDistant(path) {
  if (path === "sommaire") return DEPOT.base + "sommaire.json";
  const i = path.indexOf("/"), pre = path.slice(0, i), rest = path.slice(i + 1);
  if (pre === "pb" || pre === "fm") { const j = rest.lastIndexOf("-"); return `${DEPOT.base}${pre}/${rest.slice(0, j)}/${rest.slice(j + 1)}.json`; }
  return `${DEPOT.base}${pre}/${rest}.json`;
}
function lireDoc(path) {
  if (/^(corpus|im)\//.test(path)) return lireDb(path);
  if (!docCache.has(path)) {
    const p = lireGitHub(cheminDistant(path)).then((r) => JSON.parse(r.text));
    p.catch(() => docCache.delete(path)); docCache.set(path, p);
  }
  return docCache.get(path);
}
S.dom = "tous";
try { const d = localStorage.getItem("rad-dom"); if (d) S.dom = d; } catch {}
S.codeBook = new Map(); S.bookById = new Map();
async function loadCorpusMeta() {
  if (!S.owner || !S.mcp) { S.manifest = null; S.metaErr = S.owner ? "mcp" : null; render(); return; }
  try {
    docCache.delete("sommaire");
    const m = await lireDoc("sommaire");
    S.manifest = m;
    S.books = m.livres.map((b) => ({ ...b }));
    S.codeBook = new Map(m.livres.map((b) => [b.code, b]));
    S.bookById = new Map(m.livres.map((b) => [b.id, b]));
    S.STOPW = new Set(m.mots_vides || []);
    S.textsState = "ready";
  } catch (e) { S.manifest = null; S.metaErr = e && e.code ? e.code : "lecture"; }
  render();
  if (S.manifest) chargerEntites().catch(() => {});
}
function chapitre(b, n) { return (b && b.chapitres.find((c) => c.n === n)) || null; }
function domOk(code, ch) {
  if (S.dom === "tous") return true;
  const b = S.codeBook.get(code); const c = chapitre(b, ch);
  return !!(c ? c.d.includes(S.dom) : b && b.domaines.includes(S.dom));
}
function fnv(s) { let h = 0x811c9dc5; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; } return h >>> 0; }
const toksIdx = (s) => String(s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().split(/[^a-z0-9]+/).filter((w) => w.length > 1 && !(S.STOPW || STOP).has(w));

/* passages */
function versAncien(b, x) { const c = chapitre(b, x.ch); return { b: b.id, ch: x.ch, ct: c ? c.t : "", id: x.id, pg: x.pg || [], sec: x.sec || "", ss: x.ss || "", t: x.t, f: x.f || [], e: x.e || [] }; }
async function lirePassagesParCle(cles) {
  const blocs = new Map();
  for (const k of cles) { const [c, n] = k.split(":").map(Number); const b = S.codeBook.get(c); if (!b) continue; const path = `pb/${b.id}-${Math.floor((n - 1) / (S.manifest.bloc || 16))}`; if (!blocs.has(path)) blocs.set(path, b); }
  const docs = await Promise.all([...blocs.keys()].map((p) => lireDoc(p).catch(() => null)));
  const out = new Map();
  [...blocs.entries()].forEach(([path, b], i) => { for (const x of (docs[i] && docs[i].p) || []) out.set(b.code + ":" + Number(x.id.split(":p")[1]), versAncien(b, x)); });
  return out;
}
async function lirePassage(id) {
  const [lid, pn] = String(id).split(":p"); const b = S.bookById.get(lid); if (!b || !pn) return null;
  const m = await lirePassagesParCle([b.code + ":" + Number(pn)]); return m.get(b.code + ":" + Number(pn)) || null;
}
async function searchTexts(terms, k) {
  if (!S.manifest) return [];
  const qs = [...new Set(terms.flatMap(toksIdx))].slice(0, 30);
  const phrases = [...new Set(terms.map(norm).filter((t) => t.length > 3))];
  const { n, N, avgdl } = S.manifest.ix;
  const seaux = [...new Set(qs.map((w) => fnv(w) % n))];
  const docs = await Promise.all(seaux.map((b) => lireDoc("ix/" + b).catch(() => null)));
  const parSeau = new Map(seaux.map((b, i) => [b, docs[i]]));
  const score = new Map();
  for (const w of qs) {
    const d = parSeau.get(fnv(w) % n), post = d && d.t[w]; if (!post) continue;
    const df = (d.df && d.df[w]) || post.length, idf = Math.log(1 + (N - df + 0.5) / (df + 0.5));
    for (const [c, num, ch, tf, len] of post) { if (!domOk(c, ch)) continue; const key = c + ":" + num; score.set(key, (score.get(key) || 0) + idf * (tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * len / avgdl))); }
  }
  const top = [...score].sort((a, b) => b[1] - a[1]).slice(0, Math.max(18, k * 2));
  const ps = await lirePassagesParCle(top.map((x) => x[0]));
  const out = [];
  for (let [key, s] of top) {
    const p = ps.get(key); if (!p) continue;
    const nn = norm(p.t), ss = norm(p.sec + " " + p.ct);
    for (const ph of phrases) { if (ss.includes(ph)) s += 10; else if (nn.includes(ph)) s += 5; }
    out.push({ score: s, p, window: windowFor({ p, n: nn }, phrases, qs) });
  }
  out.sort((a, b) => b.score - a.score);
  return out.slice(0, k);
}
function windowFor(d, phrases, qs, size = 3200) {
  const t = d.p.t; if (t.length <= size) return t;
  let at = -1;
  for (const ph of phrases) { at = d.n.indexOf(ph); if (at >= 0) break; }
  if (at < 0) for (const w of qs) { at = d.n.indexOf(w); if (at >= 0) break; }
  const start = Math.max(0, Math.min(t.length - size, (at < 0 ? 0 : at) - 700));
  return (start > 0 ? "… " : "") + t.slice(start, start + size) + (start + size < t.length ? " …" : "");
}

/* figures */
function figAncien(b, ch, g) {
  const c = chapitre(b, ch);
  return { b: b.id, ch, ct: c ? c.t : "", id: g.id, fig: g.n, pa: g.pa || "", pn: g.pn || [], pg: g.pg, pp: g.pp,
    cap: g.capfr || g.cap || "", capo: g.cap || "", m: g.m || [], r: g.r, d: g.d || [], e: g.e || [], role: g.role, iv: g.iv, il: g.il };
}
async function figsChapitre(b, ch) {
  const d = await lireDoc(`fm/${b.id}-${ch}`).catch(() => null);
  const out = ((d && d.figs) || []).map((g) => figAncien(b, ch, g));
  for (const f of out) S.figById.set(f.id, f);
  return out;
}
async function figsParId(ids) {
  const need = ids.filter((id) => !S.figById.has(id)), parLivre = new Map();
  for (const id of need) { const lid = id.split(":")[0]; if (!parLivre.has(lid)) parLivre.set(lid, []); parLivre.get(lid).push(id); }
  await Promise.all([...parLivre.entries()].map(async ([lid, lst]) => {
    const b = S.bookById.get(lid); if (!b) return;
    const fx = await lireDoc("fx/" + lid).catch(() => null); if (!fx) return;
    await Promise.all([...new Set(lst.map((id) => fx[id] && fx[id][0]).filter((x) => x != null))].map((ch) => figsChapitre(b, ch)));
  }));
  return ids.map((id) => S.figById.get(id)).filter(Boolean);
}
async function searchFigures(terms, k) {
  if (!S.manifest || !S.manifest.lx) return [];
  const qs = [...new Set(terms.flatMap(toksIdx))].slice(0, 20), phrases = [...new Set(terms.map(norm).filter((t) => t.length > 3))];
  const { n, N, avgdl } = S.manifest.lx;
  const seaux = [...new Set(qs.map((w) => fnv(w) % n))];
  const docs = await Promise.all(seaux.map((b) => lireDoc("lx/" + b).catch(() => null)));
  const parSeau = new Map(seaux.map((b, i) => [b, docs[i]]));
  const score = new Map();
  for (const w of qs) {
    const d = parSeau.get(fnv(w) % n), post = d && d.t[w]; if (!post) continue;
    const df = (d.df && d.df[w]) || post.length, idf = Math.log(1 + (N - df + 0.5) / (df + 0.5));
    for (const [c, ch, rang, tf, len] of post) { if (!domOk(c, ch)) continue; const key = c + ":" + ch + ":" + rang; score.set(key, (score.get(key) || 0) + idf * (tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * len / avgdl))); }
  }
  const top = [...score].sort((a, b) => b[1] - a[1]).slice(0, k * 2);
  const chs = [...new Set(top.map(([key]) => key.split(":").slice(0, 2).join(":")))];
  await Promise.all(chs.map((x) => { const [c, ch] = x.split(":").map(Number); return figsChapitre(S.codeBook.get(c), ch); }));
  const out = [];
  for (const [key, s0] of top) {
    const [c, ch, rang] = key.split(":").map(Number); const b = S.codeBook.get(c);
    const d = docCache.has(`fm/${b.id}-${ch}`) ? await docCache.get(`fm/${b.id}-${ch}`) : null;
    const g = d && d.figs[rang]; if (!g) continue;
    const f = S.figById.get(g.id); let s = s0; const cn = norm(f.cap);
    for (const ph of phrases) if (cn.includes(ph)) s += 6;
    out.push([s, f]);
  }
  out.sort((a, b) => b[0] - a[0]);
  return out.slice(0, k).map((x) => x[1]);
}
async function figsCitedIn(passages, k) {
  const ids = [...new Set(passages.flatMap((p) => p.f || []))].slice(0, k);
  return figsParId(ids);
}
function mergeFigs(...lists) { const seen = new Set(), out = []; for (const l of lists) for (const f of l) if (!seen.has(f.id)) { seen.add(f.id); out.push(f); } return out; }
const ficheImgCache = new Map(), imgSrc = new Map(), blobUrls = new Map();
async function figImage(id, slug, full) {
  const aid = slug && S.fiches.get(slug)?.imgAssets?.[id];
  if (aid) { const u = "/_blob/" + aid; imgSrc.set(id, u); return u; }
  if (slug) {
    if (!ficheImgCache.has(slug)) ficheImgCache.set(slug, S.db.doc("fiche_img/" + slug).get().then((d) => (d.exists ? d.data().imgs || {} : {})).catch(() => ({})));
    const m = await ficheImgCache.get(slug); if (m[id]) { imgSrc.set(id, m[id]); return m[id]; }
  }
  if (!S.owner || !S.manifest) return null;
  const f = S.figById.get(id) || (await figsParId([id]))[0]; if (!f) return null;
  const chemin = full ? (f.il || f.iv) : (f.iv || f.il); if (!chemin) return null;
  if (!blobUrls.has(chemin)) {
    const p = lireGitHub(chemin).then((r) => { const bin = atob(r.blob), u8 = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i); return URL.createObjectURL(new Blob([u8], { type: r.mimeType || "image/webp" })); });
    p.catch(() => blobUrls.delete(chemin)); blobUrls.set(chemin, p);
  }
  const src = await blobUrls.get(chemin);
  if (src) imgSrc.set(id, src);
  return src;
}
async function blobDe(src) { if (src.startsWith("data:")) return dataUrlBlob(src); const r = await fetch(src); return r.blob(); }

/* entités (Bibliothèque) */
S.ent = new Map(); S.entState = "idle";
async function chargerEntites() {
  if (!S.manifest || !S.manifest.entites) return;
  const doms = S.dom === "tous" ? Object.keys(S.manifest.entites.docs) : [S.dom];
  const paths = doms.flatMap((d) => Array.from({ length: S.manifest.entites.docs[d] || 0 }, (_, k) => `ent/${d}-${k}`));
  if (paths.every((p) => docCache.has(p))) { S.entState = "ready"; render(); return; }
  S.entState = "loading"; render();
  try {
    const docs = await Promise.all(paths.map((p) => lireDoc(p)));
    for (const d of docs) for (const e of (d && d.e) || []) S.ent.set(e.i, e);
    S.entState = "ready";
  } catch { S.entState = "error"; }
  render();
}
function entitesVisibles() { return [...S.ent.values()].filter((e) => S.dom === "tous" || e.d.includes(S.dom)); }
async function detailEntite(id) { const e = S.ent.get(id); if (!e) return null; const d = await lireDoc("ed/" + e.k); return d && d.d ? d.d[id] : null; }
