#!/usr/bin/env python3
"""Migration unique d'un livre depuis l'export de la base de « Notes radiologiques ».

Usage :
  .venv/bin/python scripts/migrer_base.py --livre cotten-t1 --export <dossier export db> \
      --secours <dossier des WebP de la base> [--meta meta.json] [--etape passages|figures|images|tout]

  - passages et légendes repris tels quels (les passages > 400 mots sont redécoupés en fin de phrase,
    sans modifier le texte) ;
  - images ré-extraites du PDF sources/<livre>.pdf : chaque figure est rattachée à l'image intégrée
    de sa page par hash perceptuel avec l'image de la base ; à défaut, l'image de la base sert de secours ;
  - chaque étape est idempotente.
"""
import argparse
import glob
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import imagehash
import pymupdf
from PIL import Image

from commun import (RACINE, decouper, ecrire_json, ecrire_jsonl, exporter_webp, lire_jsonl,
                    modalites_par_regles, nom_image, resoudre_renvois)

SEUIL_HASH = 12


def charger_export(export, livre):
    passages = [p for f in sorted(glob.glob(f"{export}/texts/{livre}-*.json"))
                for p in json.load(open(f))["passages"]]
    figures = [g for f in sorted(glob.glob(f"{export}/figidx/*.json"))
               for g in json.load(open(f))["figs"] if g["b"] == livre]
    manifeste = json.load(open(f"{export}/corpus/manifest.json"))
    meta = next(b for b in manifeste["books"] if b["id"] == livre)
    return passages, figures, meta


def sha256(chemin):
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def etape_figures(livre, figures_db, dossier, domaines_ch):
    """Écrit figures/chNN.jsonl (sans images si absentes) et renvoie l'index numéro → {lettre: id}."""
    groupes = defaultdict(list)
    for g in figures_db:
        groupes[g["fig"]].append(g["pa"] or "")
    anciennes = {}
    for f in (dossier / "figures").glob("*.jsonl"):
        for x in lire_jsonl(f):
            anciennes[x["id"]] = x
    par_ch = defaultdict(list)
    for g in figures_db:
        ancien = anciennes.get(g["id"], {})
        par_ch[g["ch"]].append({
            "id": g["id"], "livre": livre, "chapitre": g["ch"], "numero": g["fig"],
            "panneau": g["pa"] or None, "panneaux": sorted(x for x in groupes[g["fig"]] if x),
            "page": g["pg"] or None, "page_pdf": g["pp"],
            "legende": g["cap"], "legende_fr": ancien.get("legende_fr"),
            "modalites": ancien.get("modalites") or modalites_par_regles(g["cap"]),
            "region": ancien.get("region"), "domaines": ancien.get("domaines") or domaines_ch(g["ch"]),
            "entites": ancien.get("entites") or [], "role": ancien.get("role"),
            "image": ancien.get("image"),
        })
    for ch, lignes in par_ch.items():
        ecrire_jsonl(dossier / "figures" / f"ch{ch:02d}.jsonl", lignes)
    index = defaultdict(dict)
    for g in figures_db:
        index[g["fig"]][g["pa"] or ""] = g["id"]
    return index


def etape_passages(livre, passages_db, index_figs, dossier, langue):
    par_ch, n = defaultdict(list), 0
    stats = {"decoupes": 0, "renvois": 0}
    for p in passages_db:
        morceaux = decouper(p["t"])
        if len(morceaux) > 1:
            stats["decoupes"] += 1
        for k, texte in enumerate(morceaux):
            n += 1
            figs = resoudre_renvois(texte, livre, index_figs)
            stats["renvois"] += len(figs)
            par_ch[p["ch"]].append({
                "id": f"{livre}:p{n:05d}", "livre": livre, "chapitre": p["ch"],
                "section": p.get("sec") or None, "sous_section": p.get("ss") or None,
                "page": (p.get("pg") or [None])[0], "pages": p.get("pg") or [],
                "langue": langue, "texte": texte, "figures_citees": figs, "entites": [],
                "ancien_id": p["id"] if len(morceaux) == 1 else f"{p['id']}#{k}",
            })
    for ch, lignes in par_ch.items():
        ecrire_jsonl(dossier / "passages" / f"ch{ch:02d}.jsonl", lignes)
    return n, stats


def pil_xref(doc, xref):
    pix = pymupdf.Pixmap(doc, xref)
    if pix.alpha:
        pix = pymupdf.Pixmap(pix, 0)
    if pix.colorspace is None or pix.colorspace.n not in (1, 3):
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    return Image.frombytes("L" if pix.n == 1 else "RGB", (pix.width, pix.height), pix.samples).convert("RGB")


def etape_images(livre, dossier, pdf, secours):
    doc = pymupdf.open(pdf)
    cache = {}

    def candidats(pi):
        if pi not in cache:
            out = []
            if 0 <= pi < doc.page_count:
                for info in doc[pi].get_image_info(xrefs=True):
                    if info["xref"] <= 0 or info["width"] < 60 or info["height"] < 60:
                        continue
                    try:
                        out.append((info["xref"], imagehash.phash(pil_xref(doc, info["xref"]))))
                    except Exception:
                        pass
            cache[pi] = out
        return cache[pi]

    bilan = {"pdf": 0, "secours": 0, "sans_image": 0, "deja": 0}
    for f in sorted((dossier / "figures").glob("*.jsonl")):
        lignes = lire_jsonl(f)
        for g in lignes:
            img = g.get("image")
            if img and (RACINE / img["lecture"]).exists() and (RACINE / img["vignette"]).exists():
                bilan["deja"] += 1
                continue
            ref = Path(secours) / nom_image(g["id"])
            if not ref.exists():
                g["image"] = None
                bilan["sans_image"] += 1
                continue
            h = imagehash.phash(Image.open(ref).convert("RGB"))
            pp = g["page_pdf"]
            meilleur = min(((h - c[1], c[0]) for pi in (pp - 1, pp - 2, pp) for c in candidats(pi)), default=None)
            if meilleur and meilleur[0] <= SEUIL_HASH:
                lec, vig, l, ht = exporter_webp(pil_xref(doc, meilleur[1]), livre, g["id"])
                prov = "pdf"
            else:
                lec, vig, l, ht = exporter_webp(Image.open(ref), livre, g["id"])
                prov = "secours-base"
            bilan["pdf" if prov == "pdf" else "secours"] += 1
            g["image"] = {"lecture": lec, "vignette": vig, "largeur": l, "hauteur": ht, "provenance": prov}
        ecrire_jsonl(f, lignes)
    return bilan


def etape_livre(livre, meta_db, meta_extra, dossier, pdf, passages_db, figures_db):
    pages = defaultdict(list)
    for p in passages_db:
        for pg in p.get("pg") or []:
            if str(pg).isdigit():
                pages[p["ch"]].append(int(pg))
    dom_ch = meta_extra.get("domaines_chapitres", {})
    principal = meta_extra["domaine_principal"]
    chapitres = [{
        "n": c["n"], "titre": c["titre"],
        "pages": {"debut": str(min(pages[c["n"]])) if pages[c["n"]] else None,
                  "fin": str(max(pages[c["n"]])) if pages[c["n"]] else None},
        "domaines": [principal] + [d for d in dom_ch.get(str(c["n"]), []) if d != principal],
    } for c in meta_db["chapitres"]]
    secondaires = sorted({d for c in chapitres for d in c["domaines"] if d != principal})
    nb_p = sum(1 for f in (dossier / "passages").glob("*.jsonl") for _ in lire_jsonl(f))
    figs = [g for f in (dossier / "figures").glob("*.jsonl") for g in lire_jsonl(f)]
    livre_json = {
        "id": livre, "titre": meta_extra.get("titre", meta_db["titre"]), "titre_court": meta_db.get("court", livre),
        "auteurs": meta_extra.get("auteurs", [meta_db.get("auteur", "")]),
        "edition": meta_extra.get("edition"), "annee": meta_extra.get("annee"),
        "langue": meta_extra["langue"],
        "domaines": {"principal": principal, "secondaires": secondaires},
        "chapitres": chapitres,
        "source": {"type": meta_extra.get("source_type", "pdf-texte"), "fichier": Path(pdf).name,
                   "sha256": sha256(pdf), "ocr": None},
        "statistiques": {
            "passages": nb_p, "figures": len(figs),
            "figures_sans_image": sum(1 for g in figs if not g.get("image")),
            "figures_image_secours": sum(1 for g in figs if (g.get("image") or {}).get("provenance") == "secours-base"),
            "passages_base_origine": len(passages_db),
        },
        "remplace_par": None,
    }
    ecrire_json(dossier / "livre.json", livre_json)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--livre", required=True)
    ap.add_argument("--export", required=True)
    ap.add_argument("--secours", required=True)
    ap.add_argument("--meta", required=True, help="JSON : titre, auteurs, edition, annee, langue, domaine_principal, domaines_chapitres")
    ap.add_argument("--etape", default="tout", choices=["figures", "passages", "images", "livre", "tout"])
    a = ap.parse_args()
    livre = a.livre
    dossier = RACINE / "livres" / livre
    pdf = RACINE / "sources" / f"{livre}.pdf"
    meta_extra = json.load(open(a.meta))
    passages_db, figures_db, meta_db = charger_export(a.export, livre)
    print(f"Export : {len(passages_db)} passages, {len(figures_db)} figures")
    if a.etape in ("figures", "passages", "tout"):
        principal = meta_extra["domaine_principal"]
        dch = meta_extra.get("domaines_chapitres", {})
        index = etape_figures(livre, figures_db, dossier,
                              lambda ch: [principal] + [d for d in dch.get(str(ch), []) if d != principal])
        print(f"Figures écrites : {len(figures_db)}")
    if a.etape in ("passages", "tout"):
        n, st = etape_passages(livre, passages_db, index, dossier, meta_extra["langue"])
        print(f"Passages écrits : {n} (dont {st['decoupes']} passages d'origine redécoupés), {st['renvois']} renvois de figures")
    if a.etape in ("images", "tout"):
        print("Images :", etape_images(livre, dossier, pdf, a.secours))
    if a.etape in ("livre", "tout"):
        etape_livre(livre, meta_db, meta_extra, dossier, pdf, passages_db, figures_db)
        print("livre.json écrit")


if __name__ == "__main__":
    main()
