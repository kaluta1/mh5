# Service Social - Documentation

## Vue d'ensemble

Le service social est un module indépendant qui permet aux utilisateurs de :
- Créer et partager des posts
- Commenter et réagir aux posts
- Suivre d'autres utilisateurs
- Créer et rejoindre des groupes
- Envoyer des messages dans les groupes
- Recevoir des notifications en temps réel via Socket.IO

## Architecture

### Modèles de données

#### Posts (`app/models/post.py`)
- `Post` : Publication sociale avec contenu, médias, visibilité
- `PostMedia` : Médias associés aux posts
- `PostComment` : Commentaires sur les posts (avec support des réponses)
- `PostReaction` : Réactions (like, love, haha, wow, sad, angry)
- `PostCommentReaction` : Réactions sur les commentaires
- `PostShare` : Partages de posts

#### Groupes sociaux (`app/models/social_group.py`)
- `SocialGroup` : Groupe social (public, privé, secret)
- `GroupMember` : Membres d'un groupe avec rôles (member, admin, moderator, owner)
- `GroupJoinRequest` : Demandes d'adhésion
- `GroupMessage` : Messages dans les groupes
- `MessageReadReceipt` : Reçus de lecture

#### Feed (`app/models/feed.py`)
- `Feed` : Fil d'actualité personnalisé pour chaque utilisateur

### API REST

Tous les endpoints sont préfixés par `/api/v1/social` :

#### Posts
- `POST /posts` - Créer un post
- `GET /posts` - Lister les posts (avec filtres)
- `GET /posts/{post_id}` - Récupérer un post
- `PUT /posts/{post_id}` - Modifier un post
- `DELETE /posts/{post_id}` - Supprimer un post

#### Commentaires
- `POST /posts/{post_id}/comments` - Commenter un post
- `GET /posts/{post_id}/comments` - Lister les commentaires
- `DELETE /comments/{comment_id}` - Supprimer un commentaire

#### Réactions
- `POST /posts/{post_id}/reactions` - Ajouter/supprimer une réaction
- `DELETE /posts/{post_id}/reactions` - Supprimer une réaction

#### Partages
- `POST /posts/{post_id}/shares` - Partager un post

#### Groupes
- `POST /groups` - Créer un groupe
- `GET /groups` - Lister les groupes
- `GET /groups/{group_id}` - Récupérer un groupe
- `POST /groups/{group_id}/join` - Rejoindre un groupe
- `DELETE /groups/{group_id}/leave` - Quitter un groupe

#### Messages
- `POST /groups/{group_id}/messages` - Envoyer un message
- `GET /groups/{group_id}/messages` - Lister les messages
- `POST /messages/{message_id}/read` - Marquer un message comme lu

#### Feed
- `GET /feed` - Récupérer le fil d'actualité

### Socket.IO

Le service utilise Socket.IO pour les notifications en temps réel.

#### Installation

```bash
pip install python-socketio
```

#### Événements Socket.IO

##### Côté client (écouter)
- `new_post` - Nouveau post créé
- `new_comment` - Nouveau commentaire
- `new_reaction` - Nouvelle réaction
- `new_message` - Nouveau message dans un groupe
- `message_read` - Message marqué comme lu
- `user_online` - Utilisateur en ligne
- `user_offline` - Utilisateur hors ligne

##### Côté client (émettre)
- `connect` - Connexion (avec authentification)
- `disconnect` - Déconnexion
- `join_group` - Rejoindre une room de groupe
- `leave_group` - Quitter une room de groupe
- `new_post` - Notifier la création d'un post
- `new_reaction` - Notifier une réaction
- `new_comment` - Notifier un commentaire
- `send_message` - Envoyer un message
- `message_read` - Marquer un message comme lu

#### Authentification Socket.IO

Lors de la connexion, le client doit envoyer un objet d'authentification :

```javascript
const socket = io('http://localhost:8000', {
  auth: {
    token: 'your_jwt_token'
  }
});
```

## Utilisation

### Exemple de création de post

```python
from app.schemas.social import PostCreate, PostType, PostVisibility

post_data = PostCreate(
    content="Mon premier post !",
    post_type=PostType.TEXT,
    visibility=PostVisibility.PUBLIC,
    media_ids=[1, 2]  # IDs des médias
)

response = requests.post(
    "http://localhost:8000/api/v1/social/posts",
    json=post_data.dict(),
    headers={"Authorization": f"Bearer {token}"}
)
```

### Exemple de connexion Socket.IO (JavaScript)

```javascript
import io from 'socket.io-client';

const socket = io('http://localhost:8000', {
  auth: {
    token: localStorage.getItem('access_token')
  }
});

socket.on('connect', () => {
  console.log('Connecté au serveur Socket.IO');
});

socket.on('new_post', (data) => {
  console.log('Nouveau post:', data);
});

socket.on('new_message', (data) => {
  console.log('Nouveau message:', data);
});

// Rejoindre un groupe
socket.emit('join_group', { group_id: 1 });
```

## Configuration

Le service social est indépendant et peut être activé/désactivé sans affecter les autres parties de l'application.

Si Socket.IO n'est pas installé, le service fonctionnera toujours mais sans les notifications en temps réel.

## Notes importantes

1. Les posts peuvent être publics, visibles uniquement par les followers, privés ou dans un groupe
2. Les groupes peuvent être publics, privés ou secrets
3. Les messages dans les groupes nécessitent d'être membre
4. Les notifications sont envoyées en arrière-plan pour ne pas bloquer les réponses API
5. Le fil d'actualité est généré dynamiquement à partir des posts des utilisateurs suivis

