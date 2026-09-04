let statusMessageTimer;

function afficherStatus(status, message, couleur) {
  clearTimeout(statusMessageTimer);
  status.style.display = 'block';
  status.style.color = couleur;
  status.innerText = message;
  statusMessageTimer = setTimeout(() => {
    status.style.display = 'none';
  }, 5000);
}

async function lancerScraping() {
  const btn = document.getElementById('btnScrape');
  const status = document.getElementById('statusMessage');
  const selectNageur = document.getElementById('selectNageur');

  // Blocage du bouton pendant la requête
  btn.disabled = true;
  afficherStatus(status, "Récupération en cours depuis Extranat...", 'black');

  try {
    const response = await fetch('/api/scraper-nageurs', { method: 'POST' });
    const data = await response.json();

    if (data.success) {
      afficherStatus(status, data.message, 'green');

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
      afficherStatus(status, "Erreur : " + (data.erreur || data.message || "Échec du scraping"), 'red');
    }
  } catch (err) {
    afficherStatus(status, "Erreur de communication avec le serveur.", 'red');
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

function echapperHtml(valeur) {
  return String(valeur ?? '').replace(/[&<>"']/g, caractere => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  }[caractere]));
}

function normaliserBassin(bassin) {
  const valeur = String(bassin || '').replace('m', '').trim();
  const bassinNumero = Number.parseInt(valeur, 10);
  return Number.isNaN(bassinNumero) ? null : bassinNumero;
}

// Vérifie si au moins une performance de la liste égale ou bat le temps de qualification
function estQualifie(listePerfs, minima) {
  if (!minima || minima.temps === '-' || !listePerfs || listePerfs.length === 0) {
    return false;
  }

  const minimaSec = convertirTempsEnSecondes(minima.temps);
  if (minimaSec === null) return false;

  return listePerfs.some(perf => {
    const tempsSec = convertirTempsEnSecondes(perf.temps);
    return tempsSec !== null && tempsSec <= minimaSec &&
      normaliserBassin(perf.bassin) === normaliserBassin(minima.bassin);
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

function indexerPerformancesParBassin(listePerfs) {
  const performancesParBassin = new Map();

  (listePerfs || []).forEach(perf => {
    const tempsSec = convertirTempsEnSecondes(perf.temps);
    if (tempsSec === null) return;

    const bassin = normaliserBassin(perf.bassin);
    if (!performancesParBassin.has(bassin)) {
      performancesParBassin.set(bassin, []);
    }
    performancesParBassin.get(bassin).push(tempsSec);
  });

  return performancesParBassin;
}

// Helper d'affichage pour les colonnes de minima
function genererCelluleMinima(performancesParBassin, minimaStr) {
  if (!minimaStr || minimaStr.length === 0) return '-';

  const minima = minimaStr.filter(item => item.temps !== '-');
  if (minima.length === 0) return '-';

  return minima.map(item => {
    const badge = item.qualifie
      ? '<span class="badge-success">✓</span>'
      : '<span class="badge-danger">✗</span>';
    const meilleursTemps = performancesParBassin.get(normaliserBassin(item.bassin)) || [];
    const ecartSec = meilleursTemps.length > 0
      ? Math.min(...meilleursTemps) - convertirTempsEnSecondes(item.temps)
      : 0;
    const ecart = !item.qualifie && meilleursTemps.length > 0
      ? `<span class="ecart-time">${formaterEcart(ecartSec)}</span>`
      : '';

    return `<div class="minima-line">${echapperHtml(item.temps)} (${echapperHtml(item.bassin)}m) ${badge}${ecart}</div>`;
  }).join('');
}

function contientMinimaValide(minimaStr) {
  return Array.isArray(minimaStr) && minimaStr.some(item => item.qualifie);
}

function genererRecapitulatifQualifications(performances, afficherQualifN2) {
  const qualifications = new Map([
    ['N1 25m', new Set()],
    ['N1 50m', new Set()],
    ['N2 25m', new Set()],
    ['N2 50m', new Set()]
  ]);
  const nageurEstN1 = performances.some(item => contientMinimaValide(item.minima_n1));

  performances.forEach(item => {
    const n1Valide = contientMinimaValide(item.minima_n1);
    const nage = echapperHtml(item.nage);

    if (n1Valide) {
      const minimaN1Valides = item.minima_n1.filter(minima => minima.qualifie);
      minimaN1Valides.forEach(minima => {
        const bassinMinima = normaliserBassin(minima.bassin);
        qualifications.get(bassinMinima === 25 ? 'N1 25m' : 'N1 50m').add(nage);
        if (bassinMinima === 25 && item.nage !== '100 4N') {
          qualifications.get('N1 50m').add(nage);
        }
      });
      return;
    }

    if (!nageurEstN1 && contientMinimaValide(item.minima_n2)) {
      const minimaN2Valides = item.minima_n2.filter(minima => minima.qualifie);
      minimaN2Valides.forEach(minima => {
        const bassinMinima = normaliserBassin(minima.bassin);
        qualifications.get(bassinMinima === 25 ? 'N2 25m' : 'N2 50m').add(nage);
        if (bassinMinima === 25 && item.nage !== '100 4N.') {
          qualifications.get('N2 50m').add(nage);
        }
      });
    }
  });

  const lignes = [...qualifications.entries()]
    .filter(([, nages]) => nages.size > 0)
    .map(([libelle, nages]) => `<div><strong>${libelle} :</strong> ${[...nages].join(', ')}</div>`)
    .join('');

  return `
    <tr class="qualification-summary">
      <td colspan="${afficherQualifN2 ? 5 : 4}">
        <strong>Qualifications obtenues</strong>
        ${lignes || '<div>Aucune qualification</div>'}
      </td>
    </tr>
  `;
}

document.addEventListener('DOMContentLoaded', () => {
  const selectNageur = document.getElementById('selectNageur');
  const sectionPerf = document.getElementById('section-performances');
  const bodyPerf = document.getElementById('body-performances');
  const titreNageur = document.getElementById('titre-nageur');
  const enTeteQualifN2 = document.getElementById('en-tete-qualif-n2');

  selectNageur.addEventListener('change', async () => {
    const iuf = selectNageur.value;
    if (!iuf) {
      enTeteQualifN2.hidden = false;
      sectionPerf.style.display = 'none';
      return;
    }

    selectNageur.disabled = true;

    try {
      const response = await fetch(`/api/nageur/${iuf}/summary`);
      if (!response.ok) throw new Error(`Erreur ${response.status}`);

      const data = await response.json();
      bodyPerf.innerHTML = '';
      const afficherQualifN2 = !data.performances?.some(item => contientMinimaValide(item.minima_n1));
      enTeteQualifN2.hidden = !afficherQualifN2;

      if (!data.performances || data.performances.length === 0) {
        bodyPerf.innerHTML = `<tr><td colspan="${afficherQualifN2 ? 5 : 4}">Aucune performance trouvée.</td></tr>`;
      } else {
        let bassinActuel = null;
        const fragment = document.createDocumentFragment();

        bodyPerf.insertAdjacentHTML(
          'beforeend',
          genererRecapitulatifQualifications(data.performances, afficherQualifN2)
        );

        data.performances.forEach(item => {
          // Séparateur de bassin
          if (item.bassin !== bassinActuel) {
            bassinActuel = item.bassin;
            const rowHeader = document.createElement('tr');
            rowHeader.innerHTML = `
              <td colspan="5" class="type_bassin">
                Bassin de ${echapperHtml(bassinActuel || 'Non spécifié')}
              </td>
            `;
            fragment.appendChild(rowHeader);
          }

          // Formatage de la MPP
          const mppStr = `<span class="time">${echapperHtml(item.mpp.temps)}</span> <span class="detail">(${echapperHtml(item.mpp.points)}) - ${echapperHtml(item.mpp.date)}</span>`;

          // Formatage des performances avec ajout de l'icône sur le record
          const perfsSaisons = item.perfs_trois_saisons || [];
          const perfsSaisonsStr = perfsSaisons.length > 0
            ? perfsSaisons
                .map(n => {
                  const estRecord = n.temps === item.mpp.temps;
                  const iconeRecord = estRecord ? ' <span class="icon-record" title="Record personnel (MPP)">⭐</span>' : '';

                  return `<span class="time">${echapperHtml(n.temps)}</span> <span class="detail">(${echapperHtml(n.points)}) - ${echapperHtml(n.date)}</span>${iconeRecord}`;
                })
                .join('<br>')
            : '-';

          // Génération de l'affichage N1 et N2 avec gestion de l'éventuel écart
          const perfsQualification = item.perfs_qualification || perfsSaisons;
          const performancesParBassin = indexerPerformancesParBassin(perfsQualification);
          const strN1 = genererCelluleMinima(
            performancesParBassin,
            item.minima_n1
          );

          // Construction de la ligne du tableau
          const row = document.createElement('tr');
          row.innerHTML = `
            <td class="nage">${echapperHtml(item.nage)}</td>
            <td>${mppStr}</td>
            <td>${perfsSaisonsStr}</td>
            ${afficherQualifN2 ? `<td class="qualif-cell">${genererCelluleMinima(performancesParBassin, item.minima_n2)}</td>` : ''}
            <td class="qualif-cell">${strN1}</td>
          `;
          fragment.appendChild(row);
        });

        bodyPerf.appendChild(fragment);
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