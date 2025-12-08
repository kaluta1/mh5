# Configuration de la Modération de Contenu

## Variables d'environnement requises

Ajoutez ces variables à votre fichier `.env.local` :

```env
# Activer/Désactiver la modération de contenu
ENABLE_CONTENT_MODERATION=true

# Sightengine - Modération d'images/vidéos + Comparaison de visages
# Inscription: https://sightengine.com/
SLIGTHENGINE_API_USER=your_api_user
SLIGTHENGINE_API_KEY=your_api_key

# Uploadthing
UPLOADTHING_SECRET=your_uploadthing_secret
UPLOADTHING_APP_ID=your_app_id
```

## Service utilisé : Sightengine

**Prix** : À partir de $29/mois

**Fonctionnalités utilisées** :
- ✅ Détection de nudité / contenu adulte
- ✅ Détection de violence / gore
- ✅ Détection d'armes
- ✅ Détection de contenu offensant
- ✅ Modération de vidéos
- ✅ Détection de visages
- ✅ Comparaison de visages (ownership verification)

## Flux de modération

```
┌─────────────────────────────────────────────────────────────────┐
│                     UPLOAD DE CONTENU                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                 1. MODÉRATION DE CONTENU                        │
│                    (Sightengine)                                │
│                                                                 │
│  ✓ Pas de nudité/contenu adulte                                │
│  ✓ Pas de violence/gore                                        │
│  ✓ Pas d'armes                                                 │
│  ✓ Pas de contenu offensant                                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │                   │
              ✅ Approuvé          ❌ Rejeté
                    │                   │
                    ▼                   ▼
┌─────────────────────────┐   ┌─────────────────────────┐
│ 2. VÉRIF. OWNERSHIP     │   │  Fichier supprimé       │
│   (Si visage détecté)   │   │  Message d'erreur       │
│                         │   └─────────────────────────┘
│ Comparer avec selfie    │
│ de vérification         │
└─────────────────────────┘
                    │
          ┌────────┴────────┐
          │                 │
    ✅ Match           ⚠️ Non-match
          │                 │
          ▼                 ▼
┌──────────────────┐  ┌──────────────────┐
│ Contenu sauvegardé│  │ Alerte admin     │
└──────────────────┘  │ Révision manuelle│
                      └──────────────────┘
```

## API Endpoints

### POST /api/content/moderate
Modère un contenu (image ou vidéo).

```json
// Request
{
  "contentUrl": "https://example.com/image.jpg",
  "contentType": "image"
}

// Response
{
  "success": true,
  "moderation": {
    "isApproved": true,
    "confidence": 0.95,
    "flags": [],
    "details": {}
  }
}
```

### POST /api/content/verify-ownership
Vérifie que l'auteur du contenu est le même que le selfie de vérification.

```json
// Request
{
  "verificationImageUrl": "https://example.com/selfie.jpg",
  "uploadedImageUrl": "https://example.com/content.jpg"
}

// Response
{
  "success": true,
  "ownership": {
    "isMatch": true,
    "confidence": 0.87,
    "faceDetected": true,
    "details": {
      "similarity": 0.87,
      "verificationImageFaces": 1,
      "uploadedImageFaces": 1
    }
  }
}
```

## Seuils de modération

Les seuils sont configurables dans `lib/services/content-moderation-service.ts` :

```typescript
const MODERATION_THRESHOLDS = {
  nudity: 0.6,        // Score au-delà = contenu adulte
  violence: 0.7,      // Score au-delà = contenu violent
  gore: 0.5,          // Score pour gore/cadavres/sang
  weapons: 0.8,       // Score pour armes
  offensive: 0.7,     // Score pour contenu offensant
  drugs: 0.8,         // Score pour drogues
}
```

## Mode développement

Sans clés API configurées, le service fonctionne en mode "pass-through" :
- Tous les contenus sont approuvés
- Les vérifications d'ownership retournent `isMatch: true`
- Un warning est affiché dans les logs

## Aucune dépendance supplémentaire requise

Sightengine est appelé via son API REST, aucune installation de package npm n'est nécessaire.
