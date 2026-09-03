from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_caching import Cache
from models import db, TempsQualification, Nageur
from constants import nettoyer_epreuve
from scraper import scraper_et_enregistrer_temps, obtenir_qualifies_club, enregistrer_nageurs_bdd, convertir_en_secondes
from extranatapi import Wrapper
import os
import json
from math import ceil
from threading import Lock
from time import monotonic

app = Flask(__name__)

# 1. Définition des chemins absolus
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# 2. Création automatique d'un dossier 'instance' dédié à la BDD
INSTANCE_PATH = os.path.join(BASE_DIR, 'instance')
os.makedirs(INSTANCE_PATH, exist_ok=True)

# 3. Path absolu de la base de données
DB_PATH = os.path.join(INSTANCE_PATH, 'natation.db')

# 4. Configuration Flask / SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# 5. Initialisation automatique des tables si la BDD est neuve
with app.app_context():
    db.create_all()

# Configuration du cache (en mémoire vive)
app.config['CACHE_TYPE'] = 'SimpleCache'
app.config['CACHE_DEFAULT_TIMEOUT'] = 3600  # Durée de conservation : 1 heure (en secondes)
app.config['SCRAPING_MIN_INTERVAL'] = 300  # Délai minimal entre deux scrapes (5 minutes)

cache = Cache(app)
scraping_lock = Lock()
dernier_scraping_at = 0.0

def get_annee_saison_courante() -> str:
    """Retourne l'année de la saison sous forme de chaîne (ex: '2026')."""
    aujourdhui = datetime.now()
    annee = aujourdhui.year + 1 if aujourdhui.month >= 9 else aujourdhui.year
    return str(annee)

def charger_minima_qualif(annee, genre_db, epreuves, categorie, types_qualif):
    """Charge en une fois les minima nécessaires au résumé d'un nageur."""
    stmt = db.select(TempsQualification).where(
        TempsQualification.annee == str(annee),
        TempsQualification.genre == genre_db,
        TempsQualification.epreuve.in_(epreuves),
        TempsQualification.categorie == categorie,
        TempsQualification.type_qualif.in_(types_qualif),
    )
    minima = {}
    for minimum in db.session.execute(stmt).scalars():
        cle = (
            minimum.epreuve,
            minimum.bassin,
            minimum.categorie,
            minimum.type_qualif,
        )
        minima[cle] = minimum.temps or '-'
    return minima

def obtenir_derniere_annee_qualif(annee_max):
    return db.session.execute(
        db.select(TempsQualification.annee)
        .where(TempsQualification.annee <= str(annee_max))
        .order_by(TempsQualification.annee.desc())
        .limit(1)
    ).scalar_one_or_none() or str(annee_max)

def normaliser_bassin(bassin):
    bassin_str = str(bassin).replace('m', '').strip()
    return int(bassin_str) if bassin_str.isdigit() else None

def est_qualifie(performances, minima):
    for minimum in minima:
        temps_minimum = convertir_en_secondes(minimum['temps'])
        if temps_minimum is None:
            continue

        for performance in performances:
            if normaliser_bassin(performance['bassin']) != minimum['bassin']:
                continue
            temps_performance = convertir_en_secondes(performance['temps'])
            if temps_performance is not None and temps_performance <= temps_minimum:
                return True

    return False

@app.route('/')
def afficher_nageurs():
    # Récupération des nageurs déjà enregistrés en BDD
    nageurs = Nageur.query.order_by(Nageur.nom_prenom).all()
    return render_template('index.html', nageurs=nageurs)

@app.route('/grille_tps')
def grille_tps():
    saison_courante = int(get_annee_saison_courante())
    annees_grille = [
        (saison_courante, f'Saison {saison_courante} (en cours)'),
        (saison_courante - 1, f'Saison {saison_courante - 1} (précédente)')
    ]

    return render_template('grille_tps.html', annees_grille=annees_grille)

# ==========================================
# API
# ==========================================

@app.route('/api/scraper-nageurs', methods=['POST'])
def lancer_scraping_nageurs():
    """Route API appelée par le frontend pour lancer le scraping."""
    global dernier_scraping_at

    if not scraping_lock.acquire(blocking=False):
        return jsonify({
            'success': False,
            'erreur': 'Une mise à jour est déjà en cours.'
        }), 429

    try:
        maintenant = monotonic()
        delai_restant = app.config['SCRAPING_MIN_INTERVAL'] - (maintenant - dernier_scraping_at)
        if delai_restant > 0:
            return jsonify({
                'success': False,
                'erreur': 'Mise à jour trop fréquente.',
                'retry_after': ceil(delai_restant),
            }), 429

        dernier_scraping_at = maintenant

        # 1. Scraping sur Extranat
        donnees_scrapees = obtenir_qualifies_club()
        
        # 2. Enregistrement / mise à jour en BDD (sans doublons)
        nb_enregistres = enregistrer_nageurs_bdd(donnees_scrapees)

        # Les résumés peuvent dépendre des données fraîchement mises à jour.
        cache.clear()
        
        # 3. Récupération de la liste à jour
        nageurs = Nageur.query.order_by(Nageur.nom_prenom).all()
        
        # Formatage pour la réponse JSON
        liste_json = [n.to_dict() for n in nageurs]

        return jsonify({
            'success': True,
            'message': f"{len(donnees_scrapees)} nageurs récupérés, {nb_enregistres} enregistrés/mis à jour.",
            'nageurs': liste_json
        })

    except Exception as e:
        return jsonify({'success': False, 'erreur': str(e)}), 500
    finally:
        scraping_lock.release()

@app.route('/api/grille', methods=['GET'])
def get_grille():
    # Récupération des données envoyées dans l'URL (ex: /api/grille?annee=2026&type_qualif=84&genre=1)
    annee = request.args.get('annee')
    type_qualif = request.args.get('type_qualif')
    genre = request.args.get('genre')

    if not all([annee, type_qualif, genre]):
        return jsonify({
            'success': False,
            'message': 'Paramètres manquants (annee, type_qualif et genre sont requis).'
        }), 400

    # Exécution du scraping / lecture en BDD
    resultats = scraper_et_enregistrer_temps(annee, type_qualif, genre)

    if resultats is None:
        return jsonify({
            'success': False,
            'message': 'Erreur lors de la récupération des données.'
        }), 500

    # Transformation des objets SQLAlchemy en liste de dictionnaires pour le JSON
    donnees_json = []
    for item in resultats:
        donnees_json.append({
            'epreuve': item.epreuve,
            'bassin': item.bassin,
            'categorie': item.categorie,
            'temps': item.temps,
            'temps_en_sec': item.temps_en_sec
        })

    return jsonify({
        'success': True,
        'donnees': donnees_json
    }), 200

@app.route('/api/nageur/<int:iuf>/summary', methods=['GET'])
@cache.cached(timeout=3600, key_prefix=lambda: request.url)
def get_nageur_summary(iuf):
    try:
        # 1. Récupération du nageur en BDD pour connaître son genre et sa catégorie
        nageur_db = db.session.get(Nageur, iuf)
        if not nageur_db:
            return (
                jsonify({
                    'error': 'Nageur non trouvé en base de données local'
                }),
                404,
            )

        # Conversion du genre pour la table tps_qualif ('H' -> '1', 'F' -> '2')
        genre_qualif = '1' if nageur_db.genre == 'H' else '2'
        categorie_qualif = nageur_db.categorie
        annee_saison = int(obtenir_derniere_annee_qualif(get_annee_saison_courante()))

        # Définition du seuil : saison courante et les 2 précédentes (ex: 2026, 2025, 2024)
        saison_min = annee_saison - 2

        # 2. Scraping Extranat via le Wrapper
        wrapper = Wrapper(showprogress=False)
        obj_mpp = wrapper.get_nageur_mpp(iuf)
        obj_all = wrapper.get_nageur_all(iuf)

        if obj_mpp is None or obj_all is None:
            return jsonify({'error': 'Nageur introuvable sur Extranat'}), 404

        epreuves = {nettoyer_epreuve(mpp.name) for mpp in obj_mpp.nages}
        minima_qualif = charger_minima_qualif(
            annee=annee_saison,
            genre_db=genre_qualif,
            epreuves=epreuves,
            categorie=categorie_qualif,
            types_qualif=('84', '85', '86', '87'),
        )

        performances_par_nage_bassin = {}
        for n in obj_all.nages:
            if isinstance(n.date, str):
                annee_perf = int(n.date.split('/')[-1])
            elif hasattr(n.date, 'year'):
                annee_perf = n.date.year
            else:
                annee_perf = 0

            if annee_perf < saison_min:
                continue

            performance = {
                'temps': n.temps,
                'points': n.points,
                'date': n.date,
                'annee': annee_perf,
                'bassin': normaliser_bassin(n.bassin),
            }
            cle = (n.name, performance['bassin'])
            performances_par_nage_bassin.setdefault(cle, []).append(performance)

        summary_data = []

        for mpp in obj_mpp.nages:
            bassin_int = normaliser_bassin(mpp.bassin) or 25

            # Codes qualification selon le bassin
            code_n1 = '85' if bassin_int == 25 else '84'
            code_n2 = '87' if bassin_int == 25 else '86'
            qualification_multi_bassin = code_n1 == '84' or code_n2 == '86'

            # Les qualifications 50 m prennent en compte les performances des deux bassins.
            historique_filtre = performances_par_nage_bassin.get((mpp.name, bassin_int), [])
            if qualification_multi_bassin:
                performances_qualification = [
                    performance
                    for (nom_nage, _), performances in performances_par_nage_bassin.items()
                    if nom_nage == mpp.name
                    for performance in performances
                ]
            else:
                performances_qualification = historique_filtre

            # requêtes SQL sur la table tps_qualif
            def charger_minima(type_qualif_code):
                bassins = (25, 50) if type_qualif_code in ('84', '86') else (bassin_int,)
                return [
                    {
                        'bassin': bassin,
                        'temps': temps,
                        'qualifie': est_qualifie(performances_qualification, [
                            {'bassin': bassin, 'temps': temps}
                        ]),
                    }
                    for bassin in bassins
                    for temps in [minima_qualif.get((
                            nettoyer_epreuve(mpp.name),
                            bassin,
                            categorie_qualif,
                            type_qualif_code,
                        ), '-')]
                ]

            t_n1 = charger_minima(code_n1)
            t_n2 = charger_minima(code_n2)

            summary_data.append({
                'nage': mpp.name,
                'bassin': mpp.bassin,
                'mpp': {
                    'temps': mpp.temps,
                    'points': mpp.points,
                    'date': mpp.date,
                },
                'perfs_trois_saisons': historique_filtre,
                'perfs_qualification': performances_qualification,
                'minima_n1': t_n1,
                'minima_n2': t_n2,
                'qualification_n1': est_qualifie(performances_qualification, t_n1),
                'qualification_n2': est_qualifie(performances_qualification, t_n2),
            })

        return (
            jsonify({
                'iuf': iuf,
                'nom_prenom': nageur_db.nom_prenom,
                'genre': nageur_db.genre,
                'categorie': categorie_qualif,
                'saison': annee_saison,
                'performances': summary_data,
            }),
            200,
        )

    except Exception as e:
        app.logger.error(f'Erreur lors du calcul du summary pour {iuf} : {e}')
        return jsonify({'error': str(e)}), 500
    
with app.app_context():
  db.create_all()

if __name__ == '__main__':
    app.run(debug=True)