# corpus-radio

Base de connaissances en radiologie (toutes spécialités) pour l'application « Radiologie », publiée comme artefact claude.ai. Claude Code est le seul à écrire dans ce dépôt.

## Règles permanentes

- **Français partout pour l'utilisateur.** Tout ce qui est présenté à l'utilisateur est en français, quelle que soit la langue source. Le texte d'origine reste conservé tel quel dans le dépôt (`texte`, `legende`).
- **Acronymes développés.** Chaque acronyme est suivi de sa signification entre parenthèses à sa première occurrence, dans les fiches, les modules et l'interface. Exemple : IRM (imagerie par résonance magnétique).
- **Aucune affirmation médicale sans source.** Chaque ligne de fiche ou de module cite un passage (`livre:pNNNNN`), une figure (`livre:figX.Y`) ou un PMID (identifiant PubMed).
- **Identifiants stables.** Un identifiant n'est jamais réutilisé ni renommé. Une correction se fait par le champ `remplace_par`. La taxonomie (`schema/taxonomie.json`) ne change que par ajout.
- **Pas de modification à la main** dans `livres/`, `catalogue/` ou `index/`. Toute modification passe par les scripts de `scripts/`, puis par `scripts/valider.py`.
- **Simplicité avant tout.** Pas de serveur, pas de dépendance hébergée, pas de framework front-end : une page HTML autonome en JavaScript natif.
- **Les PDF sources ne sont jamais versionnés.** Ils restent dans `sources/`, exclu par `.gitignore`.

## Identifiants

| Objet | Format | Exemple |
|---|---|---|
| Livre | minuscules et tirets | `cotten-t1` |
| Passage | `<livre>:p` + 5 chiffres | `cotten-t1:p00412` |
| Figure | `<livre>:fig` + numéro du livre (+ lettre du panneau) | `cotten-t1:fig2.32b` |
| Entité | `ent:` + nom en minuscules sans accents | `ent:chondrosarcome-central` |

Une entité n'existe qu'une fois, même si elle relève de plusieurs domaines. Elle est alors répétée dans chaque `catalogue/entites/<domaine>.jsonl` concerné, avec un contenu identique.

## Structure

```
schema/taxonomie.json           domaines, régions, modalités, rôles, catégories (listes fermées)
schema/*.schema.json            un JSON Schema par type de fichier
scripts/                        ingestion, extraction, index, validation (Python, .venv/)
livres/<livre>/livre.json       métadonnées, chapitres, domaines, statistiques
livres/<livre>/passages/chNN.jsonl   1 ligne = 1 passage
livres/<livre>/figures/chNN.jsonl    1 ligne = 1 figure (un panneau = une ligne)
images/<livre>/lecture/<fig>.webp    ~1200 px
images/<livre>/vignettes/<fig>.webp  ~320 px
catalogue/manifeste.json        livres, version du corpus, statistiques, date
catalogue/entites/<domaine>.jsonl
index/<portee>/termes/<xx>.json      terme normalisé → [[id, fréquence, longueur]], portee = global ou un domaine
index/<portee>/legendes/<xx>.json
index/<portee>/<type>/_meta.json     nombre de documents et longueur moyenne (BM25)
apprentissage/<domaine>/<livre>/chNN.json   modules
```

Nom de fichier d'une image : identifiant de figure avec `:` remplacé par `_`, par exemple `images/cotten-t1/lecture/cotten-t1_fig2.32b.webp`.

Termes normalisés : minuscules, sans accents, découpés sur tout ce qui n'est pas lettre ou chiffre, mots vides français et anglais retirés. Le préfixe de 2 lettres est pris sur le terme normalisé (`_` complète les termes d'une lettre).

## Environnement

```
python3 -m venv .venv && .venv/bin/pip install pymupdf jsonschema imagehash pillow
```

Pour les scans : `brew install ocrmypdf tesseract tesseract-lang`.

## Procédure d'ajout d'un livre

Commande `/ajouter-livre` (voir `.claude/skills/ajouter-livre/SKILL.md`). Chaque étape est idempotente et relançable seule. En cas d'échec, rien n'est poussé. Un ajout raté s'annule avec `git revert`.

## Validation

```
.venv/bin/python scripts/valider.py
```

Doit passer sans erreur avant tout commit qui touche `livres/`, `catalogue/`, `index/`, `images/` ou `apprentissage/`.
