async function lancerScraping() {
  const btn = document.getElementById('btnScrape');
  const status = document.getElementById('statusMessage');
  const selectNageur = document.getElementById('selectNageur');

  // Blocage du bouton pendant la requête
  btn.disabled = true;
  status.style.color = 'black';
  status.innerText = "Récupération en cours depuis Extranat...";

  try {
    const response = await fetch('/api/scraper-nageurs', { method: 'POST' });
    const data = await response.json();

    if (data.success) {
      status.style.color = 'green';
      status.innerText = data.message;

      // Sauvegarde du nageur actuellement sélectionné
      const currentSelectedIuf = selectNageur.value;

      // Réinitialisation du menu déroulant <select>
      selectNageur.innerHTML = '<option value="">-- Choisir un nageur --</option>';

      // Reconstruction dynamique des options du <select>
      if (data.nageurs && data.nageurs.length > 0) {
        data.nageurs.forEach(n => {
          const option = document.createElement('option');
          option.value = n.licence;
          option.textContent = `${n.nom_prenom}${n.categorie ? ` (${n.categorie})` : ''}`;
          selectNageur.appendChild(option);
        });

        // Restauration de la sélection précédente si elle existe toujours
        if (currentSelectedIuf) {
          selectNageur.value = currentSelectedIuf;
        }
      }
    } else {
      status.style.color = 'red';
      status.innerText = "Erreur : " + (data.erreur || data.message || "Échec du scraping");
    }
  } catch (err) {
    status.style.color = 'red';
    status.innerText = "Erreur de communication avec le serveur.";
  } finally {
    btn.disabled = false;
  }
}

// Helper pour convertir un temps "MM:SS.ss" ou "SS.ss" en secondes si non fourni par l'API
function convertirTempsEnSecondes(tempsStr) {
  if (!tempsStr || tempsStr === '-') return null;
  const parties = tempsStr.split(':');
  if (parties.length === 2) {
    return parseFloat(parties[0]) * 60 + parseFloat(parties[1]);
  }
  return parseFloat(parties[0]);
}

// Vérifie si au moins une performance de la liste égale ou bat le temps de qualification
function estQualifie(listePerfs, minimaStr) {
  if (!minimaStr || minimaStr === '-' || !listePerfs || listePerfs.length === 0) {
    return false;
  }
  
  const minimaSec = convertirTempsEnSecondes(minimaStr);
  if (minimaSec === null) return false;

  return listePerfs.some(perf => {
    const tempsSec = convertirTempsEnSecondes(perf.temps);
    return tempsSec !== null && tempsSec <= minimaSec;
  });
}

// Helper pour formater la valeur de l'écart en secondes
function formaterEcart(ecartSec) {
  if (ecartSec <= 0) return '';
  if (ecartSec >= 60) {
    const min = Math.floor(ecartSec / 60);
    const sec = (ecartSec % 60).toFixed(2).padStart(5, '0');
    return ` (+${min}:${sec})`;
  }
  return ` (+${ecartSec.toFixed(2)})`;
}

// Helper d'affichage pour les colonnes de minima
function genererCelluleMinima(listePerfs, minimaStr) {
  if (!minimaStr || minimaStr === '-') return '-';

  const qualifie = estQualifie(listePerfs, minimaStr);

  if (qualifie) {
    return `${minimaStr} <span class="badge-success">✓</span>`;
  }

  // S'il n'y a pas de performances enregistrées dans la liste, on n'affiche aucun écart
  if (!listePerfs || listePerfs.length === 0) {
    return `${minimaStr} <span class="badge-danger">✗</span>`;
  }

  // Calcul du meilleur temps réalisé parmi les perfs disponibles
  const tempsSecList = listePerfs
    .map(p => convertirTempsEnSecondes(p.temps))
    .filter(t => t !== null);

  if (tempsSecList.length === 0) {
    return `${minimaStr} <span class="badge-danger">✗</span>`;
  }

  const meilleurTemps = Math.min(...tempsSecList);
  const minimaSec = convertirTempsEnSecondes(minimaStr);

  if (minimaSec === null) {
    return `${minimaStr} <span class="badge-danger">✗</span>`;
  }

  const ecartSec = meilleurTemps - minimaSec;
  const strEcart = formaterEcart(ecartSec);

  return `${minimaStr} <span class="badge-danger">✗</span><span class="ecart-time">${strEcart}</span>`;
}

document.addEventListener('DOMContentLoaded', () => {
  const selectNageur = document.getElementById('selectNageur');
  const sectionPerf = document.getElementById('section-performances');
  const bodyPerf = document.getElementById('body-performances');
  const titreNageur = document.getElementById('titre-nageur');

  selectNageur.addEventListener('change', async () => {
    const iuf = selectNageur.value;
    if (!iuf) {
      sectionPerf.style.display = 'none';
      return;
    }

    selectNageur.disabled = true;

    try {
      const response = await fetch(`/api/nageur/${iuf}/summary`);
      if (!response.ok) throw new Error(`Erreur ${response.status}`);

      const data = await response.json();
      bodyPerf.innerHTML = '';

      if (!data.performances || data.performances.length === 0) {
        bodyPerf.innerHTML = '<tr><td colspan="5">Aucune performance trouvée.</td></tr>';
      } else {
        let bassinActuel = null;

        data.performances.forEach(item => {
          // Séparateur de bassin
          if (item.bassin !== bassinActuel) {
            bassinActuel = item.bassin;
            const rowHeader = document.createElement('tr');
            rowHeader.innerHTML = `
              <td colspan="5" class="type_bassin">
                Bassin de ${bassinActuel || 'Non spécifié'}
              </td>
            `;
            bodyPerf.appendChild(rowHeader);
          }

          // Formatage de la MPP
          const mppStr = `<span class="time">${item.mpp.temps}</span> <span class="detail">(${item.mpp.points}) - ${item.mpp.date}</span>`;

          // Formatage des performances avec ajout de l'icône sur le record
          const perfsSaisons = item.perfs_trois_saisons || [];
          const perfsSaisonsStr = perfsSaisons.length > 0
            ? perfsSaisons
                .map(n => {
                  const estRecord = n.temps === item.mpp.temps;
                  const iconeRecord = estRecord ? ' <span class="icon-record" title="Record personnel (MPP)">⭐</span>' : '';

                  return `<span class="time">${n.temps}</span> <span class="detail">(${n.points}) - ${n.date}</span>${iconeRecord}`;
                })
                .join('<br>')
            : '-';

          // Génération de l'affichage N1 et N2 avec gestion de l'éventuel écart
          const strN2 = genererCelluleMinima(perfsSaisons, item.minima_n2);
          const strN1 = genererCelluleMinima(perfsSaisons, item.minima_n1);

          // Construction de la ligne du tableau
          const row = document.createElement('tr');
          row.innerHTML = `
            <td class="nage">${item.nage}</td>
            <td>${mppStr}</td>
            <td>${perfsSaisonsStr}</td>
            <td class="qualif-cell">${strN2}</td>
            <td class="qualif-cell">${strN1}</td>
          `;
          bodyPerf.appendChild(row);
        });
      }

      sectionPerf.style.display = 'block';

    } catch (error) {
      alert(`Impossible de charger les performances : ${error.message}`);
      sectionPerf.style.display = 'none';
    } finally {
      selectNageur.disabled = false;
    }
  });
});