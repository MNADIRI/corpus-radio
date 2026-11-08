#!/usr/bin/env python3
"""Reconstruit index/ et catalogue/manifeste.json à partir de livres/ et catalogue/entites/.

Usage : .venv/bin/python scripts/construire_index.py

Pour chaque portée (global + chaque domaine présent) :
  index/<portee>/termes/<xx>.json    passages : terme → [[passage_id, fréquence, longueur], …]
  index/<portee>/legendes/<xx>.json  figures  : terme → [[figure_id, fréquence, longueur], …]
  index/<portee>/<type>/_meta.json   n_docs, longueur_moyenne, préfixes (pour BM25)
Un passage appartient aux domaines de son chapitre ; une figure à ses propres domaines.
Le dossier index/ est entièrement régénéré (idempotent).
"""
import json
import shutil
from collections import Counter, defaultdict
from datetime import date

from commun import RACINE, ecrire_json, lire_jsonl, normaliser, prefixe

VERSION_INDEX = 1
MAX_POSTINGS = 1500
MAX_OCTETS = 64_000


def construire(portee, typ, docs):
    """docs : liste de (id, texte)."""
    postings = defaultdict(list)
    longueurs = []
    for did, texte in docs:
        termes = normaliser(texte)
        if not termes:
            continue
        longueurs.append(len(termes))
        for t, n in Counter(termes).items():
            postings[t].append([did, n, len(termes)])
    # Plafond par terme : un terme très fréquent garde ses MAX_POSTINGS meilleurs documents
    # (fréquence relative), son df réel est conservé pour l'IDF de BM25.
    df_reel = {}
    for t, lst in postings.items():
        if len(lst) > MAX_POSTINGS:
            df_reel[t] = len(lst)
            lst.sort(key=lambda x: -x[1] / x[2])
            del lst[MAX_POSTINGS:]
    # Découpage adaptatif : préfixe de 2 lettres, allongé tant qu'un morceau dépasse MAX_OCTETS.
    def poids(t):
        return len(t) + 8 + sum(len(x[0]) + 12 for x in postings[t])
    morceaux = {}
    pile = [(2, sorted(postings))]
    while pile:
        n, termes = pile.pop()
        groupes = defaultdict(list)
        for t in termes:
            groupes[(t + "_" * n)[:n]].append(t)
        for px, ts in groupes.items():
            if sum(poids(t) for t in ts) > MAX_OCTETS and any(len(t) > n for t in ts) and n < 8:
                courts = [t for t in ts if len(t) <= n]
                longs = [t for t in ts if len(t) > n]
                if courts:
                    morceaux[px + "="] = courts   # termes exactement égaux au préfixe
                pile.append((n + 1, longs))
            else:
                morceaux[px] = ts
    base = RACINE / "index" / portee / typ
    taille = 0
    for px, ts in morceaux.items():
        doc = {"version": VERSION_INDEX, "portee": portee, "prefixe": px, "termes": {t: postings[t] for t in ts}}
        dfs = {t: df_reel[t] for t in ts if t in df_reel}
        if dfs:
            doc["df"] = dfs
        ecrire_json(base / f"{px}.json", doc, compact=True)
        taille += (base / f"{px}.json").stat().st_size
    ecrire_json(base / "_meta.json", {
        "version": VERSION_INDEX, "portee": portee, "type": typ, "n_docs": len(longueurs),
        "longueur_moyenne": round(sum(longueurs) / max(1, len(longueurs)), 2),
        "prefixes": sorted(morceaux), "taille_octets": taille,
    })
    return len(longueurs), taille


def main():
    livres = []
    passages = defaultdict(list)   # portée → [(id, texte)]
    legendes = defaultdict(list)
    stats_dom = defaultdict(lambda: {"livres": set(), "passages": 0, "figures": 0})
    for fl in sorted((RACINE / "livres").glob("*/livre.json")):
        L = json.loads(fl.read_text())
        if L.get("remplace_par"):
            continue
        dom_ch = {c["n"]: c["domaines"] for c in L["chapitres"]}
        nb_p = nb_f = 0
        for f in sorted((fl.parent / "passages").glob("*.jsonl")):
            for p in lire_jsonl(f):
                if p.get("remplace_par"):
                    continue
                nb_p += 1
                doms = dom_ch.get(p["chapitre"], [L["domaines"]["principal"]])
                texte = " ".join(filter(None, [p.get("section"), p.get("sous_section"), p["texte"]]))
                for portee in ["global", *doms]:
                    passages[portee].append((p["id"], texte))
                for d in doms:
                    stats_dom[d]["livres"].add(L["id"])
                    stats_dom[d]["passages"] += 1
        for f in sorted((fl.parent / "figures").glob("*.jsonl")):
            for g in lire_jsonl(f):
                if g.get("remplace_par"):
                    continue
                nb_f += 1
                texte = " ".join(filter(None, [g["legende"], g.get("legende_fr") if g.get("legende_fr") != g["legende"] else None]))
                for portee in ["global", *g["domaines"]]:
                    legendes[portee].append((g["id"], texte))
                for d in g["domaines"]:
                    stats_dom[d]["figures"] += 1
        livres.append({
            "id": L["id"], "titre": L["titre"], "titre_court": L.get("titre_court", L["id"]), "langue": L["langue"],
            "domaine_principal": L["domaines"]["principal"],
            "domaines": [L["domaines"]["principal"], *L["domaines"]["secondaires"]],
            "chapitres": len(L["chapitres"]), "passages": nb_p, "figures": nb_f,
        })

    entites_par_dom = Counter()
    entites = set()
    for f in (RACINE / "catalogue/entites").glob("*.jsonl"):
        for e in lire_jsonl(f):
            entites.add(e["id"])
            entites_par_dom[f.stem] += 1

    shutil.rmtree(RACINE / "index", ignore_errors=True)
    rapport = {}
    for portee in sorted(set(passages) | set(legendes)):
        rapport[portee] = {
            "termes": construire(portee, "termes", passages.get(portee, [])),
            "legendes": construire(portee, "legendes", legendes.get(portee, [])),
        }

    ancien = RACINE / "catalogue/manifeste.json"
    version = 1
    if ancien.exists():
        version = int(json.loads(ancien.read_text())["version_corpus"].split(".")[0]) + 1
    ecrire_json(ancien, {
        "version_corpus": f"{version}.0",
        "date": date.today().isoformat(),
        "livres": livres,
        "domaines": {d: {"livres": sorted(s["livres"]), "passages": s["passages"], "figures": s["figures"],
                         "entites": entites_par_dom.get(d, 0)} for d, s in sorted(stats_dom.items())},
        "statistiques": {"livres": len(livres), "passages": sum(l["passages"] for l in livres),
                         "figures": sum(l["figures"] for l in livres), "entites": len(entites)},
    })
    for portee, r in rapport.items():
        print(f"{portee:16s} termes {r['termes'][0]:6d} docs {r['termes'][1]/1e6:6.2f} Mo · "
              f"légendes {r['legendes'][0]:6d} docs {r['legendes'][1]/1e6:6.2f} Mo")
    print(f"Manifeste : version {version}.0, {len(livres)} livre(s)")


if __name__ == "__main__":
    main()
