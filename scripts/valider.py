#!/usr/bin/env python3
"""Validation complète du dépôt corpus-radio.

Usage : .venv/bin/python scripts/valider.py [--livre ID] [--json rapport.json]

Contrôles :
  - chaque fichier respecte son JSON Schema (schema/*.schema.json) ;
  - les valeurs de taxonomie (domaines, régions, modalités, rôles, catégories) existent ;
  - les identifiants sont uniques ;
  - chaque image référencée existe sur le disque ;
  - chaque figure citée et chaque entité référencée existe ;
  - les modules ne citent que des figures existantes.
Sortie : un rapport chiffré. Code retour 1 s'il y a au moins une erreur.
"""
import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

from jsonschema import Draft202012Validator

RACINE = Path(__file__).resolve().parent.parent
MAX_ERREURS_AFFICHEES = 40


def charger_schemas():
    return {p.name.removesuffix(".schema.json"): Draft202012Validator(json.loads(p.read_text()))
            for p in (RACINE / "schema").glob("*.schema.json")}


def lire_jsonl(chemin):
    for n, ligne in enumerate(chemin.read_text(encoding="utf-8").splitlines(), 1):
        if ligne.strip():
            yield n, json.loads(ligne)


def entites_a_head():
    """Identifiants d'entités présents au dernier commit (pour compter les nouvelles)."""
    try:
        sortie = subprocess.run(["git", "-C", str(RACINE), "ls-tree", "-r", "--name-only", "HEAD", "catalogue/entites"],
                                capture_output=True, text=True, check=True).stdout.split()
    except Exception:
        return set()
    ids = set()
    for f in sortie:
        contenu = subprocess.run(["git", "-C", str(RACINE), "show", f"HEAD:{f}"], capture_output=True, text=True).stdout
        for ligne in contenu.splitlines():
            if ligne.strip():
                ids.add(json.loads(ligne)["id"])
    return ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--livre", help="limiter le rapport chiffré à ce livre (les contrôles restent globaux)")
    ap.add_argument("--json", help="écrire aussi le rapport en JSON dans ce fichier")
    args = ap.parse_args()

    schemas = charger_schemas()
    tax = json.loads((RACINE / "schema/taxonomie.json").read_text())
    T = {k: {x["id"] for x in tax[k]} for k in ("domaines", "modalites", "regions", "roles_figure", "categories_entite")}
    erreurs = []

    def err(lieu, msg):
        erreurs.append(f"{lieu} : {msg}")

    def schema(nom, doc, lieu):
        for e in schemas[nom].iter_errors(doc):
            chemin = "/".join(str(x) for x in e.absolute_path)
            err(lieu, f"schéma {nom} [{chemin}] {e.message[:160]}")

    def tax_ok(valeurs, axe, lieu):
        for v in valeurs:
            if v not in T[axe]:
                err(lieu, f"valeur « {v} » absente de la taxonomie ({axe})")

    vus = {}

    def unique(i, lieu):
        if i in vus:
            err(lieu, f"identifiant en double {i} (déjà dans {vus[i]})")
        vus[i] = lieu

    passages, figures, entites = {}, {}, {}
    stats = defaultdict(Counter)

    # Livres, passages, figures
    for dlivre in sorted((RACINE / "livres").glob("*/")):
        lid = dlivre.name
        fl = dlivre / "livre.json"
        if not fl.exists():
            err(dlivre.relative_to(RACINE), "livre.json manquant")
            continue
        livre = json.loads(fl.read_text())
        schema("livre", livre, fl.relative_to(RACINE))
        if livre.get("id") != lid:
            err(fl.relative_to(RACINE), f"id {livre.get('id')} différent du dossier {lid}")
        tax_ok([livre["domaines"]["principal"], *livre["domaines"]["secondaires"]], "domaines", fl.relative_to(RACINE))
        for ch in livre.get("chapitres", []):
            tax_ok(ch["domaines"], "domaines", f"{fl.relative_to(RACINE)} ch{ch['n']}")
        for f in sorted((dlivre / "passages").glob("*.jsonl")):
            for n, p in lire_jsonl(f):
                lieu = f"{f.relative_to(RACINE)}:{n}"
                schema("passage", p, lieu)
                unique(p["id"], lieu)
                if p["livre"] != lid:
                    err(lieu, "champ livre incohérent")
                passages[p["id"]] = (p, lieu)
                stats[lid]["passages"] += 1
        for f in sorted((dlivre / "figures").glob("*.jsonl")):
            for n, g in lire_jsonl(f):
                lieu = f"{f.relative_to(RACINE)}:{n}"
                schema("figure", g, lieu)
                unique(g["id"], lieu)
                tax_ok(g["modalites"], "modalites", lieu)
                tax_ok(g["domaines"], "domaines", lieu)
                if g.get("region"):
                    tax_ok([g["region"]], "regions", lieu)
                if g.get("role"):
                    tax_ok([g["role"]], "roles_figure", lieu)
                figures[g["id"]] = (g, lieu)
                stats[lid]["figures"] += 1
                if not g["legende"].strip():
                    stats[lid]["figures_sans_legende"] += 1
                img = g.get("image")
                if not img:
                    stats[lid]["legendes_sans_image"] += 1
                else:
                    for cle in ("lecture", "vignette"):
                        if not (RACINE / img[cle]).exists():
                            err(lieu, f"image {cle} introuvable : {img[cle]}")
                    if img.get("provenance") == "secours-base":
                        stats[lid]["images_secours"] += 1
                if not g.get("legende_fr"):
                    stats[lid]["legendes_non_traduites"] += 1

    # Entités
    for f in sorted((RACINE / "catalogue/entites").glob("*.jsonl")):
        for n, e in lire_jsonl(f):
            lieu = f"{f.relative_to(RACINE)}:{n}"
            if e["id"] in entites:
                continue  # une entité multi-domaines apparaît dans plusieurs fichiers ; on la contrôle une fois
            schema("entite", e, lieu)
            tax_ok(e["domaines"], "domaines", lieu)
            tax_ok(e["regions"], "regions", lieu)
            tax_ok([e["categorie"]], "categories_entite", lieu)
            entites[e["id"]] = (e, lieu)

    # Références croisées
    for pid, (p, lieu) in passages.items():
        for fid in p["figures_citees"]:
            if fid not in figures:
                err(lieu, f"figure citée inexistante {fid}")
        for eid in p["entites"]:
            if eid not in entites:
                err(lieu, f"entité inexistante {eid}")
        if p.get("remplace_par") and p["remplace_par"] not in passages:
            err(lieu, f"remplace_par vers un passage inexistant {p['remplace_par']}")
    for fid, (g, lieu) in figures.items():
        for eid in g["entites"]:
            if eid not in entites:
                err(lieu, f"entité inexistante {eid}")
    for eid, (e, lieu) in entites.items():
        for pid in e["passages"]:
            if pid not in passages:
                err(lieu, f"passage inexistant {pid}")
        for fid in e["figures"]:
            if fid not in figures:
                err(lieu, f"figure inexistante {fid}")
        for lie in e["entites_liees"]:
            if lie not in entites:
                err(lieu, f"entité liée inexistante {lie}")
        if e.get("remplace_par") and e["remplace_par"] not in entites:
            err(lieu, f"remplace_par vers une entité inexistante {e['remplace_par']}")

    # Index et manifeste
    for f in sorted(p for p in (RACINE / "index").rglob("*.json") if "artefact" not in p.parts):
        doc = json.loads(f.read_text())
        lieu = f.relative_to(RACINE)
        if f.name == "_meta.json":
            schema("index-meta", doc, lieu)
            continue
        schema("index-termes", doc, lieu)
        for terme, postings in doc.get("termes", {}).items():
            for pid, *_ in postings:
                if pid not in passages and pid not in figures:
                    err(lieu, f"le terme « {terme} » pointe vers {pid} inexistant")
                    break
    fm = RACINE / "catalogue/manifeste.json"
    if fm.exists():
        schema("manifeste", json.loads(fm.read_text()), fm.relative_to(RACINE))
    elif passages:
        err("catalogue/manifeste.json", "manquant")

    # Modules
    n_modules = 0
    for f in sorted((RACINE / "apprentissage").rglob("*.json")):
        m = json.loads(f.read_text())
        lieu = f.relative_to(RACINE)
        schema("module", m, lieu)
        tax_ok([m["domaine"]], "domaines", lieu)
        unique(m["id"], lieu)
        n_modules += 1
        refs = [fid for s in m["sections"] for fid in s["figures"]] + [q["figure"] for q in m["quiz"] if q.get("figure")]
        for fid in refs:
            if fid not in figures:
                err(lieu, f"figure inexistante {fid}")

    # Rapport
    anciennes = entites_a_head()
    nouvelles = [e for e in entites if e not in anciennes]
    portee = [args.livre] if args.livre else sorted(stats)
    rapport = {
        "livres": {lid: dict(stats[lid]) for lid in portee},
        "total": {"passages": len(passages), "figures": len(figures), "entites": len(entites),
                  "nouvelles_entites": len(nouvelles), "modules": n_modules},
        "erreurs": len(erreurs),
    }
    print("== Rapport de validation corpus-radio ==")
    for lid in portee:
        s = stats[lid]
        print(f"[{lid}] passages {s['passages']} · figures {s['figures']} · figures sans légende {s['figures_sans_legende']}"
              f" · légendes sans image {s['legendes_sans_image']} · images de secours {s['images_secours']}"
              f" · légendes non traduites {s['legendes_non_traduites']}")
    t = rapport["total"]
    print(f"Total : {t['passages']} passages, {t['figures']} figures, {t['entites']} entités"
          f" ({t['nouvelles_entites']} nouvelles), {t['modules']} modules")
    if erreurs:
        print(f"\n{len(erreurs)} erreur(s) :")
        for e in erreurs[:MAX_ERREURS_AFFICHEES]:
            print("  -", e)
        if len(erreurs) > MAX_ERREURS_AFFICHEES:
            print(f"  … et {len(erreurs) - MAX_ERREURS_AFFICHEES} autres")
    else:
        print("\nAucune erreur.")
    if args.json:
        rapport["liste_erreurs"] = erreurs
        Path(args.json).write_text(json.dumps(rapport, ensure_ascii=False, indent=2))
    sys.exit(1 if erreurs else 0)


if __name__ == "__main__":
    main()
