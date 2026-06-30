#!/usr/bin/env node
/**
 * Replace French string literals used as t() fallbacks with English equivalents.
 */
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const FRONTEND = path.join(__dirname, '../frontend')

const REPLACEMENTS = [
  ["|| 'Lien copié !'", "|| 'Link copied!'"],
  ["|| 'Erreur lors de la copie'", "|| 'Error copying link'"],
  ["|| 'Invitation annulée'", "|| 'Invitation cancelled'"],
  ["|| 'Erreur lors de l\\'annulation'", "|| 'Error cancelling invitation'"],
  ["|| 'Erreur lors du chargement des données'", "|| 'Error loading data'"],
  ["|| 'Ordre sauvegardé !'", "|| 'Order saved!'"],
  ["|| 'Erreur lors de la sauvegarde'", "|| 'Error saving order'"],
  ["|| 'Classement des Sponsors'", "|| 'Sponsor Leaderboard'"],
  ["|| 'Classement Général'", "|| 'General Leaderboard'"],
  ["|| 'Classement MFM'", "|| 'MFM Leaderboard'"],
  ["|| 'Aucun sponsor trouvé'", "|| 'No sponsors found'"],
  ["|| 'Référents'", "|| 'Referrals'"],
  ["|| 'Bénéfice'", "|| 'Benefit'"],
  ["|| 'Comment fonctionne le classement ?'", "|| 'How does the leaderboard work?'"],
  ["|| 'Supprimer'", "|| 'Delete'"],
  ["|| 'Annuler'", "|| 'Cancel'"],
  ["|| 'Fermer'", "|| 'Close'"],
  ["|| 'Réessayer'", "|| 'Retry'"],
  ["|| 'Vidéo'", "|| 'Video'"],
  ["|| 'Soumis le'", "|| 'Submitted on'"],
  ["|| 'Créé le'", "|| 'Created on'"],
  ["|| 'Traité le'", "|| 'Processed on'"],
  ["|| 'Année'", "|| 'Year'"],
  ["toLocaleDateString('fr-FR'", "toLocaleDateString('en-US'"],
  ["toLocaleDateString(\"fr-FR\"", "toLocaleDateString(\"en-US\""],
  ["localeMap[language] || 'fr-FR'", "localeMap[language] || 'en-US'"],
  ["? language : 'fr'", "? language : 'en'"],
  ["language === 'fr' ? 'fr-FR' : 'en-US'", "language === 'fr' ? 'fr-FR' : language === 'es' ? 'es-ES' : language === 'de' ? 'de-DE' : 'en-US'"],
]

let filesChanged = 0
function walk(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) {
      if (!['node_modules', '.next'].includes(e.name)) walk(p)
    } else if (/\.(tsx|ts)$/.test(e.name) && !p.includes('lib/translations/')) {
      let s = fs.readFileSync(p, 'utf8')
      let orig = s
      for (const [from, to] of REPLACEMENTS) {
        s = s.split(from).join(to)
      }
      if (s !== orig) {
        fs.writeFileSync(p, s)
        filesChanged++
      }
    }
  }
}
walk(FRONTEND)
console.log('Files updated:', filesChanged)
