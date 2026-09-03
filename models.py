from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

# Définition de la table dans la base de données
class TempsQualification(db.Model):
    
    __tablename__ = 'tps_qualif'
    
    id = db.Column(db.Integer, primary_key=True)
    annee = db.Column(db.String(4), nullable=False) #Année de validité du temps de qualification
    type_qualif = db.Column(db.String(2), nullable=False) # 84=N1 bassin 50m, 85=N1 bassin 25m, 86=N2 bassin 50m, 87=N2 bassin 25m
    genre = db.Column(db.String(1), nullable=False) # 1=messieurs, 2=dames
    epreuve = db.Column(db.String(100), nullable=False)
    bassin = db.Column(db.Integer, nullable=False)  # 25 ou 50
    categorie = db.Column(db.String(5), nullable=False)  # C1, C2..., C14
    temps = db.Column(db.String(20), nullable=True) #temps de qualification
    temps_en_sec = db.Column(db.Float, nullable=True) #temps de qualification en secondes
    
    # Contrainte d'unicité pour éviter les doublons lors du re-scraping
    __table_args__ = (
        db.Index(
            'ix_tps_qualif_annee_type_genre',
            'annee', 'type_qualif', 'genre'
        ),
        db.UniqueConstraint(
            'annee', 'categorie', 'genre', 'epreuve', 'type_qualif', 'bassin',
            name='uix_grid_entry'
        ),
    )
    
class Nageur(db.Model):
    __tablename__ = 'nageur'

    licence = db.Column(db.Integer, primary_key=True, autoincrement=False)
    nom_prenom = db.Column(db.String(100), nullable=False)
    annee_naissance = db.Column(db.Integer, nullable=False)
    genre = db.Column(db.String(1), nullable=False)  # 'H' ou 'F'
    
    @property
    def categorie(self) -> str:
        
        if not self.annee_naissance:
            return ""

        aujourdhui = datetime.now()
        
        # Si on est entre septembre et décembre, on est déjà sur la saison de l'année suivante
        if aujourdhui.month >= 9:
            annee_saison = aujourdhui.year + 1
        else:
            annee_saison = aujourdhui.year

        age = annee_saison - self.annee_naissance

        # Moins de 25 ans
        if age < 25:
            return "C0"
        
        # 90 ans et plus
        if age >= 90:
            return "C14"

        # De C1 à C13 (tranches de 5 ans : 25-29=C1, 30-34=C2, etc.)
        code_cat = 1 + (age - 25) // 5
        return f"C{code_cat}"
    
    # Sérialisation de l'objet Nageur
    def to_dict(self):
        return {
            'licence': self.licence,
            'nom_prenom': self.nom_prenom,
            'annee_naissance': self.annee_naissance,
            'genre': self.genre,
            'categorie': self.categorie,
        }