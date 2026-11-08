#!/usr/bin/env python3
"""Prépare le paquet d'import de l'application « Radiologie ».

Usage : .venv/bin/python scripts/paquet_artefact.py [--livres id1 id2 …] [--sortie _publication]

Le paquet est publié temporairement comme fichiers de l'artefact (import/…). Le bouton « Importer »
de l'application le recopie dans la base db de l'artefact (index, passages, figures, entités) et dans
assets (images), puis Claude Code retire les fichiers. Le stockage n'a donc pas de plafond lié au
nombre de livres : seule la taille d'un paquet (un livre) est limitée.

Organisation dans la base (lue à la demande par l'application) :
  corpus/manifeste            livres, chapitres et domaines, paramètres des index, mots vides
  ix/<n>  lx/<n>              index BM25 des passages (ix) et des légendes (lx), découpés par hachage
                              FNV-1a du terme ; postings [livre, numéro, chapitre, tf, longueur]
  pb/<livre>-<bloc>           passages par blocs de 16 (bloc = (numéro-1) // 16)
  fm/<livre>-<chapitre>       figures d'un chapitre (métadonnées + identifiants d'images assets)
  fx/<livre>                  figure → [chapitre, rang]
  ent/<domaine>-<k>           liste compacte des entités ; ed/<k> détail (passages, figures, liens)
L'index est toujours reconstruit sur tout le corpus ; les passages, figures et images seulement pour
les livres demandés.
"""
import argparse
import base64
import json
import math
import shutil
from collections import Counter, defaultdict

from commun import MOTS_VIDES, RACINE, ecrire_json, lire_jsonl, normaliser

BLOC = 16
MAX_SEAU = 60_000          # octets visés par seau d'index
MAX_POSTINGS = 1500
MAX_FICHIER = 12_000_000   # découpe des gros fichiers JSON publiés
MAX_BIN = 14_000_000
ENT_PAR_DOC = 400
DETAIL_PAR_DOC = 40


def fnv1a(s):
    h = 0x811C9DC5
    for b in s.encode("utf-8"):
        h ^= b
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def codes_livres(livres):
    f = RACINE / "catalogue" / "codes-artefact.json"
    codes = json.loads(f.read_text()) if f.exists() else {}
    for l in livres:
        if l not in codes:
            codes[l] = max(codes.values(), default=-1) + 1
    ecrire_json(f, codes)
    return codes


def seaux(postings, df_reel):
    taille = sum(len(t) + 6 + 16 * len(p) for t, p in postings.items())
    n = max(1, math.ceil(taille / MAX_SEAU))
    out = [{"t": {}, "df": {}} for _ in range(n)]
    for t, p in postings.items():
        s = out[fnv1a(t) % n]
        s["t"][t] = p
        if t in df_reel:
            s["df"][t] = df_reel[t]
    return n, out


def plafonner(postings):
    df_reel = {}
    for t, lst in postings.items():
        if len(lst) > MAX_POSTINGS:
            df_reel[t] = len(lst)
            lst.sort(key=lambda x: -x[3] / x[4])
            del lst[MAX_POSTINGS:]
    return df_reel


def ecrire_decoupe(base, nom, items):
    """Écrit items (liste) en un ou plusieurs fichiers JSON de taille bornée ; renvoie la liste des noms."""
    noms, cur, taille = [], [], 0
    def vider():
        nonlocal cur, taille
        n = f"{nom}-{len(noms)}.json"
        ecrire_json(base / n, cur, compact=True)
        noms.append(n)
        cur, taille = [], 0
    for it in items:
        s = len(json.dumps(it, ensure_ascii=False))
        if cur and taille + s > MAX_FICHIER:
            vider()
        cur.append(it)
        taille += s
    if cur or not noms:
        vider()
    return noms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--livres", nargs="*", help="livres dont on publie passages, figures et images (défaut : tous)")
    ap.add_argument("--sortie", default="_publication")
    a = ap.parse_args()
    sortie = RACINE / a.sortie / "import"
    shutil.rmtree(sortie, ignore_errors=True)
    sortie.mkdir(parents=True)

    livres = [json.loads(f.read_text()) for f in sorted((RACINE / "livres").glob("*/livre.json"))]
    livres = [L for L in livres if not L.get("remplace_par")]
    codes = codes_livres([L["id"] for L in livres])
    a_publier = set(a.livres or [L["id"] for L in livres])

    ix, lx = defaultdict(list), defaultdict(list)
    lg_p, lg_f = [], []
    man_livres = []
    for L in livres:
        lid, code = L["id"], codes[L["id"]]
        dom_ch = {c["n"]: c["domaines"] for c in L["chapitres"]}
        passages = [p for f in sorted((RACINE / "livres" / lid / "passages").glob("*.jsonl")) for p in lire_jsonl(f)]
        figures = [g for f in sorted((RACINE / "livres" / lid / "figures").glob("*.jsonl")) for g in lire_jsonl(f)]
        for p in passages:
            num = int(p["id"].rsplit(":p", 1)[1])
            termes = normaliser(" ".join(filter(None, [p.get("section"), p.get("sous_section"), p["texte"]])))
            if termes:
                lg_p.append(len(termes))
                for t, n in Counter(termes).items():
                    ix[t].append([code, num, p["chapitre"], n, len(termes)])
        par_ch = defaultdict(list)
        for g in figures:
            par_ch[g["chapitre"]].append(g)
        fx = {}
        for ch, gs in par_ch.items():
            for rang, g in enumerate(gs):
                fx[g["id"]] = [ch, rang]
                texte = " ".join(filter(None, [g["legende"], g.get("legende_fr") if g.get("legende_fr") != g["legende"] else None]))
                termes = normaliser(texte)
                if termes:
                    lg_f.append(len(termes))
                    for t, n in Counter(termes).items():
                        lx[t].append([code, ch, rang, n, len(termes)])
        entree = {
            "id": lid, "code": code, "titre": L["titre"], "court": L.get("titre_court", lid), "langue": L["langue"],
            "auteurs": L["auteurs"], "annee": L.get("annee"), "domaine": L["domaines"]["principal"],
            "domaines": [L["domaines"]["principal"], *L["domaines"]["secondaires"]],
            "chapitres": [{"n": c["n"], "t": c["titre"], "d": c["domaines"], "p": [c["pages"]["debut"], c["pages"]["fin"]]}
                          for c in L["chapitres"]],
            "passages": len(passages), "figures": len(figures), "blocs": math.ceil(len(passages) / BLOC),
        }
        man_livres.append(entree)
        if lid not in a_publier:
            continue

        # Paquet du livre : passages, figures, images
        base = sortie / lid
        compacts = [{"id": p["id"], "ch": p["chapitre"], "sec": p.get("section"), "ss": p.get("sous_section"),
                     "pg": p.get("pages") or ([p["page"]] if p.get("page") else []), "t": p["texte"],
                     "f": p["figures_citees"], "e": p["entites"]} for p in passages]
        fichiers_p = ecrire_decoupe(base, "passages", compacts)
        chapitres_f = []
        for ch, gs in sorted(par_ch.items()):
            parts, metas, cur, taille = [], [], {}, 0
            def vider():
                nonlocal cur, taille
                nom = f"img-{ch:02d}-{len(parts)}.json"
                ecrire_json(base / nom, cur, compact=True)
                parts.append(nom)
                cur, taille = {}, 0
            for g in gs:
                im = g.get("image") or {}
                ent, pos = {}, {}
                for k, cle in (("v", "vignette"), ("l", "lecture")):
                    if im.get(cle) and (RACINE / im[cle]).exists():
                        ent[k] = base64.b64encode((RACINE / im[cle]).read_bytes()).decode()
                t = sum(len(x) for x in ent.values())
                if cur and taille + t > MAX_FICHIER:
                    vider()
                if ent:
                    cur[g["id"]] = ent
                    taille += t
                    pos = {k: len(parts) for k in ent}
                metas.append({"id": g["id"], "n": g["numero"], "pa": g.get("panneau"), "pn": g.get("panneaux", []),
                              "pg": g.get("page"), "pp": g.get("page_pdf"), "cap": g["legende"], "capfr": g.get("legende_fr"),
                              "m": g["modalites"], "r": g.get("region"), "d": g["domaines"], "e": g["entites"],
                              "role": g.get("role"), "w": im.get("largeur"), "h": im.get("hauteur"),
                              "src": im.get("provenance"), "pos": pos})
            if cur:
                vider()
            ecrire_json(base / f"figures-{ch:02d}.json", {"ch": ch, "parts": parts, "figs": metas}, compact=True)
            chapitres_f.append({"ch": ch, "fichier": f"figures-{ch:02d}.json", "parts": parts, "n": len(gs)})
        ecrire_json(base / "fx.json", fx, compact=True)
        entree["paquet"] = {"passages": fichiers_p, "figures": chapitres_f, "fx": "fx.json"}

    # Index global
    df_ix, df_lx = plafonner(ix), plafonner(lx)
    n_ix, s_ix = seaux(ix, df_ix)
    n_lx, s_lx = seaux(lx, df_lx)
    f_ix = ecrire_decoupe(sortie, "ix", s_ix)
    f_lx = ecrire_decoupe(sortie, "lx", s_lx)

    # Entités
    entites = {}
    for f in sorted((RACINE / "catalogue" / "entites").glob("*.jsonl")):
        for e in lire_jsonl(f):
            entites[e["id"]] = e
    ordre = sorted(entites)
    detail_doc = {eid: i // DETAIL_PAR_DOC for i, eid in enumerate(ordre)}
    details = defaultdict(dict)
    for eid in ordre:
        e = entites[eid]
        details[detail_doc[eid]][eid] = {"p": e["passages"], "f": e["figures"], "l": e["entites_liees"],
                                         "ab": e["abreviations"], "en": e["synonymes_en"], "rp": e.get("remplace_par")}
    par_dom = defaultdict(list)
    for eid in ordre:
        e = entites[eid]
        if e.get("remplace_par"):
            continue
        c = {"i": eid, "n": e["nom_fr"], "s": e["synonymes_fr"] + e["synonymes_en"],
             "a": [x["sigle"] for x in e["abreviations"]], "c": e["categorie"], "r": e["regions"], "d": e["domaines"],
             "np": len(e["passages"]), "nf": len(e["figures"]), "k": detail_doc[eid]}
        for d in e["domaines"]:
            par_dom[d].append(c)
    ent_docs = {}
    for d, lst in par_dom.items():
        ent_docs[d] = math.ceil(len(lst) / ENT_PAR_DOC)
    ecrire_json(sortie / "entites.json", {
        "listes": {f"{d}-{k}": lst[k * ENT_PAR_DOC:(k + 1) * ENT_PAR_DOC] for d, lst in par_dom.items() for k in range(ent_docs[d])},
        "details": {str(k): v for k, v in details.items()},
    }, compact=True)

    tax = json.loads((RACINE / "schema" / "taxonomie.json").read_text())
    version = json.loads((RACINE / "catalogue" / "manifeste.json").read_text())["version_corpus"]
    ecrire_json(sortie / "manifeste.json", {
        "version": version, "bloc": BLOC, "livres": man_livres, "publies": sorted(a_publier),
        "ix": {"n": n_ix, "N": len(lg_p), "avgdl": round(sum(lg_p) / max(1, len(lg_p)), 2), "fichiers": f_ix},
        "lx": {"n": n_lx, "N": len(lg_f), "avgdl": round(sum(lg_f) / max(1, len(lg_f)), 2), "fichiers": f_lx},
        "entites": {"docs": ent_docs, "details": len(details)},
        "mots_vides": sorted(MOTS_VIDES),
        "domaines": tax["domaines"], "regions": tax["regions"], "modalites": tax["modalites"],
        "categories": tax["categories_entite"],
    })
    tot = sum(f.stat().st_size for f in sortie.rglob("*") if f.is_file())
    nb = sum(1 for f in sortie.rglob("*") if f.is_file())
    print(f"Paquet : {nb} fichiers, {tot/1e6:.1f} Mo · index passages {n_ix} seaux, légendes {n_lx} seaux · "
          f"{len(entites)} entités")


if __name__ == "__main__":
    main()
