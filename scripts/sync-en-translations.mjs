#!/usr/bin/env node
/**
 * Merge missing en.json keys from t('key') || 'fallback' patterns in the frontend.
 * Prefers non-French fallbacks; maps common French UI phrases to English.
 */
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const FRONTEND = path.join(__dirname, '../frontend')
const EN_PATH = path.join(FRONTEND, 'lib/translations/en.json')

const FRENCH_RE =
  /[àâäéèêëïîôùûüçÀÂÄÉÈÊËÏÎÔÙÛÜÇ]|(?:\b(Vous|Erreur|Aucun|Réessayer|Supprimer|Annuler|Fermer|Concours|Candidat|Gérez|Gestion|Informations|Téléphone|Ville|Pays|Région|Dernière|Commentaires|Masquer|Afficher|Chargement|Vérifi|Inactif|Hommes|Femmes|Classement|Bénéfice|Référent|participante|autorisé|réservé|niveau|parrainage|parrainer|Envoyé|En attente|invitation|copié|annulée|sauvegardé|retiré|ajouté|enregistré|Soumis|Traité|Créé|Qualité|Marque|Contenu|Différentes|Fonctionnalités|Découvrez|Trouvez|Questions|fréquentes|Propos|première|Démocratiser|principes|Équipe|passionnés|Organisez|favoris|glisser|étoile|Lien|Commissions|Affiliés|potentiel|maximale|Tracking|cookies|indirecte|directe|inscription|accueil|concours|potentiel)\b)/i

/** French fallback → English (exact match). */
const FR_TO_EN = {
  'Lien copié !': 'Link copied!',
  'Erreur lors de la copie': 'Error copying link',
  'Invitation annulée': 'Invitation cancelled',
  "Erreur lors de l'annulation": 'Error cancelling invitation',
  'Erreur lors de l\'annulation': 'Error cancelling invitation',
  'Vos liens de parrainage': 'Your referral links',
  'Copiez et partagez ces liens pour parrainer de nouveaux utilisateurs':
    'Copy and share these links to refer new users',
  'Votre parrain': 'Your sponsor',
  "Lien d'inscription": 'Registration link',
  "Lien page d'accueil": 'Home page link',
  'Lien page concours': 'Contests page link',
  '10 niveaux de commission': '10 commission levels',
  'Commission directe': 'Direct commission',
  'Niveaux': 'Levels',
  'Indirect': 'Indirect',
  "Gagnez 1% sur chaque niveau de votre réseau, jusqu'au 10ème niveau.":
    'Earn 1% on each level of your network, up to level 10.',
  'Total potentiel': 'Total potential',
  'Commission maximale sur 10 niveaux': 'Maximum commission across 10 levels',
  'Tracking par cookies : 30 jours': 'Cookie tracking: 30 days',
  'Affiliés': 'Affiliates',
  'En attente': 'Pending',
  'KYC en cours': 'KYC in progress',
  'Commission': 'Commission',
  'Aucune commission': 'No commission',
  'Envoyé le': 'Sent on',
  'Annuler': 'Cancel',
  'Aucune invitation en attente': 'No pending invitations',
  'Envoyez des invitations à vos amis pour les parrainer':
    'Send invitations to your friends to refer them',
  'Envoyer une invitation': 'Send an invitation',
  'Liens': 'Links',
  'Commissions': 'Commissions',
  'Ordre sauvegardé !': 'Order saved!',
  'Erreur lors de la sauvegarde': 'Error saving order',
  'Organisez vos contestants favoris par glisser-déposer':
    'Organize your favorite contestants with drag and drop',
  'Aucun favori pour le moment': 'No favorites yet',
  "Ajoutez des contestants à vos favoris depuis la page d'un concours en cliquant sur l'étoile.":
    'Add contestants to your favorites from a contest page by clicking the star.',
  'Erreur lors du chargement des données': 'Error loading data',
  'Utilisateur supprimé avec succès': 'User deleted successfully',
  'Erreur lors de la suppression': 'Error deleting',
  'KYC vérifié avec succès': 'KYC verified successfully',
  'Erreur lors de la vérification KYC': 'Error verifying KYC',
  'Vérification KYC révoquée': 'KYC verification revoked',
  'Erreur lors de la révocation KYC': 'Error revoking KYC',
  'Commentaire supprimé': 'Comment deleted',
  'Commentaire masqué': 'Comment hidden',
  'Commentaire affiché': 'Comment shown',
  'Erreur lors du masquage': 'Error hiding comment',
  "Erreur lors de l'affichage": 'Error showing comment',
  'Révoquer KYC': 'Revoke KYC',
  'Vérifier KYC': 'Verify KYC',
  'Supprimer': 'Delete',
  'Vote enregistré avec succès!': 'Vote recorded successfully!',
  'Vote enregistré (remplace le 5e choix).': 'Vote recorded (replaces 5th choice).',
  'Vous avez déjà voté pour ce participant.': 'You have already voted for this participant.',
  'Erreur lors du vote. Veuillez réessayer.': 'Error voting. Please try again.',
  'Vous ne pouvez pas voter pour votre propre candidature.':
    'You cannot vote for your own entry.',
  'Veuillez compléter votre profil pour voter.': 'Please complete your profile to vote.',
  'Réaction supprimée': 'Reaction removed',
  'Réaction ajoutée': 'Reaction added',
  "Erreur lors de l'ajout de la réaction": 'Error adding reaction',
  'Vidéo': 'Video',
  'Vous ne pouvez voter que pour les candidats de votre ville.':
    'You can only vote for candidates in your city.',
  'Vous ne pouvez voter que pour les candidats de votre pays.':
    'You can only vote for candidates in your country.',
  'Vous ne pouvez voter que pour les candidats de votre région.':
    'You can only vote for candidates in your region.',
  'Vous ne pouvez voter que pour les candidats de votre continent.':
    'You can only vote for candidates in your continent.',
  'Êtes-vous sûr de vouloir supprimer cette candidature ? Cette action ne peut pas être annulée.':
    'Are you sure you want to delete this application? This action cannot be undone.',
  'Contestant retiré des favoris': 'Contestant removed from favorites',
  'Contestant ajouté aux favoris': 'Contestant added to favorites',
  'Vérification requise': 'Verification required',
  'Assurez-vous que votre compte est vérifié pour participer.':
    'Make sure your account is verified to participate.',
  'Qualité du contenu': 'Content quality',
  'Erreur lors de la suppression': 'Error deleting',
  'Soumis le': 'Submitted on',
  'Créé le': 'Created on',
  'Traité le': 'Processed on',
  'Année': 'Year',
  'Marque vérifiée': 'Verified brand',
  'Seules les marques vérifiées peuvent participer à ce concours':
    'Only verified brands can participate in this contest',
  'Contenu original': 'Original content',
  'Seul le contenu original est autorisé pour participer à ce concours':
    'Only original content is allowed in this contest',
  'Femmes uniquement': 'Women only',
  'Hommes uniquement': 'Men only',
  'Femmes': 'Women',
  'Hommes': 'Men',
  'ans': 'years',
  "Seuls les participants dans la tranche d'âge spécifiée peuvent participer":
    'Only participants in the specified age range can participate',
  'Ce concours est réservé aux femmes uniquement': 'This contest is for women only',
  'Ce concours est réservé aux hommes uniquement': 'This contest is for men only',
}

function hasKey(obj, key) {
  let v = obj
  for (const p of key.split('.')) {
    if (!v || typeof v !== 'object' || !(p in v)) return false
    v = v[p]
  }
  return typeof v === 'string'
}

function setKey(obj, key, val) {
  const parts = key.split('.')
  let cur = obj
  for (let i = 0; i < parts.length - 1; i++) {
    if (!cur[parts[i]] || typeof cur[parts[i]] !== 'object') cur[parts[i]] = {}
    cur = cur[parts[i]]
  }
  cur[parts[parts.length - 1]] = val
}

function humanizeKey(key) {
  const last = key.split('.').pop() || key
  return last
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function walk(dir, pairs) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) {
      if (!['node_modules', '.next'].includes(e.name)) walk(p, pairs)
    } else if (/\.(tsx|ts)$/.test(e.name)) {
      const s = fs.readFileSync(p, 'utf8')
      const re =
        /t\(\s*['"]([a-zA-Z][a-zA-Z0-9_.]*)['"]\s*\)\s*\|\|\s*(?:'((?:\\'|[^'])*)'|"((?:\\"|[^"])*)")/g
      let m
      while ((m = re.exec(s))) {
        const key = m[1]
        const fb = (m[2] || m[3] || '').replace(/\\'/g, "'").replace(/\\"/g, '"')
        if (!pairs.has(key) || (!FRENCH_RE.test(fb) && FRENCH_RE.test(pairs.get(key)))) {
          pairs.set(key, fb)
        }
      }
      const re2 = /t\(\s*['"]([a-zA-Z][a-zA-Z0-9_.]*)['"]\s*\)/g
      while ((m = re2.exec(s))) {
        if (!pairs.has(m[1])) pairs.set(m[1], null)
      }
    }
  }
}

const en = JSON.parse(fs.readFileSync(EN_PATH, 'utf8'))
const pairs = new Map()
walk(FRONTEND, pairs)

let added = 0
const stillMissing = []

for (const [key, fb] of pairs) {
  if (hasKey(en, key)) continue
  let value = null
  if (fb && !FRENCH_RE.test(fb)) value = fb
  else if (fb && FR_TO_EN[fb]) value = FR_TO_EN[fb]
  else if (fb && FRENCH_RE.test(fb)) value = humanizeKey(key)
  else value = humanizeKey(key)

  if (value) {
    setKey(en, key, value)
    added++
  } else {
    stillMissing.push(key)
  }
}

fs.writeFileSync(EN_PATH, JSON.stringify(en, null, 2) + '\n')
console.log(`Added ${added} keys to en.json`)
console.log(`Still unresolved: ${stillMissing.length}`)
if (stillMissing.length) {
  console.log(stillMissing.slice(0, 30).join('\n'))
}
