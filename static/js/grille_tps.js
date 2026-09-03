function echapperHtml(valeur) {
    return String(valeur ?? '').replace(/[&<>"']/g, caractere => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    }[caractere]));
}

document.addEventListener('DOMContentLoaded', () => {
    const formGrille = document.getElementById('form-grille');
    const loadingDiv = document.getElementById('loading');
    const resultatsDiv = document.getElementById('resultats');

    if (formGrille) {
        formGrille.addEventListener('submit', async (e) => {
            e.preventDefault();

            // Récupération des valeurs sélectionnées
            const anneeSelect = document.getElementById('annee');
            const typeQualifSelect = document.getElementById('type_qualif');
            const genreSelect = document.getElementById('genre');

            const annee = anneeSelect.value;
            const typeQualif = typeQualifSelect.value;
            const genre = genreSelect.value;

            // Libellés pour le titre récapitulatif
            const typeText = typeQualifSelect.options[typeQualifSelect.selectedIndex].text;
            const genreText = genreSelect.options[genreSelect.selectedIndex].text;

            // Affichage de l'état de chargement
            loadingDiv.style.display = 'block';
            loadingDiv.style.color = '#2563eb';
            loadingDiv.innerText = 'Chargement et vérification des données en cours...';
            resultatsDiv.style.display = 'none';

            try {
                const response = await fetch(`/api/grille?annee=${annee}&type_qualif=${typeQualif}&genre=${genre}`);
                const data = await response.json();

                // On vérifie data.success et la présence de la clé 'donnees'
                if (data.success && Array.isArray(data.donnees)) {
                    if (data.donnees.length === 0) {
                        loadingDiv.style.display = 'none';
                        resultatsDiv.innerHTML = '<p style="color: #64748b; padding: 1rem;">Aucune donnée disponible pour cette sélection.</p>';
                        resultatsDiv.style.display = 'block';
                        return;
                    }

                    afficherGrilleLigneParLigne(data.donnees, `${typeText} - ${genreText} (${annee})`);
                    loadingDiv.style.display = 'none';
                    resultatsDiv.style.display = 'block';
                } else {
                    loadingDiv.style.color = '#dc2626';
                    loadingDiv.innerText = "Erreur : " + (data.message || "Impossible de charger la grille.");
                }
            } catch (err) {
                console.error("Erreur Fetch:", err);
                loadingDiv.style.color = '#dc2626';
                loadingDiv.innerText = "Erreur de communication avec le serveur.";
            }
        });
    }

    /**
     * Transforme la liste de données plates [{epreuve, categorie, temps}, ...]
     * en un tableau croisé dynamique trié par nages et par catégories numériques.
     */
    function afficherGrilleLigneParLigne(donneesPlates, titreFormat) {
        // 1. Extraction des catégories uniques et des épreuves uniques
        const categoriesSet = new Set();
        const epreuvesSet = new Set();
        const matrice = Object.create(null); // Format : { '100 NL': { 'C1': '00:52.00', 'C2': '00:54.00' } }

        donneesPlates.forEach(item => {
            const epreuve = item.epreuve;
            const cat = item.categorie;
            const temps = item.temps;

            epreuvesSet.add(epreuve);
            categoriesSet.add(cat);

            if (!matrice[epreuve]) {
                matrice[epreuve] = Object.create(null);
            }
            matrice[epreuve][cat] = temps;
        });

        // 2. Tri numérique des catégories (ignore la lettre 'C')
        const categories = Array.from(categoriesSet).sort((a, b) => {
            const numA = parseInt(a.replace(/\D/g, ''), 10);
            const numB = parseInt(b.replace(/\D/g, ''), 10);

            if (!isNaN(numA) && !isNaN(numB)) {
                return numA - numB;
            }
            return a.localeCompare(b);
        });

        // 3. Tri personnalisé des épreuves par type de nage puis par distance
        const ordreNages = ['NL', 'Pap', 'Dos', 'Br', '4N'];

        const obtenirIndexNage = (epreuve) => {
            const index = ordreNages.findIndex(nage => new RegExp(`\\b${nage}\\b`, 'i').test(epreuve));
            return index !== -1 ? index : 99; // Placer en fin de tableau si nage inconnue
        };

        const epreuves = Array.from(epreuvesSet).sort((a, b) => {
            const indexNageA = obtenirIndexNage(a);
            const indexNageB = obtenirIndexNage(b);

            // Tri par ordre de la nage (NL -> Pap -> Dos -> Br -> 4N)
            if (indexNageA !== indexNageB) {
                return indexNageA - indexNageB;
            }

            // Si c'est la même nage, tri par distance croissante (50, 100, 200, 400...)
            const distA = parseInt(a.replace(/\D/g, ''), 10) || 0;
            const distB = parseInt(b.replace(/\D/g, ''), 10) || 0;

            return distA - distB;
        });

        // 4. Construction du tableau HTML moderne
        let html = `
            <h2 class="nageur-title">${echapperHtml(titreFormat)}</h2>
            <div class="table-responsive">
                <table class="modern-table">
                    <thead>
                        <tr>
                            <th>Epreuve / Nage</th>
                            ${categories.map(cat => `<th>${echapperHtml(cat)}</th>`).join('')}
                        </tr>
                    </thead>
                    <tbody>
        `;

        // 5. Remplissage des lignes par épreuve
        epreuves.forEach(epreuve => {
            html += `
                <tr>
                    <td class="nage">${echapperHtml(epreuve)}</td>
                    ${categories.map(cat => {
                        const temps = matrice[epreuve][cat] || '-';
                        return `<td class="time">${echapperHtml(temps)}</td>`;
                    }).join('')}
                </tr>
            `;
        });

        html += `
                    </tbody>
                </table>
            </div>
        `;

        resultatsDiv.innerHTML = html;
    }
});