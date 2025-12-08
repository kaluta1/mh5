'use client'

import { useState, useRef, useEffect } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { useLanguage } from '@/contexts/language-context'
import { 
  Mic, 
  MicOff,
  Square,
  Play,
  RotateCcw,
  Check,
  X,
  Loader2,
  Volume2
} from 'lucide-react'
import { verificationService } from '@/services/verification-service'

interface VoiceVerificationDialogProps {
  isOpen: boolean
  onClose: () => void
  onComplete: (audioUrl: string) => void
  maxDurationSeconds?: number
  maxSizeMb?: number
  contestId?: number
  contestantId?: number
}

export function VoiceVerificationDialog({
  isOpen,
  onClose,
  onComplete,
  maxDurationSeconds = 30,
  maxSizeMb = 50,
  contestId,
  contestantId
}: VoiceVerificationDialogProps) {
  const { t } = useLanguage()
  const [mode, setMode] = useState<'idle' | 'recording' | 'preview'>('idle')
  const [recordedAudio, setRecordedAudio] = useState<Blob | null>(null)
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [recordingTime, setRecordingTime] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const timerRef = useRef<NodeJS.Timeout | null>(null)
  const streamRef = useRef<MediaStream | null>(null)

  useEffect(() => {
    return () => {
      stopRecording()
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl)
      }
    }
  }, [audioUrl])

  const startRecording = async () => {
    try {
      setError(null)
      chunksRef.current = []
      
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      
      const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' })
      mediaRecorderRef.current = mediaRecorder
      
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data)
        }
      }
      
      mediaRecorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        setRecordedAudio(blob)
        const url = URL.createObjectURL(blob)
        setAudioUrl(url)
        setMode('preview')
      }
      
      mediaRecorder.start(100)
      setMode('recording')
      setRecordingTime(0)
      
      // Start timer
      timerRef.current = setInterval(() => {
        setRecordingTime(prev => {
          if (prev >= maxDurationSeconds - 1) {
            stopRecording()
            return prev
          }
          return prev + 1
        })
      }, 1000)
      
    } catch (err) {
      console.error('Microphone error:', err)
      setError(t('verification.microphone_error') || 'Impossible d\'accéder au microphone')
    }
  }

  const stopRecording = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }
    
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop())
      streamRef.current = null
    }
  }

  const playAudio = () => {
    if (audioRef.current && audioUrl) {
      audioRef.current.play()
      setIsPlaying(true)
    }
  }

  const stopAudio = () => {
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
      setIsPlaying(false)
    }
  }

  const retake = () => {
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl)
    }
    setRecordedAudio(null)
    setAudioUrl(null)
    setRecordingTime(0)
    setMode('idle')
  }

  const handleSubmit = async () => {
    if (!recordedAudio) return
    
    // Check file size
    if (recordedAudio.size > maxSizeMb * 1024 * 1024) {
      setError(t('verification.file_too_large') || `L'enregistrement est trop volumineux (max ${maxSizeMb}MB)`)
      return
    }
    
    setIsUploading(true)
    try {
      // Upload et créer la vérification
      const verification = await verificationService.uploadAndCreateVerification(
        recordedAudio,
        `voice_${Date.now()}.webm`,
        'voice',
        'audio',
        {
          duration_seconds: recordingTime,
          contest_id: contestId,
          contestant_id: contestantId
        }
      )
      
      onComplete(verification.media_url)
      handleClose()
    } catch (err) {
      console.error('Voice verification upload error:', err)
      setError(err instanceof Error ? err.message : (t('verification.upload_error') || 'Erreur lors de l\'envoi'))
    } finally {
      setIsUploading(false)
    }
  }

  const handleClose = () => {
    stopRecording()
    stopAudio()
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl)
    }
    setRecordedAudio(null)
    setAudioUrl(null)
    setRecordingTime(0)
    setMode('idle')
    setError(null)
    onClose()
  }

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Mic className="w-5 h-5 text-myfav-primary" />
            {t('verification.voice_verification') || 'Vérification vocale'}
          </DialogTitle>
          <DialogDescription>
            {t('verification.voice_instructions') || `Enregistrez votre voix pendant quelques secondes (max ${maxDurationSeconds}s).`}
          </DialogDescription>
        </DialogHeader>

        <div className="py-4">
          {/* Error message */}
          {error && (
            <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-center gap-2 text-red-700 dark:text-red-300">
              <X className="w-4 h-4" />
              <span className="text-sm">{error}</span>
            </div>
          )}

          {/* Recording visualization */}
          <div className="flex flex-col items-center justify-center py-8">
            {/* Timer display */}
            <div className="text-4xl font-mono font-bold text-gray-900 dark:text-white mb-6">
              {formatTime(recordingTime)} / {formatTime(maxDurationSeconds)}
            </div>

            {/* Recording button */}
            <div className="relative">
              {mode === 'recording' && (
                <div className="absolute inset-0 animate-ping">
                  <div className="w-24 h-24 rounded-full bg-red-400/30" />
                </div>
              )}
              <button
                onClick={mode === 'recording' ? stopRecording : startRecording}
                disabled={mode === 'preview'}
                className={`relative w-24 h-24 rounded-full flex items-center justify-center transition-all ${
                  mode === 'recording'
                    ? 'bg-red-500 hover:bg-red-600'
                    : mode === 'preview'
                    ? 'bg-gray-300 dark:bg-gray-700 cursor-not-allowed'
                    : 'bg-myfav-primary hover:bg-myfav-primary-dark'
                }`}
              >
                {mode === 'recording' ? (
                  <Square className="w-8 h-8 text-white" />
                ) : (
                  <Mic className="w-10 h-10 text-white" />
                )}
              </button>
            </div>

            {/* Status text */}
            <p className="mt-4 text-sm text-gray-600 dark:text-gray-400">
              {mode === 'idle' && (t('verification.tap_to_record') || 'Appuyez pour enregistrer')}
              {mode === 'recording' && (t('verification.recording') || 'Enregistrement en cours...')}
              {mode === 'preview' && (t('verification.recording_complete') || 'Enregistrement terminé')}
            </p>
          </div>

          {/* Preview controls */}
          {mode === 'preview' && audioUrl && (
            <div className="space-y-4">
              <audio 
                ref={audioRef} 
                src={audioUrl} 
                onEnded={() => setIsPlaying(false)}
                className="hidden"
              />
              
              <div className="flex justify-center gap-4">
                <Button 
                  variant="outline" 
                  size="lg"
                  onClick={isPlaying ? stopAudio : playAudio}
                >
                  {isPlaying ? (
                    <>
                      <Square className="w-4 h-4 mr-2" />
                      {t('verification.stop') || 'Stop'}
                    </>
                  ) : (
                    <>
                      <Play className="w-4 h-4 mr-2" />
                      {t('verification.play') || 'Écouter'}
                    </>
                  )}
                </Button>
              </div>
              
              <div className="flex gap-3">
                <Button variant="outline" onClick={retake} className="flex-1">
                  <RotateCcw className="w-4 h-4 mr-2" />
                  {t('verification.retake') || 'Reprendre'}
                </Button>
                <Button 
                  onClick={handleSubmit} 
                  disabled={isUploading}
                  className="flex-1 bg-myfav-primary hover:bg-myfav-primary-dark"
                >
                  {isUploading ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <Check className="w-4 h-4 mr-2" />
                  )}
                  {t('verification.confirm') || 'Confirmer'}
                </Button>
              </div>
            </div>
          )}

          {/* Cancel button for idle mode */}
          {mode === 'idle' && (
            <div className="mt-4">
              <Button variant="outline" onClick={handleClose} className="w-full">
                {t('common.cancel') || 'Annuler'}
              </Button>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
