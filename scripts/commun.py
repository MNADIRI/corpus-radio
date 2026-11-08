"""Fonctions partagées par les scripts de corpus-radio."""
import json
import re
import unicodedata
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
LECTURE_PX = 1200
VIGNETTE_PX = 320

MOTS_VIDES = set("""
a au aux avec ce ces cet cette dans de des du elle en et est etre il ils je la le les leur leurs lui mais me meme
mes moi mon ne nos notre nous on ou par pas pour qu que qui sa se ses son sur ta te tes toi ton tu un une vos votre
vous y d l s c n j m t qu plus ou entre sans sous chez lors tres peut peuvent sont ete etait cas fig figure figures
the of and to in is are was were be been an as at by for from on or that this with it its not no can may which
than these those into also other such has have had but if all any more most some only
""".split())


def normaliser(texte):
    """Minuscules, sans accents, découpé en termes, mots vides retirés."""
    t = unicodedata.normalize("NFKD", texte.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return [m for m in re.findall(r"[a-z0-9]+", t) if len(m) > 1 and m not in MOTS_VIDES]


def prefixe(terme):
    return (terme + "_")[:2]


def nom_image(fig_id):
    return fig_id.replace(":", "_") + ".webp"


def chemins_image(livre, fig_id):
    n = nom_image(fig_id)
    return f"images/{livre}/lecture/{n}", f"images/{livre}/vignettes/{n}"


def exporter_webp(im, livre, fig_id):
    """Écrit les versions lecture (~1200 px) et vignette (~320 px). Retourne (lecture, vignette, l, h)."""
    lec, vig = chemins_image(livre, fig_id)
    im = im.convert("RGB")
    a = im.copy()
    a.thumbnail((LECTURE_PX, LECTURE_PX))
    (RACINE / lec).parent.mkdir(parents=True, exist_ok=True)
    a.save(RACINE / lec, "WEBP", quality=80, method=6)
    b = im.copy()
    b.thumbnail((VIGNETTE_PX, VIGNETTE_PX))
    (RACINE / vig).parent.mkdir(parents=True, exist_ok=True)
    b.save(RACINE / vig, "WEBP", quality=70, method=6)
    return lec, vig, a.width, a.height


def ecrire_jsonl(chemin, lignes):
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with open(chemin, "w", encoding="utf-8") as f:
        for x in lignes:
            f.write(json.dumps(x, ensure_ascii=False, separators=(",", ":")) + "\n")


def lire_jsonl(chemin):
    with open(chemin, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def ecrire_json(chemin, doc, compact=False):
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        chemin.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    else:
        chemin.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- renvois aux figures

_RENVOI = re.compile(r"\b[Ff]ig(?:ure)?s?\.?\s*((?:\d+[.\-]\d+|\d+)[a-z]?(?:\s*(?:,|et|and|à|to|[-–])\s*(?:(?:\d+[.\-]\d+|\d+)[a-z]?|[a-z]\b))*)")
_JETON = re.compile(r"(\d+(?:[.\-]\d+)?)([a-z])?|\b([a-z])\b|(à|to|[-–])")


def renvois_figures(texte):
    """« fig. 2.32 », « Fig 3 et 6c », « fig. 1.10a à c » → liste de (numéro, lettre ou None)."""
    out = []
    for m in _RENVOI.finditer(texte):
        num, plage, dernier = None, False, None
        for j in _JETON.finditer(m.group(1)):
            n, l, seule, sep = j.groups()
            if sep:
                plage = True
                continue
            if n:
                num = n.replace("-", ".")
                out.append((num, l))
                dernier = l
            elif seule and num:
                if plage and dernier:
                    for c in range(ord(dernier) + 1, ord(seule) + 1):
                        out.append((num, chr(c)))
                else:
                    out.append((num, seule))
                dernier = seule
            plage = False
    return out


def resoudre_renvois(texte, livre, figures_par_numero):
    """Transforme les renvois en identifiants de figures existantes (sans lettre → tous les panneaux)."""
    ids = []
    for num, lettre in renvois_figures(texte):
        panneaux = figures_par_numero.get(num)
        if not panneaux:
            continue
        if lettre and lettre in panneaux:
            ids.append(panneaux[lettre])
        elif not lettre or lettre not in panneaux:
            ids.extend(panneaux.values())
    vu = set()
    return [i for i in ids if not (i in vu or vu.add(i))]


# ---------------------------------------------------------------- découpage des passages

_FIN_PHRASE = re.compile(r"(?<=[.!?…»])\s+(?=[«A-ZÀ-ÖØ-Þ0-9■•(])")


def decouper(texte, mini=150, maxi=400):
    """Découpe un texte trop long en morceaux de mini–maxi mots, uniquement en fin de phrase.
    ' '.join(morceaux) redonne le texte d'origine (à l'espacement près)."""
    if len(texte.split()) <= maxi:
        return [texte]
    phrases = _FIN_PHRASE.split(texte)
    morceaux, cur = [], []
    for ph in phrases:
        n_cur = sum(len(x.split()) for x in cur)
        if cur and n_cur >= mini and n_cur + len(ph.split()) > maxi:
            morceaux.append(" ".join(cur))
            cur = []
        cur.append(ph)
    if cur:
        if morceaux and sum(len(x.split()) for x in cur) < mini // 2:
            morceaux[-1] += " " + " ".join(cur)
        else:
            morceaux.append(" ".join(cur))
    return morceaux


# ---------------------------------------------------------------- pré-annotation par règles

_MODALITES = [
    ("irm", r"\birm\b|\bmri\b|\bt1\b|\bt2\b|stir|dp fs|\bflair\b|diffusion|gadolinium|\bmr\b"),
    ("tdm", r"\btdm\b|scanner|tomodensitom|\bct\b|computed tomograph|arthroscanner"),
    ("echo", r"[ée]chograph|doppler|ultrasound|\bus\b|sonograph"),
    ("nucleaire", r"scintigraph|\btep\b|\bpet\b|spect|bone scan|fdg"),
    ("angio", r"angiograph|art[ée]riograph|phl[ée]bograph"),
    ("histo", r"histolog|microscop|coloration|\bhes\b|anatomopath|pi[èe]ce op[ée]ratoire|macroscop|specimen"),
    ("schema", r"sch[ée]ma|dessin|illustration|diagram|classification de"),
    ("rx", r"radiograph|clich[ée]|\brx\b|incidence|radiogram|x-ray|profil|face\b"),
]


def modalites_par_regles(legende):
    t = legende.lower()
    return [m for m, rx in _MODALITES if re.search(rx, t)]
