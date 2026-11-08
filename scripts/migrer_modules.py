#!/usr/bin/env python3
"""Migration unique des 36 modules de « Learning Radiology » vers apprentissage/.

Usage : .venv/bin/python scripts/migrer_modules.py --data learning-DATA.json --images <dossier b/>

Chaque clé d'image de l'ancien format (c01/f1.16, m01/p019_0_0_0_74_55, m01/s014_fig1…) est remplacée
par l'identifiant de figure du corpus :
  1. renvoi explicite au numéro de figure (c01/f1.16 → cotten-t1:fig1.16, panneau choisi par hash) ;
  2. sinon, comparaison par hash perceptuel avec les figures du livre situées dans les pages du module.
Les images non rattachées sont listées dans le module (images_non_rattachees) et dans un rapport.
"""
import argparse
import base64
import io
import json
import re
from collections import defaultdict

import cv2
import imagehash
import numpy as np
from PIL import Image

from commun import RACINE, ecrire_json, lire_jsonl

LIVRES = {"cotten": "cotten-t1", "laredo": "laredo-t4"}
SEUIL = 14
SEUIL_CORRELATION = 0.65


def correlation(a, b):
    """Meilleure corrélation normalisée entre deux images, l'une cherchée dans l'autre à plusieurs échelles."""
    A = np.array(a.convert("L"))
    B = np.array(b.convert("L"))
    best = -1.0
    for petit, grand in ((A, B), (B, A)):
        G = cv2.resize(grand, (400, max(20, int(400 * grand.shape[0] / grand.shape[1]))), interpolation=cv2.INTER_AREA)
        for f in np.geomspace(0.3, 1.0, 12):
            w = int(G.shape[1] * f)
            h = int(petit.shape[0] * w / petit.shape[1])
            if w < 20 or h < 20 or h > G.shape[0]:
                continue
            t = cv2.resize(petit, (w, h), interpolation=cv2.INTER_AREA)
            best = max(best, float(cv2.minMaxLoc(cv2.matchTemplate(G, t, cv2.TM_CCOEFF_NORMED))[1]))
    return best


def hashes(im):
    im = im.convert("RGB")
    return imagehash.phash(im), imagehash.dhash(im)


def distance(a, b):
    return min(a[0] - b[0], a[1] - b[1] + 2)


def pages_num(txt):
    nums = [int(x) for x in re.findall(r"\d+", txt or "")]
    return (min(nums), max(nums)) if nums else (None, None)


def texte_md(p):
    return "\n\n".join(p) if isinstance(p, list) else (p or "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--images", required=True)
    a = ap.parse_args()
    DATA = json.load(open(a.data))

    rapport = {"modules": 0, "images": 0, "rattachees": 0, "non_rattachees": []}
    for b in DATA["books"]:
        livre = LIVRES[b["id"]]
        L = json.loads((RACINE / "livres" / livre / "livre.json").read_text())
        figures = [g for f in sorted((RACINE / "livres" / livre / "figures").glob("*.jsonl")) for g in lire_jsonl(f)]
        par_numero = defaultdict(list)
        for g in figures:
            par_numero[g["numero"]].append(g)
        cache_h = {}

        def h_fig(g):
            if g["id"] not in cache_h:
                cache_h[g["id"]] = hashes(Image.open(RACINE / g["image"]["vignette"])) if g.get("image") else None
            return cache_h[g["id"]]

        for m in b["modules"]:
            rapport["modules"] += 1
            bundle = json.load(open(f"{a.images}/{m['id']}.json"))
            p0, p1 = pages_num(m.get("pages"))
            chapitres = [c for c in L["chapitres"] if c["pages"]["debut"] and p0 and
                         int(c["pages"]["debut"]) <= (p1 or p0) and int(c["pages"]["fin"]) >= p0]
            chapitre = chapitres[0]["n"] if chapitres else None
            candidats = [g for g in figures if g.get("page") and str(g["page"]).isdigit() and p0
                         and p0 - 3 <= int(g["page"]) <= (p1 or p0) + 3]
            non_rattachees = []
            correspondances = {}

            def rattacher(cle):
                if cle in correspondances:
                    return correspondances[cle]
                rapport["images"] += 1
                uri = bundle.get(cle)
                h = hashes(Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1])))) if uri else None
                choix = None
                mnum = re.search(r"/f(\d+\.\d+)", cle)
                if mnum and par_numero.get(mnum.group(1)):
                    groupe = par_numero[mnum.group(1)]
                    if h and len(groupe) > 1:
                        d, g = min(((distance(h, h_fig(g)), g) for g in groupe if h_fig(g)), key=lambda x: x[0])
                        choix = g["id"]
                    else:
                        choix = groupe[0]["id"]
                elif h:
                    scores = [(distance(h, h_fig(g)), g["id"]) for g in candidats if h_fig(g)]
                    if scores:
                        d, fid = min(scores)
                        if d <= SEUIL:
                            choix = fid
                    mp = re.search(r"/[ps](\d{3})", cle)
                    if not choix and mp and uri:
                        n = int(mp.group(1))
                        im = Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1])))
                        proches = [g for g in figures if g.get("image") and n - 1 <= g["page_pdf"] <= n + 1]
                        sc = [(correlation(im, Image.open(RACINE / g["image"]["vignette"])), g["id"]) for g in proches]
                        if sc and max(sc)[0] >= SEUIL_CORRELATION:
                            choix = max(sc)[1]
                correspondances[cle] = choix
                if choix:
                    rapport["rattachees"] += 1
                else:
                    non_rattachees.append(cle)
                    rapport["non_rattachees"].append({"module": m["id"], "cle": cle, "image_disponible": bool(uri)})
                return choix

            sections = []
            for s in m.get("lesson", []):
                figs = [rattacher(f["img"]) for f in s.get("figs", []) if f.get("img")]
                sections.append({
                    "titre": s.get("h", ""), "texte": texte_md(s.get("p")),
                    "figures": [x for x in figs if x],
                    "legendes": [f.get("cap") or f.get("caption") or "" for f in s.get("figs", []) if f.get("img") and correspondances.get(f["img"])],
                    "cle": s.get("key"), "piege": s.get("trap") or s.get("pitfall"), "pourquoi": s.get("why"),
                    "verification": s.get("check"),
                })
            quiz = []
            for q in m.get("quiz", []):
                quiz.append({
                    "question": q["q"], "figure": rattacher(q["img"]) if q.get("img") else None,
                    "options": q["options"], "reponse": q["answer"], "explication": q.get("explain", ""),
                    "page": q.get("ref"), "image_origine": q.get("img"),
                })
            module = {
                "id": f"{livre}:{m['id']}", "domaine": L["domaines"]["principal"], "livre": livre,
                "chapitre": chapitre if chapitre is not None else m.get("chapter"),
                "chapitre_libelle": m.get("chapter"), "titre": m["title"], "pages": m.get("pages"),
                "objectifs": m.get("goals", []), "essentiels": m.get("essentials", []),
                "introduction": m.get("intro"), "sections": sections,
                "cartes": [{"recto": c.get("q") or c.get("front", ""), "verso": c.get("a") or c.get("back", ""),
                            "source": c.get("ref")} for c in m.get("cards", [])],
                "quiz": quiz, "sous_parties": m.get("subs"), "ancien_id": m["id"],
                "images_non_rattachees": sorted(set(non_rattachees)),
            }
            nom = f"ch{chapitre:02d}-{m['id']}.json" if isinstance(chapitre, int) else f"{m['id']}.json"
            ecrire_json(RACINE / "apprentissage" / module["domaine"] / livre / nom, module)
    ecrire_json(RACINE / "_travail" / "modules-non-rattachees.json", rapport)
    print(f"Modules : {rapport['modules']} · images : {rapport['images']} · rattachées : {rapport['rattachees']} · "
          f"non rattachées : {len(rapport['non_rattachees'])}")


if __name__ == "__main__":
    main()
