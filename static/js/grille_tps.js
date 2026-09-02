// Écoute de l'événement de soumission du formulaire
document.getElementById('form-grille').addEventListener('submit', async function (e) {
    e.preventDefault(); // Empêche le rechargement standard de la page HTML

    const annee = document.getElementById('annee').value;
    const typeQualif = document.getElementById('type_qualif').value;
    const genre = document.getElementById('genre').value;

    const loadingDiv = document.getElementById('loading');
    const resultatsDiv = document.getElementById('resultats');

    loadingDiv.style.display = 'block';
    resultatsDiv.innerHTML = '';

    try {
        // Appel vers la route Flask /api/grille avec les paramètres du formulaire
        const response = await fetch(`/api/grille?annee=${annee}&type_qualif=${typeQualif}&genre=${genre}`);
        const data = await response.json();

        loadingDiv.style.display = 'none';

        if (data.success && data.donnees.length > 0) {
            // Construction dynamique du tableau HTML
            let html = '<table><thead><tr><th>Épreuve</th><th>Bassin</th><th>Catégorie</th><th>Temps</th></tr></thead><tbody>';

            data.donnees.forEach(row => {
                html += `<tr>
                        <td>${row.epreuve}</td>
                        <td>${row.bassin}m</td>
                        <td>${row.categorie}</td>
                        <td><strong>${row.temps}</strong></td>
                    </tr>`;
            });

            html += '</tbody></table>';
            resultatsDiv.innerHTML = html;
        } else {
            resultatsDiv.innerHTML = `<p style="color:red;">${data.message || 'Aucune donnée trouvée.'}</p>`;
        }
    } catch (error) {
        loadingDiv.style.display = 'none';
        resultatsDiv.innerHTML = '<p style="color:red;">Erreur de connexion au serveur Flask.</p>';
        console.error(error);
    }
});