#!/usr/bin/env node
/** Replace French strings accidentally stored in en.json with English equivalents. */
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const EN_PATH = path.join(path.dirname(fileURLToPath(import.meta.url)), '../frontend/lib/translations/en.json')

const FR_TO_EN = {
  'Enregistrement...': 'Saving...',
  'Voir tout': 'View all',
  'Statistiques': 'Statistics',
  'Voir la page': 'View page',
  'Fin des inscriptions': 'Submissions closed',
  'Voir le profil du participant': 'View participant profile',
  'Raison du signalement': 'Report reason',
  'Envoyer': 'Send',
  'Voir les statistiques': 'View statistics',
  'Votre parrain': 'Your sponsor',
  'Voir les participants': 'View participants',
  'Statistiques de la plateforme': 'Platform statistics',
  'Montant': 'Amount',
  'Document de preuve (optionnel)': 'Proof document (optional)',
  'Plateforme (optionnel)': 'Platform (optional)',
  'Capturer': 'Capture',
  'Enregistrement en cours...': 'Recording...',
  'Voir toutes les notifications': 'View all notifications',
  'Enregistrer': 'Save',
  'Montant minimum': 'Minimum amount',
  'Age Minimum': 'Minimum age',
  'Referrals Indirects': 'Indirect referrals',
  'Indirect Tooltip Desc': 'Earn from referrals in levels 2–10 of your network.',
  'Indirect Description': 'Earn 1% on each level of your network, up to level 10.',
  'Commission Privacy Note': 'Commission amounts may be hidden for privacy.',
}

function walk(obj) {
  if (!obj || typeof obj !== 'object') return
  for (const [k, v] of Object.entries(obj)) {
    if (typeof v === 'string') {
      if (FR_TO_EN[v]) obj[k] = FR_TO_EN[v]
      else if (/[àâäéèêëïîôùûüç]|^Voir |^Statistiques|^Votre |^Enregistr|^Montant|^Plateforme|^Document de|^Capturer|^Raison du|^Fin des/.test(v)) {
        // humanize key as last resort
        obj[k] = k.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
      }
    } else if (v && typeof v === 'object') {
      walk(v)
    }
  }
}

const en = JSON.parse(fs.readFileSync(EN_PATH, 'utf8'))
walk(en)
fs.writeFileSync(EN_PATH, JSON.stringify(en, null, 2) + '\n')
console.log('Cleaned French strings in en.json')
