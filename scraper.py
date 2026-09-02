import requests, re, json
from bs4 import BeautifulSoup
from models import db, TempsQualification, Nageur
from constants import nettoyer_epreuve
from sqlalchemy.dialects.sqlite import insert
from datetime import datetime

# ==========================================
# 1. FONCTIONS UTILITAIRES / HELPER
# ==========================================

def convertir_en_secondes(temps_str: str) -> float | None:
    if not temps_str or temps_str.strip() in ['--', '-', '']:
        return None
    clean = temps_str.strip()
    parts = clean.split(':')
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 1:
            return float(parts[0])
    except ValueError:
        return None
    return None

# Extrait le libellé court (C1, C2,...,C14) à partir de la catégorie brute scrapée
def extraire_libelle_court_categorie(cat_brute: str) -> str:
    
    if not cat_brute:
        return ""
    
    clean = cat_brute.strip()
    
    # Cas particulier des C14
    if "90 ans" in clean or "90ans" in clean:
        return "C14"
    
    # Recherche 'C' suivi d'un ou plusieurs chiffres (ex: C1, C12)
    match = re.search(r'\b(C\d+)\b', clean, re.IGNORECASE)
    
    if match:
        return match.group(1).upper()
    
    # Si aucun motif n'est trouvé, on nettoie simplement le texte d'origine
    return clean

# Extraction des infos (nom, prénom, genre, année de naissance à partir de la donnée brute HTML scrapée)
def extraire_infos_nageur(td_nageur):

    infos = {
        "nom_prenom": None,
        "annee_naissance": None,
        "genre": None,
        "licence": None
    }

    if not td_nageur or "Championnats de France" in td_nageur.text:
        return infos

    # 1. Extraction du genre via la classe de l'icône <i>
    icone_genre = td_nageur.find('i')
    if icone_genre:
        classes = icone_genre.get('class', [])
        classes_str = ' '.join(classes) if isinstance(classes, list) else str(classes)
        
        if 'fa-venus' in classes_str:
            infos["genre"] = "F"
        elif 'fa-mars' in classes_str:
            infos["genre"] = "H"

    # 2. Extraction du numéro de licence dans le dernier <span> (format [XXXXXX])
    spans = td_nageur.find_all('span')
    
    for span in spans:
        texte_span = span.text.strip()
        
        # Recherche du numéro de licence entre crochets [1234567]
        match_licence = re.search(r'\[(\d+)\]', texte_span)
        if match_licence:
            # Conversion en entier (ex: "0123456" -> 123456)
            infos["licence"] = int(match_licence.group(1))
            continue

        # Extraction du nom/prénom et de l'année de naissance
        # Exemple de texte : "1. DUPONT Jean (1985 / 41 ans)" ou "DUPONT Jean (1985 / 41 ans)"
        match_nom_annee = re.search(r'^(?:\d+\.\s*)?(.+?)\s*\((?:ans\s*)?(\d{4})', texte_span)
        if match_nom_annee:
            infos["nom_prenom"] = match_nom_annee.group(1).strip()
            infos["annee_naissance"] = int(match_nom_annee.group(2))
        elif not infos["nom_prenom"] and not texte_span.startswith('['):
            # Fallback si le format entre parenthèses diffère légèrement
            # On nettoie le numéro de classement éventuel ("1. ")
            clean_text = re.sub(r'^\d+\.\s*', '', texte_span)
            infos["nom_prenom"] = clean_text

    return infos

# ==========================================
# 2. SCRAPING DES GRILLES DE TEMPS DE QUALIF
# ==========================================

def scraper_et_enregistrer_temps(annee: str, type_qualif: str, genre: str, force_refresh: bool = False):
    # 1. Anti-surcharge : Vérification en base de données SQLite
    if not force_refresh:
        stmt_exists = db.select(
            db.select(TempsQualification)
            .filter_by(annee=annee, type_qualif=type_qualif, genre=genre)
            .exists()
        )
        deja_en_base = db.session.execute(stmt_exists).scalar()

        if deja_en_base:
            stmt_get = db.select(TempsQualification).filter_by(annee=annee, type_qualif=type_qualif, genre=genre)
            return list(db.session.execute(stmt_get).scalars().all())

    # 2. Requête Web
    url = f"https://ffn.extranat.fr/webffn/mtr_perfs.php?idact=mtr&go=clt_tps&idsai={annee}&idclt={type_qualif}&idsex={genre}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, 'html.parser')
        tbodies = soup.find_all(['thead', 'tbody'])
        
        if not tbodies:
            return None

        objets_temps = []
        bassin_defaut = 25 if type_qualif in ("85","87")  else 50
        bassin_courant = bassin_defaut

        # 3. Parcours de chaque bloc <tbody>
        for tbody in tbodies:
            # Détection de la spécificité du bassin dans le texte du tbody
            texte_tbody = tbody.text.strip()
            if "exclusivement en bassin de 50" in texte_tbody:
                bassin_courant = 50
            elif "exclusivement en bassin de 25" in texte_tbody:
                bassin_courant = 25

            lignes = tbody.find_all('tr')
            if not lignes:
                continue

            # Extraction des catégories dans la première ligne du tbody
            premiere_ligne = lignes[0]
            cellules_entete = premiere_ligne.find_all(['td', 'th'])
            
            categories_du_tbody = [
                extraire_libelle_court_categorie(c.text) 
                for c in cellules_entete[1:] 
                if c.text.strip()
            ]

            lignes_epreuves = lignes[1:]
            
            for ligne in lignes_epreuves:
                cellules = ligne.find_all('td')
                if not cellules:
                    continue

                mots_cles = ["Nage Libre", "Dos", "Brasse", "Papillon", "4 Nages"]
                nom_epreuve_brut = cellules[0].text.strip()

                if any(mot in nom_epreuve_brut for mot in mots_cles):
                    # 1. Normalisation du nom de l'épreuve
                    nom_epreuve_clean = nettoyer_epreuve(nom_epreuve_brut)

                    cellules_temps = cellules[1:]

                    for idx, cell in enumerate(cellules_temps):
                        valeur_temps = cell.text.strip()

                        if idx < len(categories_du_tbody):
                            cat_nom = categories_du_tbody[idx]
                        else:
                            cat_nom = f"C{idx + 1}"

                        temps_sec = convertir_en_secondes(valeur_temps)

                        # 3. Instanciation avec des libellés propres
                        tps_obj = TempsQualification(
                            annee=str(annee),
                            type_qualif=str(type_qualif),
                            genre=str(genre),
                            epreuve=nom_epreuve_clean,
                            bassin=int(bassin_courant),
                            categorie=cat_nom,
                            temps=valeur_temps,
                            temps_en_sec=temps_sec
                        )
                        objets_temps.append(tps_obj)

        # 4. Insertion / Mise à jour dans SQLite via Upsert
        if objets_temps:
            valeurs = [
                {
                    'annee': item.annee,
                    'type_qualif': item.type_qualif,
                    'genre': item.genre,
                    'epreuve': item.epreuve,
                    'bassin': item.bassin,
                    'categorie': item.categorie,
                    'temps': item.temps,
                    'temps_en_sec': item.temps_en_sec
                }
                for item in objets_temps
            ]

            with db.session.no_autoflush:
                stmt = insert(TempsQualification).values(valeurs)
                stmt_upsert = stmt.on_conflict_do_update(
                    index_elements=['annee', 'categorie', 'genre', 'epreuve', 'type_qualif', 'bassin'],
                    set_={
                        'temps': stmt.excluded.temps,
                        'temps_en_sec': stmt.excluded.temps_en_sec
                    }
                )
                db.session.execute(stmt_upsert)
                db.session.commit()

            return objets_temps

    except Exception as e:
        db.session.rollback()
        print(f"Erreur scraping / enregistrement : {e}")
        return None

    return None

    # ==========================================
    # 3. SCRAPING DES QUALIFIÉS D'UN CLUB
    # ==========================================
def obtenir_qualifies_club(annee: str = None, id_club: str = "375"):
    
    if annee is None:
        annee = str(datetime.now().year)
    
    url = f"https://ffn.extranat.fr/webffn/mtr_perfs.php?idact=mtr&go=clt&idsai={annee}&idtrt=str&idrch_id={id_club}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"Erreur HTTP {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table')
        
        if not table:
            print("Aucun tableau de résultats trouvé sur la page.")
            return []

        qualifies = []
        lignes = table.find_all('tr')

        for ligne in lignes:
            cellules = ligne.find_all('td')
            if not cellules:
                continue

            td_nageur = cellules[0]
            texte_td = td_nageur.text.strip()
            
            # Ignorer la ligne si elle contient l'intitulé des championnats
            if "Championnats de France" in texte_td:
                continue

            # On vérifie que la cellule contient bien les éléments d'un nageur
            if td_nageur.find('span'):
                nageur_info = extraire_infos_nageur(td_nageur)
                
                # Sécurité supplémentaire : ignorer si aucun nom n'est extrait ou s'il s'agit d'un titre
                if not nageur_info["nom_prenom"] or "Championnats de France" in nageur_info["nom_prenom"]:
                    continue

                qualifies.append({
                    "nom_prenom": nageur_info["nom_prenom"],
                    "annee_naissance": nageur_info["annee_naissance"],
                    "genre": nageur_info["genre"],
                    "licence": nageur_info["licence"]
                })

        return qualifies

    except Exception as e:
        print(f"Erreur lors du scraping des qualifiés : {e}")
        return []
    
# Enregistrement des nageurs en base de donnée    
def enregistrer_nageurs_bdd(liste_nageurs: list) -> int:

    if not liste_nageurs:
        return 0

    valeurs = []
    for n in liste_nageurs:
        if n.get("licence") is None:
            continue

        valeurs.append({
            'licence': int(n['licence']),  # S'assure du format entier
            'nom_prenom': n['nom_prenom'],
            'annee_naissance': n['annee_naissance'],
            'genre': n['genre']
        })

    if not valeurs:
        return 0

    try:
        with db.session.no_autoflush:
            stmt = insert(Nageur).values(valeurs)
            
            stmt_upsert = stmt.on_conflict_do_update(
                index_elements=['licence'],
                set_={
                    'nom_prenom': stmt.excluded.nom_prenom,
                    'annee_naissance': stmt.excluded.annee_naissance,
                    'genre': stmt.excluded.genre
                }
            )
            db.session.execute(stmt_upsert)
            db.session.commit()
            return len(valeurs)

    except Exception as e:
        db.session.rollback()
        print(f"Erreur d'enregistrement BDD : {e}")
        return 0