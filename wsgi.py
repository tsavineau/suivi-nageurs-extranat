import sys
import os

# 1. Obtenir le chemin absolu du dossier contenant ce fichier (racine du projet)
project_dir = os.path.dirname(os.path.abspath(__file__))

# 2. Ajouter le dossier du projet en tête du PATH Python s'il n'y est pas déjà
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

# 3. Importer l'instance Flask depuis app.py et l'exposer sous le nom 'application'
from app import app as application