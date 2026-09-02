# Correspondance des épreuves
EPREUVES_MAP = {
    "50 Nage Libre": "50 NL",
    "100 Nage Libre": "100 NL",
    "200 Nage Libre": "200 NL",
    "400 Nage Libre": "400 NL",
    "800 Nage Libre": "800 NL",
    "1500 Nage Libre": "1500 NL",
    "50 Dos": "50 Dos",
    "100 Dos": "100 Dos",
    "200 Dos": "200 Dos",
    "50 Bra." : "50 Br",
    "50 Brasse": "50 Br",
    "100 Bra." : "100 Br",
    "100 Brasse": "100 Br",
    "200 Bra." : "200 Br",
    "200 Brasse": "200 Br",
    "50 Pap." : "50 Pap",
    "50 Papillon": "50 Pap",
    "100 Pap." : "100 Pap",
    "100 Papillon": "100 Pap",
    "200 Pap." : "200 Pap",
    "200 Papillon": "200 Pap",
    "100 4 N.": "100 4N",
    "100 4 Nages": "100 4N",
    "200 4 N.": "200 4N",
    "200 4 Nages": "200 4N",
    "400 4 N.": "400 4N",
    "400 4 Nages": "400 4N"
}

def nettoyer_epreuve(libelle_brut: str) -> str:
    clean = libelle_brut.strip()
    # Recherche exacte dans le dictionnaire, sinon conserve le texte propre d'origine
    return EPREUVES_MAP.get(clean, clean)