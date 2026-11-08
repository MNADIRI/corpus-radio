#!/usr/bin/env python3
"""Construit index/artefact/ : le corpus découpé pour la lecture à distance par l'application
(connecteur GitHub, un fichier par appel, jamais un gros fichier).

Usage : .venv/bin/python scripts/construire_distant.py

  index/artefact/sommaire.json          livres, chapitres, domaines, paramètres BM25, mots vides
  index/artefact/ix/<n>.json            index des passages, seau = FNV-1a(terme) % n ; postings [livre, numéro, chapitre, tf, longueur]
  index/artefact/lx/<n>.json            index des légendes ; postings [livre, chapitre, rang, tf, longueur]
  index/artefact/pb/<livre>/<bloc>.json passages par blocs de 16 (bloc = (numéro - 1) // 16)
  index/artefact/fm/<livre>/<ch>.json   figures du chapitre (avec chemins des images dans images/)
  index/artefact/fx/<livre>.json        figure → [chapitre, rang]
  index/artefact/ent/<dom>-<k>.json     liste compacte des entités ; ed/<k>.json détail
Le dossier est entièrement régénéré à chaque ajout de livre (idempotent).
"""
import json
import math
import shutil
from collections import Counter, defaultdict

from commun import MOTS_VIDES, RACINE, ecrire_json, lire_jsonl, normaliser
from paquet_artefact import BLOC, DETAIL_PAR_DOC, ENT_PAR_DOC, codes_livres, plafonner, seaux

SORTIE = RACINE / "index" / "artefact"


def main():
    shutil.rmtree(SORTIE, ignore_errors=True)
    livres = [json.loads(f.read_text()) for f in sorted((RACINE / "livres").glob("*/livre.json"))]
    livres = [L for L in livres if not L.get("remplace_par")]
    codes = codes_livres([L["id"] for L in livres])
    ix, lx, lg_p, lg_f, man = defaultdict(list), defaultdict(list), [], [], []
    for L in livres:
        lid, code = L["id"], codes[L["id"]]
        passages = [p for f in sorted((RACINE / "livres" / lid / "passages").glob("*.jsonl")) for p in lire_jsonl(f)]
        figures = [g for f in sorted((RACINE / "livres" / lid / "figures").glob("*.jsonl")) for g in lire_jsonl(f)]
        blocs = defaultdict(list)
        for p in passages:
            num = int(p["id"].rsplit(":p", 1)[1])
            blocs[(num - 1) // BLOC].append({"id": p["id"], "ch": p["chapitre"], "sec": p.get("section"), "ss": p.get("sous_section"),
                                             "pg": p.get("pages") or ([p["page"]] if p.get("page") else []), "t": p["texte"],
                                             "f": p["figures_citees"], "e": p["entites"]})
            termes = normaliser(" ".join(filter(None, [p.get("section"), p.get("sous_section"), p["texte"]])))
            if termes:
                lg_p.append(len(termes))
                for t, n in Counter(termes).items():
                    ix[t].append([code, num, p["chapitre"], n, len(termes)])
        for k, v in blocs.items():
            ecrire_json(SORTIE / "pb" / lid / f"{k}.json", {"p": v}, compact=True)
        par_ch = defaultdict(list)
        for g in figures:
            par_ch[g["chapitre"]].append(g)
        fx = {}
        for ch, gs in sorted(par_ch.items()):
            metas = []
            for rang, g in enumerate(gs):
                fx[g["id"]] = [ch, rang]
                im = g.get("image") or {}
                metas.append({"id": g["id"], "n": g["numero"], "pa": g.get("panneau"), "pn": g.get("panneaux", []),
                              "pg": g.get("page"), "pp": g.get("page_pdf"), "cap": g["legende"], "capfr": g.get("legende_fr"),
                              "m": g["modalites"], "r": g.get("region"), "d": g["domaines"], "e": g["entites"], "role": g.get("role"),
                              "w": im.get("largeur"), "h": im.get("hauteur"), "iv": im.get("vignette"), "il": im.get("lecture")})
                texte = " ".join(filter(None, [g["legende"], g.get("legende_fr") if g.get("legende_fr") != g["legende"] else None]))
                termes = normaliser(texte)
                if termes:
                    lg_f.append(len(termes))
                    for t, n in Counter(termes).items():
                        lx[t].append([code, ch, rang, n, len(termes)])
            ecrire_json(SORTIE / "fm" / lid / f"{ch}.json", {"figs": metas}, compact=True)
        ecrire_json(SORTIE / "fx" / f"{lid}.json", fx, compact=True)
        man.append({"id": lid, "code": code, "titre": L["titre"], "court": L.get("titre_court", lid), "langue": L["langue"],
                    "auteurs": L["auteurs"], "annee": L.get("annee"), "domaine": L["domaines"]["principal"],
                    "domaines": [L["domaines"]["principal"], *L["domaines"]["secondaires"]],
                    "chapitres": [{"n": c["n"], "t": c["titre"], "d": c["domaines"], "p": [c["pages"]["debut"], c["pages"]["fin"]]} for c in L["chapitres"]],
                    "passages": len(passages), "figures": len(figures)})

    df_ix, df_lx = plafonner(ix), plafonner(lx)
    n_ix, s_ix = seaux(ix, df_ix)
    n_lx, s_lx = seaux(lx, df_lx)
    for i, s in enumerate(s_ix):
        ecrire_json(SORTIE / "ix" / f"{i}.json", s, compact=True)
    for i, s in enumerate(s_lx):
        ecrire_json(SORTIE / "lx" / f"{i}.json", s, compact=True)

    entites = {}
    for f in sorted((RACINE / "catalogue" / "entites").glob("*.jsonl")):
        for e in lire_jsonl(f):
            entites[e["id"]] = e
    ordre = sorted(entites)
    k_detail = {eid: i // DETAIL_PAR_DOC for i, eid in enumerate(ordre)}
    details, par_dom = defaultdict(dict), defaultdict(list)
    for eid in ordre:
        e = entites[eid]
        details[k_detail[eid]][eid] = {"p": e["passages"], "f": e["figures"], "l": e["entites_liees"],
                                       "ab": e["abreviations"], "en": e["synonymes_en"], "rp": e.get("remplace_par")}
        if not e.get("remplace_par"):
            c = {"i": eid, "n": e["nom_fr"], "s": e["synonymes_fr"] + e["synonymes_en"], "a": [x["sigle"] for x in e["abreviations"]],
                 "c": e["categorie"], "r": e["regions"], "d": e["domaines"], "np": len(e["passages"]), "nf": len(e["figures"]), "k": k_detail[eid]}
            for d in e["domaines"]:
                par_dom[d].append(c)
    docs_ent = {}
    for d, lst in par_dom.items():
        docs_ent[d] = math.ceil(len(lst) / ENT_PAR_DOC)
        for k in range(docs_ent[d]):
            ecrire_json(SORTIE / "ent" / f"{d}-{k}.json", {"e": lst[k * ENT_PAR_DOC:(k + 1) * ENT_PAR_DOC]}, compact=True)
    for k, v in details.items():
        ecrire_json(SORTIE / "ed" / f"{k}.json", {"d": v}, compact=True)

    tax = json.loads((RACINE / "schema" / "taxonomie.json").read_text())
    version = json.loads((RACINE / "catalogue" / "manifeste.json").read_text())["version_corpus"]
    ecrire_json(SORTIE / "sommaire.json", {
        "version": version, "bloc": BLOC, "livres": man,
        "ix": {"n": n_ix, "N": len(lg_p), "avgdl": round(sum(lg_p) / max(1, len(lg_p)), 2)},
        "lx": {"n": n_lx, "N": len(lg_f), "avgdl": round(sum(lg_f) / max(1, len(lg_f)), 2)},
        "entites": {"docs": docs_ent}, "mots_vides": sorted(MOTS_VIDES),
        "domaines": tax["domaines"], "regions": tax["regions"], "modalites": tax["modalites"], "categories": tax["categories_entite"],
    }, compact=True)
    fichiers = [f for f in SORTIE.rglob("*.json")]
    print(f"index/artefact : {len(fichiers)} fichiers, {sum(f.stat().st_size for f in fichiers) / 1e6:.1f} Mo, "
          f"plus gros {max(f.stat().st_size for f in fichiers) / 1e3:.0f} Ko · seaux ix {n_ix}, lx {n_lx}")


if __name__ == "__main__":
    main()
