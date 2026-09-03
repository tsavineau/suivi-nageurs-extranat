from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_caching import Cache
from models import db, TempsQualification, Nageur
from constants import nettoyer_epreuve
from scraper import scraper_et_enregistrer_temps, obtenir_qualifies_club, enregistrer_nageurs_bdd
from extranatapi import Wrapper
import os
import json

app = Flask(__name__)

# Définition d'un chemin absolu vers le fichier SQLite dans le dossier du projet
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(
    BASE_DIR, 'database.db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Configuration du cache (en mémoire vive)
app.config['CACHE_TYPE'] = 'SimpleCache'
app.config['CACHE_DEFAULT_TIMEOUT'] = 3600  # Durée de conservation : 1 heure (en secondes)

cache = Cache(app)

def get_annee_saison_courante() -> str:
    """Retourne l'année de la saison sous forme de chaîne (ex: '2026')."""
    aujourdhui = datetime.now()
    annee = aujourdhui.year + 1 if aujourdhui.month >= 9 else aujourdhui.year
    return str(annee)

def chercher_temps_qualif(annee, genre_db, epreuve, bassin, categorie, type_qualif_code):
    """Recherche un temps de qualification (compatible SQLAlchemy 2.0)."""
    try:
        bassin_int = int(str(bassin).replace('m', '').strip())
    except (ValueError, TypeError):
        return '-'

    # Requête construite avec db.select()
    stmt = db.select(TempsQualification).filter_by(
        annee=2026,
        genre=genre_db,
        epreuve=epreuve,
        bassin=bassin_int,
        categorie=categorie,
        type_qualif=str(type_qualif_code)
    )
    
    enregistrement = db.session.execute(stmt).scalar_one_or_none()

    return enregistrement.temps if enregistrement and enregistrement.temps else '-'

@app.route('/')
def afficher_nageurs():
    # Récupération des nageurs déjà enregistrés en BDD
    nageurs = Nageur.query.order_by(Nageur.nom_prenom).all()
    return render_template('index.html', nageurs=nageurs)

@app.route('/grille_tps')
def index():
    return render_template('grille_tps.html')

# ==========================================
# API
# ==========================================

@app.route('/api/scraper-nageurs', methods=['POST'])
def lancer_scraping_nageurs():
    """Route API appelée par le frontend pour lancer le scraping."""
    try:
        # 1. Scraping sur Extranat
        donnees_scrapees = obtenir_qualifies_club()
        
        # 2. Enregistrement / mise à jour en BDD (sans doublons)
        nb_enregistres = enregistrer_nageurs_bdd(donnees_scrapees)
        
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
        annee_saison = int(get_annee_saison_courante())

        # Définition du seuil : saison courante et les 2 précédentes (ex: 2026, 2025, 2024)
        saison_min = annee_saison - 2

        # 2. Scraping Extranat via le Wrapper
        wrapper = Wrapper(showprogress=False)
        obj_mpp = wrapper.get_nageur_mpp(iuf)
        obj_all = wrapper.get_nageur_all(iuf)

        if obj_mpp is None or obj_all is None:
            return jsonify({'error': 'Nageur introuvable sur Extranat'}), 404

        summary_data = []

        for mpp in obj_mpp.nages:
            bassin_str = str(mpp.bassin).replace('m', '').strip()
            bassin_int = int(bassin_str) if bassin_str.isdigit() else 25

            # Codes qualification selon le bassin
            code_n1 = '85' if bassin_int == 25 else '84'
            code_n2 = '87' if bassin_int == 25 else '86'

            # Filtrer toutes les performances de la même nage/bassin réalisées lors des 3 dernières saisons
            historique_filtre = []
            for n in obj_all.nages:
                if n.name == mpp.name and n.bassin == mpp.bassin:
                    # Extraction de l'année de la perf (gère un objet datetime ou un string "DD/MM/YYYY")
                    if isinstance(n.date, str):
                        annee_perf = int(n.date.split('/')[-1])
                    elif hasattr(n.date, 'year'):
                        annee_perf = n.date.year
                    else:
                        annee_perf = 0

                    if annee_perf >= saison_min:
                        historique_filtre.append({
                            'temps': n.temps,
                            'points': n.points,
                            'date': n.date,
                            'annee': annee_perf,
                        })

            # Recommandation : requêtes SQL sur la table tps_qualif
            t_n1 = chercher_temps_qualif(
                annee=annee_saison,
                genre_db=genre_qualif,
                epreuve=nettoyer_epreuve(mpp.name),
                bassin=bassin_int,
                categorie=categorie_qualif,
                type_qualif_code=code_n1,
            )

            t_n2 = chercher_temps_qualif(
                annee=annee_saison,
                genre_db=genre_qualif,
                epreuve=nettoyer_epreuve(mpp.name),
                bassin=bassin_int,
                categorie=categorie_qualif,
                type_qualif_code=code_n2,
            )

            summary_data.append({
                'nage': mpp.name,
                'bassin': mpp.bassin,
                'mpp': {
                    'temps': mpp.temps,
                    'points': mpp.points,
                    'date': mpp.date,
                },
                'perfs_trois_saisons': historique_filtre,
                'minima_n1': t_n1,
                'minima_n2': t_n2,
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