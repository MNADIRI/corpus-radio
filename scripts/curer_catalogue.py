#!/usr/bin/env python3
"""Cure le catalogue d'entités sans renommer ni supprimer d'identifiant (règle des identifiants stables).

Usage : .venv/bin/python scripts/curer_catalogue.py

  - doublons (pluriel, accents, qualificatif de section : « généralités », « traitement », « formes… »,
    « autres localisations », « chez l'enfant »…) : l'entité la plus complète est gardée, les autres
    reçoivent remplace_par vers elle ; ses listes de passages et de figures absorbent les leurs ;
  - titres qui ne sont pas des entités (« Case 26… », sections génériques) : masque = true
    (ils restent dans le catalogue mais ne sont plus proposés par l'application).
Idempotent : relancer ne change rien de plus.
"""
import re
import unicodedata
from collections import defaultdict

from commun import RACINE, ecrire_jsonl, lire_jsonl

QUALIFS = r"(generalites?|traitements?|autres? localisations?|formes? (cliniques?|particulieres?|atypiques?)|aspects? (cliniques?|radiologiques?|en imagerie)|imagerie|diagnostic( differentiel)?|chez l.?enfant|chez l.?adulte|de l.?enfant|de l.?adulte|epidemiologie|clinique|evolution|complications?|definition|introduction|physiopathologie)"
BRUIT = re.compile(r"^(case|cas)\s*\d+\b|^(chapitre|tableau|figure|annexe)\b|^(points? cles?|a retenir|en pratique|conclusion)$")


def norm(s):
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def cle(nom):
    s = norm(nom)
    s = re.sub(r"\s*\([^)]*\)", "", s)
    s = re.split(r"\s*[:–—]\s*", s)[0] if re.search(r"[:–—]\s*" + QUALIFS, s) else s
    s = re.sub(r"[,;]\s*" + QUALIFS + r".*$", "", s)
    s = re.sub(r"\s+" + QUALIFS + r"$", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return " ".join(w[:-1] if len(w) > 4 and w.endswith(("s", "x")) else w for w in s.split())


def main():
    fichiers = sorted((RACINE / "catalogue" / "entites").glob("*.jsonl"))
    par_dom = {f: lire_jsonl(f) for f in fichiers}
    ents = {}
    for lst in par_dom.values():
        for e in lst:
            ents.setdefault(e["id"], e)
    groupes = defaultdict(list)
    for e in ents.values():
        if e.get("remplace_par"):
            continue
        k = cle(e["nom_fr"])
        if BRUIT.search(norm(e["nom_fr"])) or len(k) < 3:
            e["masque"] = True
            continue
        groupes[k].append(e)
    fusions = 0
    for k, g in groupes.items():
        if len(g) < 2:
            continue
        g.sort(key=lambda e: (-(len(e["passages"]) + len(e["figures"])), len(e["nom_fr"])))
        tete = g[0]
        for e in g[1:]:
            e["remplace_par"] = tete["id"]
            for champ in ("passages", "figures"):
                tete[champ] = sorted(set(tete[champ]) | set(e[champ]))
            for s in [e["nom_fr"], *e["synonymes_fr"]]:
                if s != tete["nom_fr"] and s not in tete["synonymes_fr"]:
                    tete["synonymes_fr"].append(s)
            tete["domaines"] = sorted(set(tete["domaines"]) | set(e["domaines"]))
            tete["regions"] = sorted(set(tete["regions"]) | set(e["regions"]))[:6]
            fusions += 1
    for f, lst in par_dom.items():
        ecrire_jsonl(f, [ents[e["id"]] for e in lst])
    actives = [e for e in ents.values() if not e.get("remplace_par") and not e.get("masque")]
    print(f"Entités : {len(ents)} · fusionnées {fusions} · masquées {sum(1 for e in ents.values() if e.get('masque'))} · actives {len(actives)}")


if __name__ == "__main__":
    main()
