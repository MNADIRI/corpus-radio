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
import re
from collections import defaultdict
from pathlib import Path

import cv2
import imagehash
import numpy as np
import pymupdf
from PIL import Image

from commun import (RACINE, decouper, ecrire_json, ecrire_jsonl, exporter_webp, lire_jsonl,
                    modalites_par_regles, nom_image, resoudre_renvois)

SEUIL_HASH = 12
SEUIL_CORRELATION = 0.70


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


def propre(fid):
    """Identifiant conforme au format : caractères hors [0-9A-Za-z.] supprimés (« - » devient « v »)."""
    livre, reste = fid.split(":", 1)
    return livre + ":" + re.sub(r"[^0-9A-Za-z.]", "", reste.replace("-", "v"))


def nouvel_id(livre, g, groupes):
    """Numérotation du livre. Livres numérotés par chapitre (« Fig. 12 ») : fig<ch>.<n>[lettre]."""
    if "." in g["fig"]:
        return propre(g["id"])
    num = g["fig"] if not g["fig"].startswith("x") else f"x{g['pp']}"
    membres = groupes[(g["ch"], num)]
    lettre = chr(97 + membres.index(g["id"])) if len(membres) > 1 else ""
    return propre(f"{livre}:fig{g['ch']}.{num}{lettre}")


def etape_figures(livre, figures_db, dossier, domaines_ch):
    """Écrit figures/chNN.jsonl et renvoie l'index de résolution des renvois."""
    par_chapitre = all("." not in g["fig"] for g in figures_db)
    groupes = defaultdict(list)
    for g in figures_db:
        cle = (g["ch"], g["fig"] if not g["fig"].startswith("x") else f"x{g['pp']}")
        groupes[cle].append(g["id"])
    anciennes = {}
    for f in (dossier / "figures").glob("*.jsonl"):
        for x in lire_jsonl(f):
            anciennes[x.get("ancien_id") or x["id"]] = x
    par_ch = defaultdict(list)
    index = defaultdict(dict)
    for g in figures_db:
        fid = nouvel_id(livre, g, groupes)
        ancien = anciennes.get(g["id"], {})
        img = ancien.get("image")
        if img and fid != g["id"]:
            for k in ("lecture", "vignette"):
                src = RACINE / img[k]
                dst = src.with_name(nom_image(fid))
                if src.exists() and src != dst:
                    src.rename(dst)
                img[k] = str(dst.relative_to(RACINE))
        lettre = fid.rsplit(".", 1)[1].lstrip("0123456789x")[-1:] if not g["pa"] else g["pa"]
        cle = (g["ch"], g["fig"]) if par_chapitre else g["fig"]
        index[cle][lettre or ""] = fid
        ligne = {
            "id": fid, "livre": livre, "chapitre": g["ch"], "numero": g["fig"],
            "panneau": (g["pa"] or lettre) or None,
            "panneaux": [], "page": g["pg"] or None, "page_pdf": g["pp"],
            "legende": g["cap"], "legende_fr": ancien.get("legende_fr"),
            "modalites": ancien.get("modalites") or modalites_par_regles(g["cap"]),
            "region": ancien.get("region"), "domaines": ancien.get("domaines") or domaines_ch(g["ch"]),
            "entites": ancien.get("entites") or [], "role": ancien.get("role"),
            "image": img,
        }
        if fid != g["id"]:
            ligne["ancien_id"] = g["id"]
        par_ch[g["ch"]].append(ligne)
    for lignes in par_ch.values():
        freres = defaultdict(list)
        for l in lignes:
            freres[l["numero"]].append(l)
        for groupe in freres.values():
            lettres = sorted(x["panneau"] for x in groupe if x["panneau"])
            for l in groupe:
                l["panneaux"] = lettres
    for ch, lignes in par_ch.items():
        ecrire_jsonl(dossier / "figures" / f"ch{ch:02d}.jsonl", lignes)
    return index, par_chapitre


def etape_passages(livre, passages_db, index_figs, dossier, langue, par_chapitre=False):
    par_ch, n = defaultdict(list), 0
    stats = {"decoupes": 0, "renvois": 0}
    for p in passages_db:
        morceaux = decouper(p["t"])
        if len(morceaux) > 1:
            stats["decoupes"] += 1
        for k, texte in enumerate(morceaux):
            n += 1
            if par_chapitre:
                idx = {num: d for (ch, num), d in index_figs.items() if ch == p["ch"]}
            else:
                idx = index_figs
            figs = resoudre_renvois(texte, livre, idx)
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


def _page_gris(doc, pi, zoom):
    pix = doc[pi].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csGRAY)
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width)


def localiser(doc, pi, vignette):
    """Retrouve la vignette dans le rendu de la page (corrélation normalisée, multi-échelle).
    Retourne (score, rectangle en points PDF)."""
    P = _page_gris(doc, pi, 1.0)
    T = np.array(vignette.convert("L"))
    meilleur = (-1.0, None)
    for s in np.geomspace(0.12, 1.0, 30):
        w = int(P.shape[1] * s)
        h = int(T.shape[0] * w / T.shape[1])
        if w < 20 or h < 20 or h > P.shape[0] or w > P.shape[1]:
            continue
        t = cv2.resize(T, (w, h), interpolation=cv2.INTER_AREA)
        _, mv, _, ml = cv2.minMaxLoc(cv2.matchTemplate(P, t, cv2.TM_CCOEFF_NORMED))
        if mv > meilleur[0]:
            meilleur = (float(mv), pymupdf.Rect(ml[0], ml[1], ml[0] + w, ml[1] + h))
    return meilleur


def etape_recadrage(livre, dossier, pdf, secours):
    """Deuxième passe pour les figures restées en image de secours (scans, planches découpées) :
    on localise la vignette dans la page et on recadre le rendu de la page en haute résolution."""
    doc = pymupdf.open(pdf)
    bilan = {"recadrees": 0, "restent_secours": 0}
    for f in sorted((dossier / "figures").glob("*.jsonl")):
        lignes = lire_jsonl(f)
        modif = False
        for g in lignes:
            img = g.get("image") or {}
            if img.get("provenance") != "secours-base" or img.get("essai_recadrage"):
                continue
            ref = Path(secours) / nom_image(g["id"])
            vig = Image.open(ref)
            pp = g["page_pdf"]
            essais = [(localiser(doc, pi, vig), pi) for pi in (pp - 1, pp - 2, pp) if 0 <= pi < doc.page_count]
            (score, rect), pi = max(essais, key=lambda x: x[0][0])
            if score >= SEUIL_CORRELATION:
                zoom = min(4.0, 1200 / max(rect.width, rect.height))
                pix = doc[pi].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=rect)
                im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples) if pix.n == 3 else \
                    Image.frombytes("RGB", (pix.width, pix.height), pymupdf.Pixmap(pymupdf.csRGB, pix).samples)
                lec, vg, l, ht = exporter_webp(im, livre, g["id"])
                g["image"] = {"lecture": lec, "vignette": vg, "largeur": l, "hauteur": ht, "provenance": "pdf-recadre"}
                bilan["recadrees"] += 1
            else:
                img["essai_recadrage"] = round(score, 3)
                bilan["restent_secours"] += 1
            modif = True
        if modif:
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
            "figures_recadrees": sum(1 for g in figs if (g.get("image") or {}).get("provenance") == "pdf-recadre"),
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
    ap.add_argument("--etape", default="tout", choices=["figures", "passages", "images", "recadrage", "livre", "tout"])
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
        index, par_chapitre = etape_figures(livre, figures_db, dossier,
                              lambda ch: [principal] + [d for d in dch.get(str(ch), []) if d != principal])
        print(f"Figures écrites : {len(figures_db)}")
    if a.etape in ("passages", "tout"):
        n, st = etape_passages(livre, passages_db, index, dossier, meta_extra["langue"], par_chapitre)
        print(f"Passages écrits : {n} (dont {st['decoupes']} passages d'origine redécoupés), {st['renvois']} renvois de figures")
    if a.etape in ("images", "tout"):
        print("Images :", etape_images(livre, dossier, pdf, a.secours))
    if a.etape in ("recadrage", "tout"):
        print("Recadrage :", etape_recadrage(livre, dossier, pdf, a.secours))
    if a.etape in ("livre", "tout"):
        etape_livre(livre, meta_db, meta_extra, dossier, pdf, passages_db, figures_db)
        print("livre.json écrit")


if __name__ == "__main__":
    main()
