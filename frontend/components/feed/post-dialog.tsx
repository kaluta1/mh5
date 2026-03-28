'use client'

import { useEffect, useState } from 'react'
import { X, BarChart3, Globe, Users, Lock, Smile, MapPin, Calendar, Plus } from 'lucide-react'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { UploadButton } from '@/components/ui/upload-button'
import { socialService, CreatePostRequest, Post } from '@/services/social-service'
import { useAuth } from '@/hooks/use-auth'
import { UserAvatar } from '@/components/user/user-avatar'
import { cn } from '@/lib/utils'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { MentionTextarea } from '@/components/feed/mention-textarea'

interface PostDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onPostCreated?: () => void
  postToEdit?: Post | null
  onPostUpdated?: (post: Post) => void
}

export function PostDialog({ open, onOpenChange, onPostCreated, postToEdit, onPostUpdated }: PostDialogProps) {
  const { user } = useAuth()
  const { t } = useLanguage()
  const { addToast } = useToast()
  const [content, setContent] = useState('')
  const [visibility, setVisibility] = useState<'public' | 'followers' | 'private'>('public')
  const [mediaIds, setMediaIds] = useState<number[]>([])
  const [poll, setPoll] = useState<{ question: string; options: string[] } | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [activeTab, setActiveTab] = useState<'post' | 'poll'>('post')
  const [charCount, setCharCount] = useState(0)
  const isEditing = Boolean(postToEdit)

  const maxChars = 280

  useEffect(() => {
    if (!open) return

    if (postToEdit) {
      const nextContent = postToEdit.content || ''
      setContent(nextContent)
      setVisibility(postToEdit.visibility || 'public')
      setMediaIds([])
      setPoll(null)
      setActiveTab('post')
      setCharCount(nextContent.length)
      return
    }

    setContent('')
    setVisibility('public')
    setMediaIds([])
    setPoll(null)
    setActiveTab('post')
    setCharCount(0)
  }, [open, postToEdit])

  const handleSubmit = async () => {
    if (!content.trim() && mediaIds.length === 0 && !poll) return
    if (poll) {
      addToast(t('dashboard.feed.poll_not_supported') || 'Poll posting is not available yet.', 'error')
      return
    }

    setIsLoading(true)
    try {
      const validMediaIds = mediaIds.filter((id) => Number.isInteger(id) && id > 0)
      const postData: CreatePostRequest = {
        content: content.trim(),
        visibility,
        media_ids: validMediaIds.length > 0 ? validMediaIds : undefined,
      }

      if (postToEdit) {
        const updatedPost = await socialService.updatePost(postToEdit.id, {
          content: postData.content,
          visibility: postData.visibility,
        })
        onPostUpdated?.(updatedPost)
        addToast('Post updated successfully!', 'success')
      } else {
        await socialService.createPost(postData)
        onPostCreated?.()
        addToast(t('dashboard.feed.post_success') || 'Post created successfully!', 'success')
      }
      handleClose()
    } catch (error) {
      console.error(`Error ${postToEdit ? 'updating' : 'creating'} post:`, error)
      addToast(
        postToEdit
          ? (t('dashboard.feed.post_error') || 'Failed to update post. Please try again.')
          : (t('dashboard.feed.post_error') || 'Failed to create post. Please try again.'),
        'error'
      )
    } finally {
      setIsLoading(false)
    }
  }

  const handleClose = () => {
    setContent('')
    setMediaIds([])
    setPoll(null)
    setVisibility('public')
    setActiveTab('post')
    setCharCount(0)
    onOpenChange(false)
  }

  const addPollOption = () => {
    if (!poll) {
      setPoll({ question: '', options: ['', ''] })
    } else {
      setPoll({ ...poll, options: [...poll.options, ''] })
    }
  }

  const updatePollOption = (index: number, value: string) => {
    if (!poll) return
    const newOptions = [...poll.options]
    newOptions[index] = value
    setPoll({ ...poll, options: newOptions })
  }

  const removePollOption = (index: number) => {
    if (!poll || poll.options.length <= 2) return
    const newOptions = poll.options.filter((_, i) => i !== index)
    setPoll({ ...poll, options: newOptions })
  }

  const canPost = (content.trim().length > 0 || mediaIds.length > 0 || (poll && poll.question.trim())) && charCount <= maxChars

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] p-0 gap-0 bg-white dark:bg-gray-900 rounded-2xl overflow-hidden flex flex-col">
        <DialogHeader className="sr-only">
          <DialogTitle>{isEditing ? (t('edit') || 'Edit post') : (t('dashboard.feed.create_post_dialog_title') || 'Create a post')}</DialogTitle>
          <DialogDescription>
            {isEditing
              ? 'Update your post before saving your changes.'
              : (t('dashboard.feed.post_placeholder') || "Write your post and publish it to your feed.")}
          </DialogDescription>
        </DialogHeader>
        {/* Header */}
        <div className="flex flex-col gap-3 px-4 sm:px-6 py-4 border-b border-gray-200 dark:border-gray-800 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3 min-w-0">
            <Button
              variant="ghost"
              size="icon"
              onClick={handleClose}
              className="h-9 w-9 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800"
            >
              <X className="h-5 w-5" />
            </Button>
            <h2 className="truncate text-lg sm:text-xl font-bold text-gray-900 dark:text-white">
              {isEditing ? (t('edit') || 'Edit post') : (t('dashboard.feed.create_post_dialog_title') || 'Create a post')}
            </h2>
          </div>
          <Button
            onClick={handleSubmit}
            disabled={!canPost || isLoading}
            className="w-full sm:w-auto rounded-full bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white font-semibold px-6 h-10 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading
              ? (isEditing ? 'Saving...' : (t('dashboard.feed.posting') || 'Posting...'))
              : (isEditing ? 'Save changes' : (t('dashboard.feed.post') || 'Post'))}
          </Button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-4">
          <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'post' | 'poll')}>
            <TabsList className={`grid w-full ${isEditing ? 'grid-cols-1' : 'grid-cols-2'} mb-6 bg-gray-100 dark:bg-gray-800 rounded-xl p-1`}>
              <TabsTrigger 
                value="post" 
                className="rounded-lg data-[state=active]:bg-white dark:data-[state=active]:bg-gray-700 data-[state=active]:shadow-sm"
              >
                {t('dashboard.feed.post_tab') || 'Post'}
              </TabsTrigger>
              {!isEditing && (
                <TabsTrigger 
                  value="poll"
                  className="rounded-lg data-[state=active]:bg-white dark:data-[state=active]:bg-gray-700 data-[state=active]:shadow-sm"
                >
                  {t('dashboard.feed.poll_tab') || 'Poll'}
                </TabsTrigger>
              )}
            </TabsList>

            <TabsContent value="post" className="mt-0 space-y-4">
              <div className="flex gap-4">
                <UserAvatar user={user} className="w-12 h-12 flex-shrink-0" />
                <div className="flex-1 space-y-4">
                  <div>
                    <MentionTextarea
                      placeholder={t('dashboard.feed.post_placeholder') || "What's on your mind?"}
                      value={content}
                      onChange={(nextValue) => {
                        setContent(nextValue)
                        setCharCount(nextValue.length)
                      }}
                      className="min-h-[150px] resize-none border-0 text-lg p-0 focus-visible:ring-0 focus-visible:ring-offset-0 bg-transparent placeholder:text-gray-400 dark:placeholder:text-gray-500"
                      autoFocus
                    />
                    
                    {/* Media Preview */}
                    {mediaIds.length > 0 && (
                      <div className="mt-4 p-3 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
                        <p className="text-sm text-gray-600 dark:text-gray-400">
                          {mediaIds.length} {t('dashboard.feed.files_selected') || 'file(s) selected'}
                        </p>
                      </div>
                    )}
                  </div>

                  {/* Action Bar */}
                  <div className="flex flex-col gap-3 pt-4 border-t border-gray-200 dark:border-gray-800 lg:flex-row lg:items-center lg:justify-between">
                    <div className="flex flex-wrap items-center gap-1">
                      {!isEditing && (
                        <>
                          <UploadButton
                            endpoint="imageUploader"
                            onClientUploadComplete={(res) => {
                              if (res) {
                                const uploadedIds = res
                                  .map((r: any) => Number.parseInt(String(r?.key ?? ''), 10))
                                  .filter((id: number) => Number.isInteger(id) && id > 0)
                                setMediaIds([...mediaIds, ...uploadedIds])
                              }
                            }}
                            onUploadError={(error) => {
                              console.error('Upload error:', error)
                            }}
                          />
                          <UploadButton
                            endpoint="videoUploader"
                            onClientUploadComplete={(res) => {
                              if (res) {
                                const uploadedIds = res
                                  .map((r: any) => Number.parseInt(String(r?.key ?? ''), 10))
                                  .filter((id: number) => Number.isInteger(id) && id > 0)
                                setMediaIds([...mediaIds, ...uploadedIds])
                              }
                            }}
                            onUploadError={(error) => {
                              console.error('Upload error:', error)
                            }}
                          />
                          <button 
                            onClick={() => setActiveTab('poll')}
                            className="p-2.5 rounded-full hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors group"
                            title={t('dashboard.feed.poll') || 'Poll'}
                          >
                            <BarChart3 className="h-5 w-5 text-blue-500 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors" />
                          </button>
                        </>
                      )}
                      <button 
                        className="p-2.5 rounded-full hover:bg-yellow-50 dark:hover:bg-yellow-900/20 transition-colors group"
                        title={t('dashboard.feed.emoji') || 'Emoji'}
                      >
                        <Smile className="h-5 w-5 text-yellow-500 group-hover:text-yellow-600 dark:group-hover:text-yellow-400 transition-colors" />
                      </button>
                      <button 
                        className="p-2.5 rounded-full hover:bg-green-50 dark:hover:bg-green-900/20 transition-colors group"
                        title={t('dashboard.feed.schedule') || 'Schedule'}
                      >
                        <Calendar className="h-5 w-5 text-green-500 group-hover:text-green-600 dark:group-hover:text-green-400 transition-colors" />
                      </button>
                      <button 
                        className="p-2.5 rounded-full hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors group"
                        title={t('dashboard.feed.location') || 'Location'}
                      >
                        <MapPin className="h-5 w-5 text-red-500 group-hover:text-red-600 dark:group-hover:text-red-400 transition-colors" />
                      </button>
                    </div>
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between lg:justify-end lg:gap-4">
                      {charCount > 0 && (
                        <span className={cn(
                          "text-sm font-medium",
                          charCount > maxChars ? "text-red-500" : charCount > maxChars * 0.9 ? "text-yellow-500" : "text-gray-500 dark:text-gray-400"
                        )}>
                          {charCount}/{maxChars}
                        </span>
                      )}
                      <div className="flex flex-wrap items-center gap-1 bg-gray-100 dark:bg-gray-800 rounded-2xl p-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setVisibility('public')}
                          className={cn(
                            "h-8 rounded-full text-xs px-3",
                            visibility === 'public' 
                              ? "bg-white dark:bg-gray-700 text-myhigh5-primary shadow-sm" 
                              : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
                          )}
                          title={t('dashboard.feed.public_visibility') || 'Public'}
                        >
                          <Globe className="h-3.5 w-3.5 mr-1.5" />
                          {t('dashboard.feed.public_visibility') || 'Public'}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setVisibility('followers')}
                          className={cn(
                            "h-8 rounded-full text-xs px-3",
                            visibility === 'followers' 
                              ? "bg-white dark:bg-gray-700 text-myhigh5-primary shadow-sm" 
                              : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
                          )}
                          title={t('dashboard.feed.followers_visibility') || 'Followers'}
                        >
                          <Users className="h-3.5 w-3.5 mr-1.5" />
                          {t('dashboard.feed.followers_visibility') || 'Followers'}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setVisibility('private')}
                          className={cn(
                            "h-8 rounded-full text-xs px-3",
                            visibility === 'private' 
                              ? "bg-white dark:bg-gray-700 text-myhigh5-primary shadow-sm" 
                              : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
                          )}
                          title={t('dashboard.feed.private_visibility') || 'Private'}
                        >
                          <Lock className="h-3.5 w-3.5 mr-1.5" />
                          {t('dashboard.feed.private_visibility') || 'Private'}
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </TabsContent>

            <TabsContent value="poll" className="mt-0 space-y-4">
              <div className="flex gap-4">
                <UserAvatar user={user} className="w-12 h-12 flex-shrink-0" />
                <div className="flex-1 space-y-4">
                  <div>
                    <MentionTextarea
                      placeholder={t('dashboard.feed.poll_question_placeholder') || 'Ask your question...'}
                      value={poll?.question || ''}
                      onChange={(nextValue) => setPoll(poll ? { ...poll, question: nextValue } : { question: nextValue, options: ['', ''] })}
                      className="min-h-[100px] resize-none border-0 text-lg p-0 focus-visible:ring-0 bg-transparent placeholder:text-gray-400 dark:placeholder:text-gray-500"
                      autoFocus
                    />
                  </div>

                  <div className="space-y-3">
                    <label className="text-sm font-semibold text-gray-700 dark:text-gray-300 block">
                      {t('dashboard.feed.poll_options_label') || 'Poll options'}
                    </label>
                    <div className="space-y-2">
                      {poll?.options.map((option, index) => (
                        <div key={index} className="flex items-center gap-2">
                          <input
                            type="text"
                            placeholder={`${t('dashboard.feed.poll_option_placeholder') || 'Option'} ${index + 1}`}
                            value={option}
                            onChange={(e) => updatePollOption(index, e.target.value)}
                            className="flex-1 px-4 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-myhigh5-primary focus:border-transparent"
                          />
                          {poll.options.length > 2 && (
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => removePollOption(index)}
                              className="h-10 w-10 rounded-full hover:bg-red-50 dark:hover:bg-red-900/20"
                            >
                              <X className="h-4 w-4 text-red-500" />
                            </Button>
                          )}
                        </div>
                      ))}
                      <Button
                        variant="outline"
                        onClick={addPollOption}
                        className="w-full rounded-full border-dashed hover:border-myhigh5-primary hover:text-myhigh5-primary"
                      >
                        <Plus className="h-4 w-4 mr-2" />
                        {t('dashboard.feed.add_poll_option') || 'Add an option'}
                      </Button>
                    </div>
                  </div>
                </div>
              </div>
            </TabsContent>
          </Tabs>
        </div>
      </DialogContent>
    </Dialog>
  )
}
