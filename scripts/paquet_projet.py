#!/usr/bin/env python3
"""Prépare les fichiers à déposer dans la Library du Project Claude Code lu par l'application.

Usage : .venv/bin/python scripts/paquet_projet.py [--sortie _projet]

Fichiers produits (noms versionnés, à téléverser tels quels ; l'application prend le sommaire le plus récent) :
  radiologie-sommaire-v<V>.json   petit : livres, chapitres, paramètres BM25, positions (offset, longueur)
  radiologie-index-v<V>.bin       seaux d'index des passages (ix) et des légendes (lx), entités (ent, ed)
  <livre>-v<V>.bin                blocs de 16 passages (pb), figures par chapitre (fm, avec la position
                                  de chaque image), table figure → chapitre (fx), images WebP brutes
L'application lit chaque morceau avec files.read(fichier, {offset, length}) : jamais un fichier entier.
Un livre déjà déposé et inchangé garde son fichier ; seuls le sommaire, l'index et le nouveau livre changent.
"""
import argparse
import hashlib
import json
import math
import shutil
from collections import Counter, defaultdict

from commun import MOTS_VIDES, RACINE, ecrire_json, lire_jsonl, normaliser
from paquet_artefact import BLOC, DETAIL_PAR_DOC, ENT_PAR_DOC, codes_livres, plafonner, seaux


class Pack:
    def __init__(self, chemin):
        self.f = open(chemin, "wb")
        self.pos = 0

    def json(self, obj):
        return self.octets(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    def octets(self, b):
        p = [self.pos, len(b)]
        self.f.write(b)
        self.pos += len(b)
        return p

    def fermer(self):
        self.f.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sortie", default="_projet")
    a = ap.parse_args()
    sortie = RACINE / a.sortie
    shutil.rmtree(sortie, ignore_errors=True)
    sortie.mkdir(parents=True)

    livres = [json.loads(f.read_text()) for f in sorted((RACINE / "livres").glob("*/livre.json"))]
    livres = [L for L in livres if not L.get("remplace_par")]
    codes = codes_livres([L["id"] for L in livres])
    version = json.loads((RACINE / "catalogue" / "manifeste.json").read_text())["version_corpus"].split(".")[0]

    ix, lx, lg_p, lg_f, man_livres = defaultdict(list), defaultdict(list), [], [], []
    for L in livres:
        lid, code = L["id"], codes[L["id"]]
        passages = [p for f in sorted((RACINE / "livres" / lid / "passages").glob("*.jsonl")) for p in lire_jsonl(f)]
        figures = [g for f in sorted((RACINE / "livres" / lid / "figures").glob("*.jsonl")) for g in lire_jsonl(f)]
        empreinte = hashlib.sha1()
        for f in sorted((RACINE / "livres" / lid).rglob("*.json*")):
            empreinte.update(f.read_bytes())
        nom = f"{lid}-v{empreinte.hexdigest()[:8]}.bin"
        pk = Pack(sortie / nom)
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
        pos_pb = {k: pk.json({"p": v}) for k, v in sorted(blocs.items())}
        par_ch = defaultdict(list)
        for g in figures:
            par_ch[g["chapitre"]].append(g)
        fx, pos_fm = {}, {}
        for ch, gs in sorted(par_ch.items()):
            metas = []
            for rang, g in enumerate(gs):
                fx[g["id"]] = [ch, rang]
                im = g.get("image") or {}
                pos = {}
                for k, cle in (("v", "vignette"), ("l", "lecture")):
                    if im.get(cle) and (RACINE / im[cle]).exists():
                        pos[k] = pk.octets((RACINE / im[cle]).read_bytes())
                metas.append({"id": g["id"], "n": g["numero"], "pa": g.get("panneau"), "pn": g.get("panneaux", []),
                              "pg": g.get("page"), "pp": g.get("page_pdf"), "cap": g["legende"], "capfr": g.get("legende_fr"),
                              "m": g["modalites"], "r": g.get("region"), "d": g["domaines"], "e": g["entites"],
                              "role": g.get("role"), "w": im.get("largeur"), "h": im.get("hauteur"), "pos": pos})
                texte = " ".join(filter(None, [g["legende"], g.get("legende_fr") if g.get("legende_fr") != g["legende"] else None]))
                termes = normaliser(texte)
                if termes:
                    lg_f.append(len(termes))
                    for t, n in Counter(termes).items():
                        lx[t].append([code, ch, rang, n, len(termes)])
            pos_fm[ch] = pk.json({"figs": metas})
        pos_fx = pk.json(fx)
        pk.fermer()
        man_livres.append({
            "id": lid, "code": code, "titre": L["titre"], "court": L.get("titre_court", lid), "langue": L["langue"],
            "auteurs": L["auteurs"], "annee": L.get("annee"), "domaine": L["domaines"]["principal"],
            "domaines": [L["domaines"]["principal"], *L["domaines"]["secondaires"]],
            "chapitres": [{"n": c["n"], "t": c["titre"], "d": c["domaines"], "p": [c["pages"]["debut"], c["pages"]["fin"]]} for c in L["chapitres"]],
            "passages": len(passages), "figures": len(figures),
            "pack": {"fichier": nom, "pb": pos_pb, "fm": pos_fm, "fx": pos_fx},
        })

    # Index global et entités
    df_ix, df_lx = plafonner(ix), plafonner(lx)
    n_ix, s_ix = seaux(ix, df_ix)
    n_lx, s_lx = seaux(lx, df_lx)
    nom_index = f"radiologie-index-v{version}.bin"
    pk = Pack(sortie / nom_index)
    pos_ix = [pk.json(s) for s in s_ix]
    pos_lx = [pk.json(s) for s in s_lx]
    entites = {}
    for f in sorted((RACINE / "catalogue" / "entites").glob("*.jsonl")):
        for e in lire_jsonl(f):
            entites[e["id"]] = e
    ordre = sorted(entites)
    k_detail = {eid: i // DETAIL_PAR_DOC for i, eid in enumerate(ordre)}
    details = defaultdict(dict)
    par_dom = defaultdict(list)
    for eid in ordre:
        e = entites[eid]
        details[k_detail[eid]][eid] = {"p": e["passages"], "f": e["figures"], "l": e["entites_liees"],
                                       "ab": e["abreviations"], "en": e["synonymes_en"], "rp": e.get("remplace_par")}
        if not e.get("remplace_par"):
            c = {"i": eid, "n": e["nom_fr"], "s": e["synonymes_fr"] + e["synonymes_en"], "a": [x["sigle"] for x in e["abreviations"]],
                 "c": e["categorie"], "r": e["regions"], "d": e["domaines"], "np": len(e["passages"]), "nf": len(e["figures"]), "k": k_detail[eid]}
            for d in e["domaines"]:
                par_dom[d].append(c)
    pos_ent, docs_ent = {}, {}
    for d, lst in par_dom.items():
        docs_ent[d] = math.ceil(len(lst) / ENT_PAR_DOC)
        for k in range(docs_ent[d]):
            pos_ent[f"{d}-{k}"] = pk.json({"e": lst[k * ENT_PAR_DOC:(k + 1) * ENT_PAR_DOC]})
    pos_ed = {str(k): pk.json({"d": v}) for k, v in details.items()}
    pk.fermer()

    tax = json.loads((RACINE / "schema" / "taxonomie.json").read_text())
    nom_sommaire = f"radiologie-sommaire-v{version}.json"
    ecrire_json(sortie / nom_sommaire, {
        "version": version, "bloc": BLOC, "livres": man_livres,
        "index": {"fichier": nom_index, "ix": pos_ix, "lx": pos_lx, "ent": pos_ent, "ed": pos_ed},
        "ix": {"n": n_ix, "N": len(lg_p), "avgdl": round(sum(lg_p) / max(1, len(lg_p)), 2)},
        "lx": {"n": n_lx, "N": len(lg_f), "avgdl": round(sum(lg_f) / max(1, len(lg_f)), 2)},
        "entites": {"docs": docs_ent},
        "mots_vides": sorted(MOTS_VIDES),
        "domaines": tax["domaines"], "regions": tax["regions"], "modalites": tax["modalites"], "categories": tax["categories_entite"],
    }, compact=True)
    for f in sorted(sortie.iterdir()):
        print(f"{f.name:40s} {f.stat().st_size / 1e6:8.1f} Mo")


if __name__ == "__main__":
    main()
