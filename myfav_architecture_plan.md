# Plan d'Architecture MyFav - Plateforme de Concours Multi-Niveaux

## Vue d'ensemble du Système

### Architecture Générale
- **Backend**: FastAPI + PostgreSQL (Neon) + Redis
- **Frontend**: React/Next.js (responsive multi-device)
- **Storage**: AWS S3 pour médias + CDN
- **Authentification**: JWT + Vérification Shufti
- **Paiements**: Stripe + DSP (Digital Shopping Points)

## 1. Modèles de Données Principaux

### 1.1 Géolocalisation Hiérarchique
```sql
-- Continents et régions prédéfinis
continents (id, name, code)
regions (id, continent_id, name, code)
countries (id, region_id, name, code, flag_url)
cities (id, country_id, name, latitude, longitude)
```

### 1.2 Système de Concours Multi-Niveaux
```sql
-- Types de concours
contest_types (id, name, description, rules, voting_restrictions)
contest_categories (id, contest_type_id, name, description)

-- Saisons et étapes de concours
contest_seasons (id, contest_type_id, year, status, start_date, end_date)
contest_stages (id, season_id, stage_level, geographic_scope_id, start_date, end_date, status)

-- Participants et soumissions
contestants (id, user_id, contest_type_id, season_id, status, verification_status)
contest_submissions (id, contestant_id, media_type, file_url, title, description, upload_date)
```

### 1.3 Système de Vote et Ranking
```sql
-- Votes avec système de points (5-4-3-2-1)
votes (id, voter_id, contestant_id, contest_stage_id, rank_position, points, vote_date)
vote_sessions (id, voter_id, contest_type_id, stage_id, max_votes_reached)

-- Rankings calculés
contestant_rankings (id, contestant_id, stage_id, total_points, page_views, likes, final_rank)
```

### 1.4 Système d'Affiliation 10 Niveaux
```sql
-- Structure d'affiliation
affiliate_tree (id, user_id, sponsor_id, level, path, join_date)
affiliate_commissions (id, user_id, source_user_id, commission_type, amount, level, transaction_date)
commission_rates (id, level, rate_percentage, commission_type)
```

### 1.5 Système de Revenus Publicitaires
```sql
-- Plateforme publicitaire native
ad_campaigns (id, advertiser_id, name, budget, cost_model, status, start_date, end_date)
ad_creatives (id, campaign_id, format, content_url, title, description)
ad_placements (id, page_type, position, targeting_criteria)
ad_impressions (id, ad_id, user_id, page_url, timestamp, cost)
ad_clicks (id, impression_id, timestamp, conversion_tracked)

-- Distribution des revenus
revenue_shares (id, user_id, source_type, amount, percentage, distribution_date)
```

### 1.6 Clubs Payants et DSP
```sql
-- Digital Shopping Points
dsp_wallets (id, user_id, balance, last_updated)
dsp_transactions (id, wallet_id, transaction_type, amount, reference_id, timestamp)

-- Clubs payants
fan_clubs (id, owner_id, name, description, monthly_fee, annual_discount, status)
club_memberships (id, club_id, member_id, membership_type, start_date, end_date, payment_status)
club_admins (id, club_id, admin_id, permissions, multisig_required)
```

## 2. Endpoints API Principaux

### 2.1 Authentification et Utilisateurs
```
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/verify-identity  # Intégration Shufti
GET /api/v1/users/profile
PUT /api/v1/users/profile
GET /api/v1/users/affiliate-tree
```

### 2.2 Géolocalisation
```
GET /api/v1/geo/continents
GET /api/v1/geo/regions/{continent_id}
GET /api/v1/geo/countries/{region_id}
GET /api/v1/geo/cities/{country_id}
```

### 2.3 Concours et Participants
```
GET /api/v1/contests/types
GET /api/v1/contests/{type_id}/seasons
POST /api/v1/contestants/register
POST /api/v1/contestants/{id}/submit-media
GET /api/v1/contests/{type_id}/stages/{stage_id}/contestants
GET /api/v1/contestants/{id}/profile
```

### 2.4 Système de Vote
```
POST /api/v1/votes/cast
GET /api/v1/votes/my-favorites/{contest_type_id}
PUT /api/v1/votes/reorder-favorites
GET /api/v1/contests/{stage_id}/rankings
```

### 2.5 Clubs et DSP
```
POST /api/v1/clubs/create
GET /api/v1/clubs/{id}
POST /api/v1/clubs/{id}/join
GET /api/v1/dsp/wallet
POST /api/v1/dsp/transfer
GET /api/v1/shop/products
POST /api/v1/shop/purchase
```

### 2.6 Publicités et Revenus
```
POST /api/v1/ads/campaigns
GET /api/v1/ads/performance/{campaign_id}
GET /api/v1/revenue/shares
GET /api/v1/affiliate/commissions
```

## 3. Fonctionnalités Spécialisées

### 3.1 Système de Progression Multi-Niveaux
- **Upload Phase**: 60 jours pour soumettre contenu
- **City Level**: Vote local, top 5 qualifiés
- **Country Level**: Vote national, top 5 qualifiés  
- **Regional Level**: Vote régional, top 5 qualifiés
- **Continental Level**: Vote continental, top 5 qualifiés
- **Global Level**: Vote mondial, finale avec camping live

### 3.2 Types de Concours Spécialisés
- **Beauty/Handsome**: Restrictions de vote par genre
- **Latest Hits**: Détection automatique date de sortie
- **Sports Clubs**: Système de contenu fan-generated
- **Pets**: Concours par espèce animale

### 3.3 Intelligence Artificielle
- **Vérification d'identité**: Comparaison avec données Shufti
- **Détection de contenu**: Modération automatique
- **Classification musicale**: Auto-catégorisation par genre
- **Ciblage publicitaire**: Algorithme de placement contextuel

## 4. Système Comptable CPA Canada

### 4.1 Structure Comptable
```sql
-- Plan comptable conforme CPA Canada
chart_of_accounts (id, account_code, account_name, account_type, parent_id)
journal_entries (id, entry_date, description, reference, total_debit, total_credit)
journal_lines (id, entry_id, account_id, debit_amount, credit_amount, description)

-- Rapports financiers automatisés
financial_reports (id, report_type, period_start, period_end, generated_date, data_json)
```

### 4.2 Types de Transactions
- Revenus publicitaires (40% participants, 10% sponsors directs, 1% x 10 niveaux)
- Frais d'adhésion clubs (80% propriétaire, 20% plateforme)
- Commissions affiliation (distribution 10 niveaux)
- Revenus boutique digitale (80% vendeur, 20% plateforme)

## 5. Sécurité et Performance

### 5.1 Sécurité
- **Authentification**: JWT avec refresh tokens
- **Autorisation**: RBAC (Role-Based Access Control)
- **Données sensibles**: Chiffrement AES-256
- **API**: Rate limiting et validation stricte
- **Fraude**: Détection click fraud et cookie stuffing

### 5.2 Performance
- **Cache**: Redis pour sessions et rankings
- **CDN**: Distribution mondiale des médias
- **Base de données**: Index optimisés, partitioning
- **API**: Pagination et lazy loading
- **Monitoring**: Logs structurés et métriques temps réel

## 6. Phases de Développement

### Phase 1: Infrastructure de Base (4-6 semaines)
- Modèles de données core
- Authentification et utilisateurs
- Système géographique
- API de base

### Phase 2: Système de Concours (6-8 semaines)
- Gestion des concours multi-niveaux
- Upload et gestion médias
- Système de vote et ranking
- Interface utilisateur responsive

### Phase 3: Monétisation (4-6 semaines)
- Système d'affiliation
- Plateforme publicitaire
- DSP et clubs payants
- Système comptable

### Phase 4: Fonctionnalités Avancées (4-6 semaines)
- IA pour modération et classification
- Analytics avancées
- Optimisations performance
- Tests et déploiement

## 7. Technologies et Intégrations

### 7.1 Stack Technique
- **Backend**: FastAPI, SQLAlchemy, Alembic
- **Base de données**: PostgreSQL (Neon), Redis
- **Frontend**: React/Next.js, TypeScript, Tailwind CSS
- **Mobile**: React Native ou PWA
- **Cloud**: AWS (S3, CloudFront, Lambda)

### 7.2 Intégrations Tierces
- **Vérification**: Shufti Pro API
- **Paiements**: Stripe, PayPal
- **Médias**: YouTube API, Vimeo API
- **Email**: SendGrid ou AWS SES
- **Analytics**: Google Analytics, Mixpanel
- **Monitoring**: Sentry, DataDog

## 8. Considérations Légales et Conformité

### 8.1 Conformité
- **RGPD**: Protection données européennes
- **CCPA**: Lois californiennes sur la vie privée
- **CPA Canada**: Standards comptables canadiens
- **Copyright**: Système de détection et suppression

### 8.2 Modération
- **Contenu**: IA + modération humaine
- **Fraude**: Détection patterns suspects
- **Spam**: Filtres automatiques
- **Abus**: Système de signalement utilisateurs
