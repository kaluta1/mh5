# 🚀 Plan de travail Agile – MyFav

## 🎯 Vision produit
Construire **MyFav**, une plateforme moderne de concours en ligne (photos, vidéos, YouTube/Vimeo), multi-langues, responsive, avec progression par niveaux (ville → pays → région → continent → monde), monétisation (publicité native + clubs payants), programme d’affiliation sur 10 niveaux, modération IA, et comptabilité CPA Canada.

---

## 👥 Équipe & rôles
- **Product Owner (PO)** : définit la vision, priorise le backlog.
- **Scrum Master (SM)** : facilite, enlève les blocages.
- **Développeurs front-end** (Next.js, Tailwind, shadcn/ui).
- **Développeurs back-end** (FastAPI, PostgreSQL).
- **DevOps** (Docker, CI/CD, Cloudflare, hébergement).
- **UX/UI Designer** (maquettes Figma, logo, design system).
- **QA/Testeur** (tests fonctionnels, automatisés).
- **Comptable/Conseiller conformité** (CPA Canada, RGPD).

---

## 🛠️ Stack technique
- **Front-end** : Next.js 14 (App Router), TailwindCSS, shadcn/ui, i18n.
- **Back-end** : FastAPI, PostgreSQL, Redis, Celery (workers).
- **Infra** : Docker, Cloudflare (DNS, CDN, WAF), Render/Cloud Run.
- **Médias** : S3/MinIO + Cloudflare R2, FFmpeg workers.
- **Auth** : JWT + OAuth.
- **Modération** : ClamAV + API Vision NSFW.
- **Comptabilité** : intégration comptable CPA Canada.

---

## 📅 Roadmap Agile (14 mois – à adapter)

### **Phase 0 – Préparation (Sprint 0 – 2 semaines)**
- Définir backlog initial, maquettes principales (Figma).
- Finaliser charte graphique + logo MyFav.
- Mettre en place repo Git (Bitbucket ou GitHub).
- CI/CD (Docker + pipeline Render/Cloudflare).
- Définir architecture (diagrammes contextes + composants).
- Installer environnements (dev/staging/prod).

**Livrables :**
- Design system (light/dark/cloud).
- Logo + styleguide.
- Repo + CI/CD opérationnel.

---

### **Phase 1 – MVP Core (Sprints 1 à 4 – 7 semaines)**
**Épopées principales :**
1. Authentification & profils utilisateurs (inscription, login, JWT).
2. Upload médias (photo/vidéo) + intégration YouTube/Vimeo.
3. Page d'accueil avec message de bienvenue + liste des concours.
4. Système de vote **MyFav (max 5 choix, drag&drop, scores 5-1)**.
5. Page concours (classement dynamique par score, tie-break).
6. Search bar pour retrouver un participant.
7. **Modération et sécurité**:

   - Vérification d'identité (intégration Shufti)
   - Détection automatique de contenu inapproprié
   - Système de signalement par les utilisateurs

**Livrables incrémentaux :**
- Sprint 1-2 → Auth + profils + upload média basique.
- Sprint 2-3 → Concours (page list + détail + votes + MyFav).
- Sprint 3-4 → Modération IA + vérification d'identité + recherche.

---

### **Phase 2 – Progression concours (Sprints 5 à 9 – 8 semaines)**
**Épopées :**
1. Gestion multi-niveaux (ville → pays → région → continent → monde).
2. Définition des régions/continents (modèle hiérarchique complet):
   - **Afrique**: Nord, Ouest, Centre, Est, Sud
   - **Asie**: Nord, Ouest (Moyen-Orient), Centre, Sud, Est, Sud-Est
   - **Europe**: Nord, Ouest, Centre, Est, Sud, Balkans
   - **Amérique du Nord**: Nord, Centre, Sud, Caraïbes
   - **Amérique du Sud**: Nord, Ouest (Région andine), Est, Sud (Cône Sud)
   - **Océanie**: Australie, Mélanésie, Micronésie, Polynésie
   - **Antarctique**
3. Automatisation des passages de stages (top 5 → suivant).
4. Règles d’éligibilité (genre pour Beauty/Handsome).
5. Système de périodes (upload 60j, vote 60j, reset).
6. **Templates de concours réutilisables**:
   - Template avec restrictions géographiques (Beauty/Handsome)
   - Template sans restrictions géographiques (Latest Hits)
   - Template avec restrictions de genre pour le vote

**Livrables incrémentaux :**
- Sprint 5-6 → Modèle de données location + city contests.
- Sprint 7-8 → Pays et régions + règles vote par périmètre.
- Sprint 9 → Templates de concours + niveaux continent/global.

---

### **Phase 3 – Contenus & interactions (Sprints 10 à 14 – 8 semaines)**
**Épopées :**
1. Commentaires (modération IA + signalement).
2. Likes + vues + suivi analytics.
3. Clubs payants (Fan Clubs, wallet DSP, multi-admin):
   - Création de clubs par utilisateurs vérifiés
   - Gestion multi-admin avec signatures multiples
   - Interface de paiement DSP (Digital Shopping Points)
4. Système d'affiliation (10 niveaux, tracking cookies 30j):
   - Commissions directes (20% sur références niveau 1)
   - Commissions indirectes (2% sur niveaux 2-10)
   - Tracking par cookies (30 jours)
   - Attribution aléatoire aux Early Founding Members
5. Marketplace de contenus numériques:
   - Vente de contenus téléchargeables
   - Intégration DSP (min. 50% du prix)
   - Commissions plateforme (20%)
6. Comptabilité basique (revenus pubs/fees → CPA Canada entries).

**Livrables incrémentaux :**
- Sprint 10-11 → Commentaires + likes + analytics basique.
- Sprint 12-13 → Fan Clubs + système DSP + gestion multi-admin.
- Sprint 14 → Affiliation 10 niveaux + tracking cookies + marketplace.

---

### **Phase 4 – Monétisation & ads (Sprints 15 à 17 – 6 semaines)**
**Épopées :**
1. Plateforme native ads (CPC/CPM).
2. Gestion de campagnes (budget, créatives, pacing).
3. Intégration DSP & Prebid.js.
4. Tableau de bord annonceur (stats temps réel).
5. Finalisation comptabilité CPA Canada.

**Livrables incrémentaux :**
- Sprint 15-16 → Interface annonceur + plateforme native ads + gestion campagnes.
- Sprint 17 → Comptabilité CPA complète + reporting financier.

---

### **Phase 5 – Scale & QA (Sprints 18-19 – 4 semaines)**
**Épopées :**
- Stress tests (performance).
- Sécurité (2FA, RBAC, audits).
- Optimisation SEO + i18n.
- UX refinements (mobile-first, animations).
- Déploiement bêta fermé + feedback.

---

### **Phase 6 – Release publique (Sprint 20 – 2 semaines)**
- Ouverture publique.
- Monitoring + bugfix rapide.
- Lancement campagne marketing + onboarding.

---

## 📌 Backlog initial (priorisé par valeur)
1. Auth utilisateurs + profil (Must Have)
2. Upload médias + intégration YouTube/Vimeo (Must Have)
3. Système de vote MyFav (Must Have)
4. Progression multi-niveaux des concours (Must Have)
5. Clubs payants & affiliation (Should Have)
6. Native ads + comptabilité CPA (Should Have)
7. Live streaming finale mondiale (Could Have)
8. Marketplace digital DSP (Could Have)

---

## 📋 User Stories – Phase 1 (MVP Core)

### Épopée 1 : Auth & Profils
- **US1.1** : En tant qu’utilisateur, je veux m’inscrire avec email + mot de passe afin de créer un compte.
- **US1.2** : En tant qu’utilisateur, je veux me connecter avec mon compte afin d’accéder à mes concours.
- **US1.3** : En tant qu’utilisateur, je veux mettre à jour mon profil (photo, bio, infos de base) afin de personnaliser mon identité.

### Épopée 2 : Upload médias
- **US2.1** : En tant que participant, je veux uploader une photo afin de participer à un concours.
- **US2.2** : En tant que participant, je veux uploader une vidéo (ou lien YouTube/Vimeo) afin d’élargir mon format de participation.
- **US2.3** : En tant que système, je veux vérifier la validité et la taille du fichier afin d’assurer la qualité des médias.

### Épopée 3 : Page d’accueil
- **US3.1** : En tant qu’utilisateur, je veux voir un message de bienvenue afin de comprendre la mission du site.
- **US3.2** : En tant qu’utilisateur, je veux voir la liste des concours actifs afin de choisir où voter ou participer.

### Épopée 4 : Système de vote MyFav
- **US4.1** : En tant qu’utilisateur, je veux pouvoir sélectionner jusqu’à 5 candidats favoris par concours afin d’exprimer mes préférences.
- **US4.2** : En tant qu’utilisateur, je veux attribuer des scores (5 à 1) automatiquement selon l’ordre afin que mon classement ait un poids clair.
- **US4.3** : En tant que système, je veux empêcher de voter deux fois afin d’assurer l’équité.

### Épopée 5 : Page concours & classements
- **US5.1** : En tant qu’utilisateur, je veux consulter la page d’un concours afin de voir les participants et leurs scores.
- **US5.2** : En tant qu’utilisateur, je veux voir le classement dynamique afin de suivre l’évolution en temps réel.
- **US5.3** : En tant que système, je veux appliquer une règle de tie-break (meilleur score reçu) afin de départager les ex aequo.

### Épopée 6 : Recherche
- **US6.1** : En tant qu’utilisateur, je veux rechercher un participant par nom afin de le retrouver facilement.
- **US6.2** : En tant que système, je veux proposer l’autocomplétion afin d’accélérer la recherche.

### Épopée 7 : Modération et Sécurité
- **US7.1** : En tant que système, je veux vérifier l'identité des participants via Shufti pour garantir l'authenticité des contenus.
- **US7.2** : En tant que système, je veux détecter automatiquement le contenu inapproprié via API Vision pour maintenir la qualité de la plateforme.
- **US7.3** : En tant qu'utilisateur, je veux signaler du contenu problématique ou non conforme pour contribuer à la modération communautaire.
- **US7.4** : En tant qu'administrateur, je veux recevoir des alertes pour les contenus signalés afin d'intervenir rapidement.

---

## 📝 User Stories additionnelles

### Épopée 8 : Templates de Concours
- **US8.1** : En tant qu'administrateur, je veux créer différents types de concours à partir de templates pour faciliter l'expansion de la plateforme.
- **US8.2** : En tant que système, je veux appliquer automatiquement les règles spécifiques à chaque type de concours (restrictions géographiques ou de genre) pour garantir l'équité.
- **US8.3** : En tant qu'utilisateur, je veux recommander un nouveau type de concours afin d'enrichir la plateforme.
- **US8.4** : En tant qu'utilisateur, je veux comprendre clairement les règles spécifiques à chaque concours avant d'y participer.

### Épopée 9 : Économie et Monétisation
- **US9.1** : En tant qu'utilisateur vérifié, je veux créer un Fan Club payant pour monétiser mon contenu.
- **US9.2** : En tant qu'utilisateur, je veux configurer une gestion multi-admin avec signatures multiples pour sécuriser les opérations de mon club.
- **US9.3** : En tant qu'utilisateur, je veux recevoir des commissions sur 10 niveaux d'affiliation pour bénéficier du programme complet.
- **US9.4** : En tant que système, je veux générer automatiquement les écritures comptables pour les commissions d'affiliation.
- **US9.5** : En tant qu'utilisateur, je veux vendre des contenus numériques téléchargeables via la marketplace intégrée.
- **US9.6** : En tant qu'annonceur, je veux créer des campagnes publicitaires natives ciblées pour promouvoir mes produits.

---

✅ Ce document peut servir directement de **plan projet + backlog initial** pour l'équipe MyFav.
