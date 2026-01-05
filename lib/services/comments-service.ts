import api from '@/lib/api'

export interface Comment {
  id: string | number
  author_name: string
  author_avatar?: string
  content: string  // Le backend utilise 'content' au lieu de 'text'
  text?: string  // Garder pour compatibilité
  created_at: string
  updated_at?: string
  like_count?: number
  reply_count?: number
  parent_id?: number | null
  user_id?: number
  is_liked?: boolean  // Si l'utilisateur actuel a liké ce commentaire
  target_type?: 'contest' | 'photo' | 'video'
  target_id?: string
  replies?: Comment[]  // Réponses en cascade
}

export interface CreateCommentRequest {
  text: string
  target_type: 'contest' | 'photo' | 'video'
  target_id?: string
}

export interface CommentResponse {
  id: string
  text: string
  author_id: number
  author_name: string
  author_avatar?: string
  target_type: string
  target_id?: string
  created_at: string
  updated_at: string
}

export interface CommentListResponse {
  comments: Comment[]
  total: number
  page: number
  page_size: number
}

export const commentsService = {
  // Récupérer les commentaires pour un contestant avec pagination
  async getContestantComments(
    contestantId: string, 
    skip: number = 0, 
    limit: number = 20
  ): Promise<CommentListResponse> {
    try {
      const response = await api.get(`/api/v1/contestants/${contestantId}/comments`, {
        params: { skip, limit }
      })
      const data = response.data
      // Fonction récursive pour mapper les commentaires et leurs réponses
      const mapComment = (comment: any): Comment => ({
        ...comment,
        text: comment.content || comment.text,  // Pour compatibilité
        content: comment.content || comment.text,  // S'assurer que content existe
        is_liked: comment.is_liked || false,
        replies: comment.replies ? comment.replies.map(mapComment) : []
      })
      
      const comments = (data.comments || []).map(mapComment)
      return {
        comments,
        total: data.total || 0,
        page: data.page || 1,
        page_size: data.page_size || limit
      }
    } catch (error) {
      console.error('Erreur lors de la récupération des commentaires:', error)
      return { comments: [], total: 0, page: 1, page_size: limit }
    }
  },

  // Récupérer les commentaires pour un média spécifique
  async getMediaComments(
    contestantId: string,
    mediaType: 'photo' | 'video',
    mediaId: string
  ): Promise<Comment[]> {
    try {
      const response = await api.get(
        `/api/v1/contestants/${contestantId}/media/${mediaType}/${mediaId}/comments`
      )
      return response.data.comments || []
    } catch (error) {
      console.error('Erreur lors de la récupération des commentaires du média:', error)
      return []
    }
  },

  // Ajouter un commentaire au contestant
  async addContestantComment(
    contestantId: string,
    text: string,
    parentId?: number | null
  ): Promise<Comment> {
    try {
      const response = await api.post(
        `/api/v1/contestants/${contestantId}/comments`,
        { 
          content: text,  // Utiliser 'content' comme le backend
          target_type: 'contest',
          parent_id: parentId || null
        }
      )
      const comment = response.data
      // Mapper le commentaire retourné pour correspondre à l'interface Comment
      return {
        ...comment,
        text: comment.content || comment.text,
        content: comment.content || comment.text,
        is_liked: comment.is_liked || false,
        replies: comment.replies ? comment.replies.map((r: any) => ({
          ...r,
          text: r.content || r.text,
          content: r.content || r.text,
          is_liked: r.is_liked || false,
          replies: r.replies || []
        })) : []
      }
    } catch (error) {
      console.error('Erreur lors de l\'ajout du commentaire:', error)
      throw error
    }
  },

  // Ajouter un commentaire à un média
  async addMediaComment(
    contestantId: string,
    mediaType: 'photo' | 'video',
    mediaId: string,
    text: string
  ): Promise<CommentResponse> {
    try {
      const response = await api.post(
        `/api/v1/contestants/${contestantId}/media/${mediaType}/${mediaId}/comments`,
        { text, target_type: mediaType }
      )
      return response.data
    } catch (error) {
      console.error('Erreur lors de l\'ajout du commentaire au média:', error)
      throw error
    }
  },

  // Supprimer un commentaire
  async deleteComment(commentId: string): Promise<void> {
    try {
      await api.delete(`/api/v1/comments/${commentId}`)
    } catch (error) {
      console.error('Erreur lors de la suppression du commentaire:', error)
      throw error
    }
  },

  // Mettre à jour un commentaire
  async updateComment(commentId: string, text: string): Promise<CommentResponse> {
    try {
      const response = await api.put(`/api/v1/comments/${commentId}`, { text })
      return response.data
    } catch (error) {
      console.error('Erreur lors de la mise à jour du commentaire:', error)
      throw error
    }
  },

  // Liker un commentaire
  async likeComment(commentId: string | number): Promise<any> {
    try {
      const response = await api.post(`/api/v1/contestants/comment/${commentId}/like`)
      return response.data
    } catch (error) {
      console.error('Erreur lors du like du commentaire:', error)
      throw error
    }
  },

  // Retirer le like d'un commentaire
  async unlikeComment(commentId: string | number): Promise<any> {
    try {
      const response = await api.post(`/api/v1/contestants/comment/${commentId}/unlike`)
      return response.data
    } catch (error) {
      console.error('Erreur lors du retrait du like:', error)
      throw error
    }
  },

  // Récupérer les réponses d'un commentaire
  async getCommentReplies(
    commentId: string | number,
    skip: number = 0,
    limit: number = 20
  ): Promise<CommentListResponse> {
    try {
      const response = await api.get(`/api/v1/contestants/comment/${commentId}/replies`, {
        params: { skip, limit }
      })
      const data = response.data
      // Fonction récursive pour mapper les commentaires et leurs réponses
      const mapComment = (comment: any): Comment => ({
        ...comment,
        text: comment.content || comment.text,
        content: comment.content || comment.text,
        is_liked: comment.is_liked || false,
        replies: comment.replies ? comment.replies.map(mapComment) : []
      })
      
      const comments = (data.comments || []).map(mapComment)
      return {
        comments,
        total: data.total || 0,
        page: data.page || 1,
        page_size: data.page_size || limit
      }
    } catch (error) {
      console.error('Erreur lors de la récupération des réponses:', error)
      return { comments: [], total: 0, page: 1, page_size: limit }
    }
  },

  // Récupérer la liste des utilisateurs ayant commenté sur un contestant
  async getContestantCommenters(contestantId: string | number): Promise<Array<{
    id: number
    username: string
    name: string
    avatar_url?: string
  }>> {
    try {
      const response = await api.get(`/api/v1/contestants/${contestantId}/commenters`)
      return response.data || []
    } catch (error) {
      console.error('Erreur lors de la récupération des commentateurs:', error)
      return []
    }
  }
}
