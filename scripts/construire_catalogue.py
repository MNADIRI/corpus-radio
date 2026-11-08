#!/usr/bin/env python3
"""Construit ou complète catalogue/entites/<domaine>.jsonl et annote passages et figures.

Usage : .venv/bin/python scripts/construire_catalogue.py [--livre ID ...]

Version « règles » (v1), déterministe et idempotente :
  1. candidats = titres de section qui ressemblent à une entité pathologique ;
  2. fusion des variantes (accents, pluriel, sigle entre parenthèses) et réutilisation des entités
     existantes du catalogue (même identifiant ou même nom normalisé, synonymes compris) ;
  3. catégorie par mots-clés, domaines d'après les chapitres, régions d'après les textes ;
  4. liens : passage ↔ entité (section identique ou nom cité), figure ↔ entité (légende qui cite
     le nom, ou figure citée par un passage de l'entité dans le même chapitre) ;
  5. région et rôle « schéma » des figures par mots-clés.
Les champs enrichis à la main ou par Claude (synonymes_en, abreviations, entites_liees, remplace_par)
ne sont jamais écrasés.
"""
import json
import re
import unicodedata
from collections import defaultdict

from commun import RACINE, ecrire_jsonl, lire_jsonl

GENERIQUE = re.compile(r"^(introduction|conclusion|imagerie|clinique|diagnostic|epidemiologie|traitement|biologie|definition|"
                       r"generalites|histologie|anatomie|physiopathologie|pathogenie|etiologie|evolution|complications|"
                       r"radiographie|irm|echographie|scanner|tdm|scintigraphie|references|bibliographie|semiologie|aspects|"
                       r"points? cles|plan du chapitre|signes|technique|resume|imaging|differential|discussion|key points|"
                       r"diagnosis|clinical|pearls|findings|analyse|adulte|enfant|forme|formes|localisation|aspect)\b")
ENTITE = re.compile(r"(omes?\b|ites?\b|oses?\b|maladie|syndrome|kyste|tumeur|fracture|dysplasie|sarcome|luxation|rupture|"
                    r"necrose|infarctus|hernie|stenose|spondyl|arthr|myel|osteo|chondro|lipo|fibro|hemangi|angiom|tendin|"
                    r"bursite|conflit|instabilit|entorse|avulsion|dysostose|malformation|amylose|goutte|rachitisme|scorbut|"
                    r"histiocytose|myopathie|myosite|abces|tuberc|disease|tumou?r|syndrome|cyst|itis\b|oma\b)")
CATEGORIES = [
    ("traumatique", r"fracture|luxation|rupture|entorse|avulsion|trauma|lesion de|desinsertion|contusion|arrachement|fatigue"),
    ("infection", r"infect|abces|tuberc|osteomyelite|spondylodiscite|septique|cellulite|fasciite|myosite infect|brucell|actinomyc|syphil|lepre|mycos|hydatid"),
    ("tumeur", r"sarcome|ome\b|omes\b|tumeur|metasta|lymphome|myelome|leucem|carcinom|blastome|oma\b|tumor|kyste|cyst|histiocytose"),
    ("inflammatoire", r"arthrite|polyarthrite|spondyl(o)?arthrit|lupus|sclerodermie|vascularite|sarcoidose|sapho|myosite|dermatomyosite|tendinite|bursite|synovite|enthesite"),
    ("degeneratif", r"arthrose|degenera|discopathie|tendinopathie|conflit|usure|hernie discale|chondropathie"),
    ("metabolique", r"goutte|chondrocalcinose|rachitisme|osteomalacie|osteoporose|hyperparathyro|amylose|paget|acromegal|scorbut|hydroxyapatite|ochronose|hemochromatose|diabet|renale chronique"),
    ("congenital", r"dysplasie|dysostose|malformation|congenit|achondro|aplasie|agenesie|synostose|pied bot|osteochondrodysplasie|mucopolysacchar|osteogenese imparfaite"),
    ("vasculaire", r"necrose|osteonecrose|infarctus|angiome|hemangiome|vasculaire|anevrysm|thrombo|ischemi|hemophil"),
]
REGIONS = [
    ("epaule", r"epaule|coiffe|acromio|glenohumer|sus-epineux|supra-?epineux|labrum glenoid|clavicul|scapul|omoplate|shoulder"),
    ("coude", r"coude|olecran|epicondyl|epitrochle|radiocapitell|elbow"),
    ("poignet-main", r"poignet|carpe|scaphoide|lunatum|semi-lunaire|main\b|doigt|phalange|metacarp|pouce|wrist|hand|finger"),
    ("hanche", r"hanche|coxo|cotyle|acetabul|col femoral|tete femorale|trochanter|hip\b"),
    ("genou", r"genou|menisque|rotule|patell|ligament croise|tibial plateau|plateau tibial|knee"),
    ("cheville-pied", r"cheville|pied\b|calcaneu|talus|astragale|tarse|metatars|orteil|achille|ankle|foot"),
    ("rachis-cervical", r"cervical|atlas|axis|odontoide"),
    ("rachis-lombaire", r"lombaire|lumbar"),
    ("rachis-thoracique", r"rachis thoracique|rachis dorsal|vertebre thoracique|dorsal spine"),
    ("sacro-iliaques", r"sacro-?iliaque|sacroiliac"),
    ("bassin", r"bassin|pubis|ilium|iliaque|ischion|pelvis\b|pelvic"),
    ("crane", r"crane|cranien|voute|skull"),
    ("paroi-thoracique", r"cote\b|cotes\b|costal|sternum|sternal|paroi thoracique|rib\b"),
    ("cuisse", r"cuisse|diaphyse femorale|femur|thigh"),
    ("jambe", r"jambe|tibia|fibula|perone|leg\b"),
    ("bras", r"humerus|humeral|bras\b|arm\b"),
    ("avant-bras", r"avant-bras|radius|ulna|cubitus|forearm"),
]
SCHEMA = re.compile(r"sch[ée]ma|dessin|illustration|diagram")


def norm(s):
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c)).strip()


def cle(s):
    """Clé de fusion : sans accents, sans sigle entre parenthèses, sans pluriel simple."""
    s = re.sub(r"\s*\([^)]*\)", "", norm(s))
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return " ".join(w[:-1] if len(w) > 4 and w.endswith(("s", "x")) else w for w in s.split())


def slug(s):
    return "ent:" + re.sub(r"[^a-z0-9]+", "-", re.sub(r"\s*\([^)]*\)", "", norm(s))).strip("-")[:60].strip("-")


def sigle(s):
    m = re.search(r"\(([A-Z][A-Za-z0-9\-]{1,9})\)", s)
    return m.group(1) if m else None


def premier(regles, texte, defaut):
    t = norm(texte)
    for v, rx in regles:
        if re.search(rx, t):
            return v
    return defaut


def regions_de(texte):
    t = norm(texte)
    return [r for r, rx in REGIONS if re.search(rx, t)]


def main():
    livres, langues = {}, {}
    passages, figures = {}, {}
    fichiers_p, fichiers_f = defaultdict(list), defaultdict(list)
    for fl in sorted((RACINE / "livres").glob("*/livre.json")):
        L = json.loads(fl.read_text())
        livres[L["id"]] = {c["n"]: c["domaines"] for c in L["chapitres"]}
        langues[L["id"]] = L["langue"]
        for f in sorted((fl.parent / "passages").glob("*.jsonl")):
            for p in lire_jsonl(f):
                passages[p["id"]] = p
                fichiers_p[f].append(p["id"])
        for f in sorted((fl.parent / "figures").glob("*.jsonl")):
            for g in lire_jsonl(f):
                figures[g["id"]] = g
                fichiers_f[f].append(g["id"])

    # Catalogue existant
    existantes = {}
    for f in (RACINE / "catalogue/entites").glob("*.jsonl"):
        for e in lire_jsonl(f):
            existantes[e["id"]] = e
    par_cle = {}
    for e in existantes.values():
        for nom in [e["nom_fr"], *e["synonymes_fr"], *e["synonymes_en"]]:
            par_cle.setdefault(cle(nom), e["id"])

    # 1-2. Candidats et fusion
    entites = {eid: dict(e, passages=[], figures=[]) for eid, e in existantes.items()}
    sections = defaultdict(list)
    for p in passages.values():
        s = (p.get("section") or "").strip()
        if s and len(s) < 90 and not GENERIQUE.match(norm(s)) and ENTITE.search(norm(s)):
            sections[s].append(p["id"])
    for s, pids in sorted(sections.items()):
        k = cle(s)
        if not k:
            continue
        eid = par_cle.get(k)
        if not eid:
            eid = slug(s)
            while eid in entites and cle(entites[eid]["nom_fr"]) != k:
                eid += "-2"
            par_cle[k] = eid
        e = entites.setdefault(eid, {
            "id": eid, "nom_fr": re.sub(r"\s+", " ", s), "synonymes_fr": [], "synonymes_en": [], "abreviations": [],
            "domaines": [], "regions": [], "categorie": premier(CATEGORIES, s, "autre"),
            "passages": [], "figures": [], "entites_liees": [], "remplace_par": None})
        if s != e["nom_fr"] and s not in e["synonymes_fr"] and cle(s) != cle(e["nom_fr"]):
            e["synonymes_fr"].append(s)
        sg = sigle(s)
        if sg and sg not in [a["sigle"] for a in e["abreviations"]]:
            e["abreviations"].append({"sigle": sg, "forme": re.sub(r"\s*\([^)]*\)", "", s)})
        e["passages"].extend(pids)

    # 4. Liens par citation du nom (noms d'au moins 2 mots ou d'au moins 9 lettres)
    motifs = []
    for e in entites.values():
        if e.get("remplace_par"):
            continue
        for nom in [e["nom_fr"], *e["synonymes_fr"], *e["synonymes_en"]]:
            k = cle(nom)
            if len(k.split()) >= 2 or len(k) >= 9:
                motifs.append((re.compile(r"\b" + re.escape(k).replace(r"\ ", r"s?\s+") + r"s?\b"), e["id"]))
    def cites(texte):
        t = " ".join(cle(texte).split())
        return {eid for rx, eid in motifs if rx.search(t)}

    for p in passages.values():
        p["entites"] = sorted(set(p.get("entites") or []) | cites(p["texte"]) |
                              {eid for eid, e in entites.items() if p["id"] in e["passages"]})
    pass_par_ent = defaultdict(set)
    for p in passages.values():
        for eid in p["entites"]:
            pass_par_ent[eid].add(p["id"])
    for g in figures.values():
        lies = cites(g["legende"] + " " + (g.get("legende_fr") or ""))
        g["entites"] = sorted(set(g.get("entites") or []) | lies)
    # figure citée par un passage d'une entité (même chapitre)
    for p in passages.values():
        for fid in p["figures_citees"]:
            g = figures.get(fid)
            if g and g["chapitre"] == p["chapitre"] and p.get("section") in sections:
                eid = par_cle.get(cle(p["section"]))
                if eid and eid not in g["entites"]:
                    g["entites"].append(eid)
                    g["entites"].sort()

    # 3. Domaines, régions, listes de l'entité
    for eid, e in entites.items():
        pids = sorted(pass_par_ent.get(eid, set()))
        fids = sorted(fid for fid, g in figures.items() if eid in g["entites"])
        e["passages"], e["figures"] = pids, fids
        doms = set(e["domaines"])
        regs = defaultdict(int)
        for pid in pids:
            p = passages[pid]
            doms.update(livres[p["livre"]].get(p["chapitre"], []))
            for r in regions_de((p.get("section") or "") + " " + p["texte"][:600]):
                regs[r] += 1
        e["domaines"] = sorted(doms) or ["msk"]
        if not e["regions"]:
            seuil = max(2, len(pids) // 4)
            e["regions"] = sorted(r for r, n in regs.items() if n >= seuil)[:4]

    # 5. Figures : région et rôle « schéma »
    for g in figures.values():
        if not g.get("region"):
            rs = regions_de(g["legende"])
            g["region"] = rs[0] if len(rs) == 1 else ("multiple" if len(rs) > 1 else None)
        if not g.get("role") and ("schema" in g["modalites"] or SCHEMA.search(g["legende"].lower())):
            g["role"] = "schema"
        if not g.get("legende_fr") and langues.get(g["livre"]) == "fr":
            # livre en français : la légende d'origine est déjà la légende française
            g["legende_fr"] = g["legende"]

    # Écriture
    for f, ids in fichiers_p.items():
        ecrire_jsonl(f, [passages[i] for i in ids])
    for f, ids in fichiers_f.items():
        ecrire_jsonl(f, [figures[i] for i in ids])
    actives = [e for e in entites.values() if e["passages"] or e["figures"] or e.get("remplace_par")]
    for f in (RACINE / "catalogue/entites").glob("*.jsonl"):
        f.unlink()
    par_dom = defaultdict(list)
    for e in sorted(actives, key=lambda x: x["id"]):
        for d in e["domaines"]:
            par_dom[d].append(e)
    for d, es in par_dom.items():
        ecrire_jsonl(RACINE / "catalogue/entites" / f"{d}.jsonl", es)
    nouvelles = [e for e in actives if e["id"] not in existantes]
    print(f"Entités : {len(actives)} ({len(nouvelles)} nouvelles) · domaines : "
          + ", ".join(f"{d} {len(v)}" for d, v in sorted(par_dom.items())))
    print(f"Passages liés à au moins une entité : {sum(1 for p in passages.values() if p['entites'])}/{len(passages)}")
    print(f"Figures liées à au moins une entité : {sum(1 for g in figures.values() if g['entites'])}/{len(figures)}")
    print(f"Figures avec région : {sum(1 for g in figures.values() if g.get('region'))}/{len(figures)}")


if __name__ == "__main__":
    main()
