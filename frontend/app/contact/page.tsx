"use client"

import * as React from "react"
import { useState } from "react"
import { Header } from "@/components/layout/header"
import { Footer } from "@/components/sections/footer"
import { useLanguage } from "@/contexts/language-context"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { apiService } from "@/lib/api"
import { 
  Mail, 
  MapPin, 
  Send, 
  MessageSquare,
  Clock,
  Globe,
  HelpCircle,
  FileText,
  Users,
  Headphones,
  CheckCircle
} from "lucide-react"

export default function ContactPage() {
  const { t, language } = useLanguage()

  const contactMethodsData: Record<string, { title: string; description: string; value: string }[]> = {
    en: [
      { title: "Email", description: "Send us an email", value: "infos@myhigh5.com" },
      { title: "Live Chat", description: "Instant response", value: "Available 24/7" },
      { title: "Headquarters", description: "In progress", value: "British Columbia" }
    ],
    fr: [
      { title: "Email", description: "Envoyez-nous un email", value: "infos@myhigh5.com" },
      { title: "Chat en direct", description: "Réponse instantanée", value: "Disponible 24/7" },
      { title: "Siège social", description: "En cours", value: "Colombie-Britannique" }
    ],
    es: [
      { title: "Email", description: "Envíanos un email", value: "infos@myhigh5.com" },
      { title: "Chat en vivo", description: "Respuesta instantánea", value: "Disponible 24/7" },
      { title: "Sede central", description: "En progreso", value: "Columbia Británica" }
    ],
    de: [
      { title: "E-Mail", description: "Senden Sie uns eine E-Mail", value: "infos@myhigh5.com" },
      { title: "Live-Chat", description: "Sofortige Antwort", value: "24/7 verfügbar" },
      { title: "Hauptsitz", description: "In Bearbeitung", value: "British Columbia" }
    ]
  }

  const contactMethods = [
    { icon: Mail, action: "mailto:infos@myhigh5.com", ...contactMethodsData[language]?.[0] || contactMethodsData.en[0] },
    { icon: MessageSquare, action: "#chat", ...contactMethodsData[language]?.[1] || contactMethodsData.en[1] },
    { icon: MapPin, action: "#", ...contactMethodsData[language]?.[2] || contactMethodsData.en[2] }
  ]

  const faqData: Record<string, { question: string; answer: string }[]> = {
    en: [
      { question: "How to participate in a contest?", answer: "Create an account, verify it, complete your profile, and click 'Participate' on the contest of your choice." },
      { question: "How does the MyHigh5 voting system work?", answer: "Select up to 5 favorites and rank them by drag-and-drop. 1st gets 5 points, 2nd 4 points, etc." },
      { question: "How to create a Fan Club?", answer: "After identity verification, go to your dashboard and click 'Create a Club'." },
      { 
        question: "How does the affiliate program work?", 
        answer: "• For verification fee payments: you earn a 10% commission on payments made by your direct referrals, and a 1% commission on payments made by each of your indirect referrals from Level 2 to Level 10.\n• For ad revenue: participating contestants receive 40% of the ad revenue generated on their contest pages. The direct sponsor of a participating contestant receives 5%, and each indirect sponsor from Level 2 to Level 10 receives 1%.\n• Nominating members: receive 10% of the ad revenue generated on the contest pages of their nominated contestants, 2.5% of the ad revenue generated on the contest pages of contestants nominated by their direct referrals, and 1% of the ad revenue generated on the contest pages of contestants nominated by each of their indirect referrals from Level 2 to Level 10.\n• For clubs: club owners receive 20% of the ad revenue generated on their club or fan pages. The direct sponsor of a club owner receives 5%, and each indirect sponsor from Level 2 to Level 10 receives 0.5%.\n• Club membership fees: MyHigh5 applies a 10% markup to the member's selected subscription fee. Of this markup, 10% is paid to the direct sponsor of the payer, and 1% is paid to each indirect sponsor from Level 2 to Level 10.\n• Website Sponsors page: for slots paid for on the Website Sponsors page, 10% is paid to the Level 1 sponsor, and 1% is paid to each of the Level 2 through Level 10 sponsors."
      }
    ],
    fr: [
      { question: "Comment participer à un concours ?", answer: "Créez un compte, vérifiez-le, complétez votre profil et cliquez sur 'Participer' sur le concours de votre choix." },
      { question: "Comment fonctionne le système de vote MyHigh5 ?", answer: "Sélectionnez jusqu'à 5 favoris et classez-les par glisser-déposer. Le 1er reçoit 5 points, le 2ème 4 points, etc." },
      { question: "Comment créer un Fan Club ?", answer: "Après vérification de votre identité, accédez à votre tableau de bord et cliquez sur 'Créer un Club'." },
      { 
        question: "Comment fonctionne le programme d'affiliation ?", 
        answer: "• Paiements de frais de vérification : vous gagnez 10% sur les paiements de vos parrainages directs, et 1% sur ceux de vos parrainages indirects du niveau 2 au niveau 10.\n• Revenus publicitaires : les candidats participants reçoivent 40% des revenus publicitaires générés sur leurs pages de concours. Le parrain direct reçoit 5%, et chaque parrain indirect du niveau 2 au niveau 10 reçoit 1%.\n• Membres nominants : reçoivent 10% des revenus publicitaires générés sur les pages de concours de leurs candidats nommés, 2.5% sur ceux générés par les candidats nommés par leurs parrainages directs, et 1% sur ceux générés par les candidats nommés par leurs parrainages indirects du niveau 2 au niveau 10.\n• Clubs : les propriétaires de clubs reçoivent 20% des revenus publicitaires générés sur leurs pages de club ou de fans. Le parrain direct reçoit 5%, et chaque parrain indirect du niveau 2 au niveau 10 reçoit 0.5%.\n• Frais d'adhésion aux clubs : MyHigh5 applique une majoration de 10% aux frais d'abonnement sélectionnés par le membre. De cette majoration, 10% est versé au parrain direct du payeur, et 1% est versé à chaque parrain indirect du niveau 2 au niveau 10.\n• Page des Sponsors du Site Web : pour les emplacements payés, 10% est versé au parrain de niveau 1, et 1% est versé à chacun des parrains des niveaux 2 à 10."
      }
    ],
    es: [
      { question: "¿Cómo participar en un concurso?", answer: "Crea una cuenta, verifícala, completa tu perfil y haz clic en 'Participar' en el concurso de tu elección." },
      { question: "¿Cómo funciona el sistema de votación MyHigh5?", answer: "Selecciona hasta 5 favoritos y ordénalos arrastrando y soltando. El 1º recibe 5 puntos, el 2º 4 puntos, etc." },
      { question: "¿Cómo crear un Fan Club?", answer: "Después de verificar tu identidad, ve a tu panel y haz clic en 'Crear un Club'." },
      { 
        question: "¿Cómo funciona el programa de afiliados?", 
        answer: "• Tarifas de verificación: ganas una comisión del 10% sobre los pagos realizados por tus referidos directos, y una comisión del 1% sobre los pagos realizados por cada uno de tus referidos indirectos del Nivel 2 al Nivel 10.\n• Ingresos publicitarios: los concursantes participantes reciben el 40% de los ingresos publicitarios generados en sus páginas de concurso. El patrocinador directo de un concursante participante recibe el 5%, y cada patrocinador indirecto del Nivel 2 al Nivel 10 recibe el 1%.\n• Miembros que nominan: reciben el 10% de los ingresos publicitarios generados en las páginas de concurso de sus concursantes nominados, el 2.5% de los ingresos publicitarios generados en las páginas de concurso de concursantes nominados por sus referidos directos, y el 1% de los ingresos publicitarios generados en las páginas de concurso de concursantes nominados por cada uno de sus referidos indirectos del Nivel 2 al Nivel 10.\n• Clubes: los propietarios de clubes reciben el 20% de los ingresos publicitarios generados en sus páginas de club o fan. El patrocinador directo de un propietario de club recibe el 5%, y cada patrocinador indirecto del Nivel 2 al Nivel 10 recibe el 0.5%.\n• Tarifas de membresía del club: MyHigh5 aplica un margen del 10% a la tarifa de suscripción seleccionada por el miembro. De este margen, el 10% se paga al patrocinador directo del pagador, y el 1% se paga a cada patrocinador indirecto del Nivel 2 al Nivel 10.\n• Página de Patrocinadores del Sitio Web: para los espacios pagados, 10% se paga al patrocinador de Nivel 1, y 1% se paga a cada uno de los patrocinadores de los Niveles 2 a 10."
      }
    ],
    de: [
      { question: "Wie nehme ich an einem Wettbewerb teil?", answer: "Erstellen Sie ein Konto, verifizieren Sie es, vervollständigen Sie Ihr Profil und klicken Sie auf 'Teilnehmen' beim Wettbewerb Ihrer Wahl." },
      { question: "Wie funktioniert das MyHigh5-Abstimmungssystem?", answer: "Wählen Sie bis zu 5 Favoriten aus und ordnen Sie sie per Drag-and-Drop. Der 1. erhält 5 Punkte, der 2. 4 Punkte, usw." },
      { question: "Wie erstelle ich einen Fan Club?", answer: "Nach der Identitätsüberprüfung gehen Sie zu Ihrem Dashboard und klicken Sie auf 'Club erstellen'." },
      { 
        question: "Wie funktioniert das Partnerprogramm?", 
        answer: "• Verifizierungsgebühren: Sie erhalten eine Provision von 10% auf Zahlungen Ihrer direkten Empfehlungen und eine Provision von 1% auf Zahlungen jeder Ihrer indirekten Empfehlungen von Stufe 2 bis Stufe 10.\n• Werbeeinnahmen: Teilnehmende Kandidaten erhalten 40% der Werbeeinnahmen, die auf ihren Wettbewerbsseiten generiert werden. Der direkte Sponsor erhält 5%, und jeder indirekte Sponsor von Stufe 2 bis Stufe 10 erhält 1%.\n• Nominierende Mitglieder: erhalten 10% der Werbeeinnahmen, die auf den Wettbewerbsseiten ihrer nominierten Kandidaten generiert werden, 2.5% der Werbeeinnahmen, die auf den Wettbewerbsseiten von Kandidaten generiert werden, die von ihren direkten Empfehlungen nominiert wurden, und 1% der Werbeeinnahmen, die auf den Wettbewerbsseiten von Kandidaten generiert werden, die von jeder ihrer indirekten Empfehlungen von Stufe 2 bis Stufe 10 nominiert wurden.\n• Clubs: Clubbesitzer erhalten 20% der Werbeeinnahmen, die auf ihren Club- oder Fan-Seiten generiert werden. Der direkte Sponsor eines Clubbesitzers erhält 5%, und jeder indirekte Sponsor von Stufe 2 bis Stufe 10 erhält 0.5%.\n• Club-Mitgliedsgebühren: MyHigh5 wendet einen Aufschlag von 10% auf die vom Mitglied ausgewählte Abonnementgebühr an. Von diesem Aufschlag werden 10% an den direkten Sponsor des Zahlers gezahlt, und 1% werden an jeden indirekten Sponsor von Stufe 2 bis Stufe 10 gezahlt.\n• Website-Sponsoren-Seite: für bezahlte Plätze werden 10% an den Stufe-1-Patron gezahlt, und 1% wird an jeden der Stufe-2-bis-Stufe-10-Patrone gezahlt."
      }
    ]
  }
  const faqItems = faqData[language] || faqData.en

  const supportData: Record<string, { title: string; description: string }[]> = {
    en: [
      { title: "General Help", description: "Questions about using the platform" },
      { title: "Billing", description: "Questions about payments and subscriptions" },
      { title: "Account", description: "Login or profile issues" },
      { title: "Technical Support", description: "Bugs and technical problems" }
    ],
    fr: [
      { title: "Aide générale", description: "Questions sur l'utilisation de la plateforme" },
      { title: "Facturation", description: "Questions sur les paiements et abonnements" },
      { title: "Compte", description: "Problèmes de connexion ou de profil" },
      { title: "Support technique", description: "Bugs et problèmes techniques" }
    ],
    es: [
      { title: "Ayuda general", description: "Preguntas sobre el uso de la plataforma" },
      { title: "Facturación", description: "Preguntas sobre pagos y suscripciones" },
      { title: "Cuenta", description: "Problemas de inicio de sesión o perfil" },
      { title: "Soporte técnico", description: "Errores y problemas técnicos" }
    ],
    de: [
      { title: "Allgemeine Hilfe", description: "Fragen zur Nutzung der Plattform" },
      { title: "Abrechnung", description: "Fragen zu Zahlungen und Abonnements" },
      { title: "Konto", description: "Anmelde- oder Profilprobleme" },
      { title: "Technischer Support", description: "Fehler und technische Probleme" }
    ]
  }

  const supportCategories = [
    { icon: HelpCircle, ...supportData[language]?.[0] || supportData.en[0] },
    { icon: FileText, ...supportData[language]?.[1] || supportData.en[1] },
    { icon: Users, ...supportData[language]?.[2] || supportData.en[2] },
    { icon: Headphones, ...supportData[language]?.[3] || supportData.en[3] }
  ]

  const formLabels: Record<string, Record<string, any>> = {
    en: { 
      select_category: "Select a category", 
      general: "General help", 
      billing: "Billing", 
      account: "Account", 
      technical: "Technical support", 
      partnership: "Partnership", 
      other: "Other", 
      sending: "Sending...", 
      sent_title: "Message sent!", 
      sent_desc: "We will respond as soon as possible.", 
      weekdays: "Monday - Friday", 
      saturday: "Saturday", 
      sunday: "Sunday", 
      closed: "Closed", 
      live_chat: "Live chat available 24/7",
      errors: {
        name_required: "Name is required",
        name_min: "Name must be at least 2 characters",
        email_required: "Email is required",
        email_invalid: "Please enter a valid email address",
        subject_required: "Subject is required",
        subject_min: "Subject must be at least 3 characters",
        category_required: "Please select a category",
        message_required: "Message is required",
        message_min: "Message must be at least 10 characters",
        form_invalid: "Please correct the errors in the form",
        submit_error: "An error occurred while sending the message. Please try again.",
        submit_error_400: "The form data is invalid. Please check all fields.",
        submit_error_500: "A server error occurred. Please try again later."
      }
    },
    fr: { 
      select_category: "Sélectionnez une catégorie", 
      general: "Aide générale", 
      billing: "Facturation", 
      account: "Compte", 
      technical: "Support technique", 
      partnership: "Partenariat", 
      other: "Autre", 
      sending: "Envoi en cours...", 
      sent_title: "Message envoyé !", 
      sent_desc: "Nous vous répondrons dans les plus brefs délais.", 
      weekdays: "Lundi - Vendredi", 
      saturday: "Samedi", 
      sunday: "Dimanche", 
      closed: "Fermé", 
      live_chat: "Chat en direct disponible 24/7",
      errors: {
        name_required: "Le nom est requis",
        name_min: "Le nom doit contenir au moins 2 caractères",
        email_required: "L'email est requis",
        email_invalid: "Veuillez entrer une adresse email valide",
        subject_required: "Le sujet est requis",
        subject_min: "Le sujet doit contenir au moins 3 caractères",
        category_required: "Veuillez sélectionner une catégorie",
        message_required: "Le message est requis",
        message_min: "Le message doit contenir au moins 10 caractères",
        form_invalid: "Veuillez corriger les erreurs dans le formulaire",
        submit_error: "Une erreur est survenue lors de l'envoi du message. Veuillez réessayer.",
        submit_error_400: "Les données du formulaire sont invalides. Veuillez vérifier tous les champs.",
        submit_error_500: "Une erreur serveur est survenue. Veuillez réessayer plus tard."
      }
    },
    es: { 
      select_category: "Selecciona una categoría", 
      general: "Ayuda general", 
      billing: "Facturación", 
      account: "Cuenta", 
      technical: "Soporte técnico", 
      partnership: "Asociación", 
      other: "Otro", 
      sending: "Enviando...", 
      sent_title: "¡Mensaje enviado!", 
      sent_desc: "Le responderemos lo antes posible.", 
      weekdays: "Lunes - Viernes", 
      saturday: "Sábado", 
      sunday: "Domingo", 
      closed: "Cerrado", 
      live_chat: "Chat en vivo disponible 24/7",
      errors: {
        name_required: "El nombre es obligatorio",
        name_min: "El nombre debe tener al menos 2 caracteres",
        email_required: "El email es obligatorio",
        email_invalid: "Por favor ingrese una dirección de email válida",
        subject_required: "El asunto es obligatorio",
        subject_min: "El asunto debe tener al menos 3 caracteres",
        category_required: "Por favor seleccione una categoría",
        message_required: "El mensaje es obligatorio",
        message_min: "El mensaje debe tener al menos 10 caracteres",
        form_invalid: "Por favor corrija los errores en el formulario",
        submit_error: "Ocurrió un error al enviar el mensaje. Por favor intente nuevamente.",
        submit_error_400: "Los datos del formulario son inválidos. Por favor verifique todos los campos.",
        submit_error_500: "Ocurrió un error del servidor. Por favor intente más tarde."
      }
    },
    de: { 
      select_category: "Kategorie auswählen", 
      general: "Allgemeine Hilfe", 
      billing: "Abrechnung", 
      account: "Konto", 
      technical: "Technischer Support", 
      partnership: "Partnerschaft", 
      other: "Andere", 
      sending: "Wird gesendet...", 
      sent_title: "Nachricht gesendet!", 
      sent_desc: "Wir werden so schnell wie möglich antworten.", 
      weekdays: "Montag - Freitag", 
      saturday: "Samstag", 
      sunday: "Sonntag", 
      closed: "Geschlossen", 
      live_chat: "Live-Chat 24/7 verfügbar",
      errors: {
        name_required: "Name ist erforderlich",
        name_min: "Name muss mindestens 2 Zeichen lang sein",
        email_required: "E-Mail ist erforderlich",
        email_invalid: "Bitte geben Sie eine gültige E-Mail-Adresse ein",
        subject_required: "Betreff ist erforderlich",
        subject_min: "Betreff muss mindestens 3 Zeichen lang sein",
        category_required: "Bitte wählen Sie eine Kategorie aus",
        message_required: "Nachricht ist erforderlich",
        message_min: "Nachricht muss mindestens 10 Zeichen lang sein",
        form_invalid: "Bitte korrigieren Sie die Fehler im Formular",
        submit_error: "Beim Senden der Nachricht ist ein Fehler aufgetreten. Bitte versuchen Sie es erneut.",
        submit_error_400: "Die Formulardaten sind ungültig. Bitte überprüfen Sie alle Felder.",
        submit_error_500: "Ein Serverfehler ist aufgetreten. Bitte versuchen Sie es später erneut."
      }
    }
  }
  const fl = formLabels[language] || formLabels.en
  const errorMessages = (fl as any).errors || {}
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    subject: "",
    category: "",
    message: ""
  })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [touched, setTouched] = useState<Record<string, boolean>>({})
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isSubmitted, setIsSubmitted] = useState(false)

  // Validation des champs
  const validateField = (name: string, value: string): string => {
    switch (name) {
      case 'name':
        if (!value.trim()) {
          return errorMessages.name_required || 'Name is required'
        }
        if (value.trim().length < 2) {
          return errorMessages.name_min || 'Name must be at least 2 characters'
        }
        break
      case 'email':
        if (!value.trim()) {
          return errorMessages.email_required || 'Email is required'
        }
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
        if (!emailRegex.test(value.trim())) {
          return errorMessages.email_invalid || 'Please enter a valid email address'
        }
        break
      case 'subject':
        if (!value.trim()) {
          return errorMessages.subject_required || 'Subject is required'
        }
        if (value.trim().length < 3) {
          return errorMessages.subject_min || 'Subject must be at least 3 characters'
        }
        break
      case 'category':
        if (!value) {
          return errorMessages.category_required || 'Please select a category'
        }
        break
      case 'message':
        if (!value.trim()) {
          return errorMessages.message_required || 'Message is required'
        }
        if (value.trim().length < 10) {
          return errorMessages.message_min || 'Message must be at least 10 characters'
        }
        break
    }
    return ''
  }

  // Valider tous les champs
  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {}
    
    Object.keys(formData).forEach((key) => {
      const error = validateField(key, formData[key as keyof typeof formData])
      if (error) {
        newErrors[key] = error
      }
    })
    
    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleBlur = (e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value } = e.target
    setTouched(prev => ({ ...prev, [name]: true }))
    
    const error = validateField(name, value)
    if (error) {
      setErrors(prev => ({ ...prev, [name]: error }))
    } else {
      setErrors(prev => {
        const newErrors = { ...prev }
        delete newErrors[name]
        return newErrors
      })
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    // Marquer tous les champs comme touchés
    setTouched({
      name: true,
      email: true,
      subject: true,
      category: true,
      message: true
    })
    
    // Valider le formulaire
    if (!validateForm()) {
      return
    }
    
    setIsSubmitting(true)
    setErrors({}) // Réinitialiser les erreurs
    
    try {
      const payload = {
        name: formData.name.trim(),
        email: formData.email.trim(),
        subject: formData.subject.trim(),
        category: formData.category,
        message: formData.message.trim(),
      }
      
      console.log('Envoi du message de contact:', payload)
      console.log('Endpoint:', '/api/v1/contact')
      console.log('Langue:', language)
      
      // Appeler l'API pour envoyer le message avec la langue dans les headers
      // La langue sera détectée automatiquement depuis les headers Accept-Language du navigateur
      const response = await apiService.post('/api/v1/contact', payload)
      
      console.log('Réponse du serveur:', response)
      
      setIsSubmitting(false)
      setIsSubmitted(true)
      setFormData({ name: "", email: "", subject: "", category: "", message: "" })
      setErrors({})
      setTouched({})
      
      // Reset success message après 5 secondes
      setTimeout(() => setIsSubmitted(false), 5000)
    } catch (error: any) {
      console.error('Erreur complète lors de l\'envoi du message:', error)
      console.error('Erreur response:', error?.response)
      console.error('Erreur message:', error?.message)
      console.error('Erreur status:', error?.response?.status)
      console.error('Erreur data:', error?.response?.data)
      
      setIsSubmitting(false)
      
      // Gérer les erreurs de validation du backend
      if (error?.response?.data?.detail) {
        const detail = error.response.data.detail
        console.log('Detail de l\'erreur:', detail)
        
        // Si c'est une erreur de validation Pydantic, parser les erreurs
        if (typeof detail === 'object' && Array.isArray(detail)) {
          const newErrors: Record<string, string> = {}
          detail.forEach((err: any) => {
            if (err.loc && err.loc.length > 1) {
              const field = err.loc[err.loc.length - 1]
              newErrors[field] = err.msg || errorMessages.submit_error || 'An error occurred'
            }
          })
          if (Object.keys(newErrors).length > 0) {
            setErrors(newErrors)
            return
          }
        } else if (typeof detail === 'string') {
          // Erreur générale
          setErrors({ _general: detail })
          return
        }
      }
      
      // Erreur réseau ou serveur
      let errorMessage = errorMessages.submit_error || 'An error occurred while sending the message. Please try again.'
      
      if (error?.response?.status === 400) {
        errorMessage = errorMessages.submit_error_400 || 'The form data is invalid. Please check all fields.'
      } else if (error?.response?.status === 500) {
        errorMessage = errorMessages.submit_error_500 || 'A server error occurred. Please try again later.'
      } else if (error?.response?.status === 404) {
        errorMessage = 'Endpoint not found. Please check the API configuration.'
      } else if (error?.response?.status === 403) {
        errorMessage = 'Access forbidden. Please check your permissions.'
      } else if (error?.code === 'NETWORK_ERROR' || error?.message?.includes('Network Error')) {
        errorMessage = 'Network error. Please check your internet connection and try again.'
      } else if (error?.message) {
        errorMessage = error.message
      }
      
      console.error('Message d\'erreur final:', errorMessage)
      setErrors({ _general: errorMessage })
    }
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    setFormData(prev => ({
      ...prev,
      [e.target.name]: e.target.value
    }))
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-myhigh5-blue-50 via-white to-myhigh5-cyan-50 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900">
      <Header />
      
      <main className="pt-24 pb-16">
        {/* Hero Section */}
        <section className="relative py-16 bg-gradient-to-r from-myhigh5-primary to-myhigh5-secondary overflow-hidden">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_80%,rgba(255,255,255,0.1),transparent_40%)]" />
          <div className="container px-4 md:px-6 relative z-10">
            <div className="max-w-3xl mx-auto text-center text-white">
              <Headphones className="w-16 h-16 mx-auto mb-6" />
              <h1 className="text-4xl md:text-5xl font-black mb-4">
                {t('pages.contact.title') || "Contactez-nous"}
              </h1>
              <p className="text-xl opacity-90">
                {t('pages.contact.subtitle') || "Notre équipe est là pour vous aider. Nous répondons généralement sous 24h."}
              </p>
            </div>
          </div>
        </section>

        {/* Contact Methods */}
        <section className="container px-4 md:px-6 -mt-10 relative z-20">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {contactMethods.map((method, index) => (
              <a
                key={index}
                href={method.action}
                className="bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-xl border border-gray-200 dark:border-gray-700 hover:shadow-2xl transition-all duration-300 hover:-translate-y-1 group"
              >
                <method.icon className="w-10 h-10 text-myhigh5-primary mb-4 group-hover:scale-110 transition-transform" />
                <h3 className="font-bold text-gray-900 dark:text-white mb-1">
                  {method.title}
                </h3>
                <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">
                  {method.description}
                </p>
                <p className="text-myhigh5-primary font-semibold">
                  {method.value}
                </p>
              </a>
            ))}
          </div>
        </section>

        {/* Contact Form & FAQ */}
        <section className="container px-4 md:px-6 py-16">
          <div className="grid lg:grid-cols-2 gap-12">
            {/* Contact Form */}
            <div>
              <h2 className="text-2xl md:text-3xl font-bold text-gray-900 dark:text-white mb-6">
                {t('pages.contact.form.title') || "Envoyez-nous un message"}
              </h2>
              
              {isSubmitted ? (
                <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-2xl p-8 text-center">
                  <CheckCircle className="w-16 h-16 mx-auto text-green-500 mb-4" />
                  <h3 className="text-xl font-bold text-green-700 dark:text-green-400 mb-2">
                    {fl.sent_title}
                  </h3>
                  <p className="text-green-600 dark:text-green-500">
                    {fl.sent_desc}
                  </p>
                </div>
              ) : (
                <form onSubmit={handleSubmit} className="space-y-5">
                  {/* Message d'erreur général */}
                  {errors._general && (
                    <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
                      <p className="text-sm text-red-700 dark:text-red-400">{errors._general}</p>
                    </div>
                  )}
                  
                  <div className="grid md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        {t('pages.contact.form.name') || "Nom complet"}
                        <span className="text-red-500 ml-1">*</span>
                      </label>
                      <Input
                        name="name"
                        value={formData.name}
                        onChange={handleChange}
                        onBlur={handleBlur}
                        placeholder="Votre nom"
                        required
                        className={`h-12 ${touched.name && errors.name ? 'border-red-500 focus:border-red-500 focus:ring-red-500' : ''}`}
                      />
                      {touched.name && errors.name && (
                        <p className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.name}</p>
                      )}
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        {t('pages.contact.form.email') || "Email"}
                        <span className="text-red-500 ml-1">*</span>
                      </label>
                      <Input
                        name="email"
                        type="email"
                        value={formData.email}
                        onChange={handleChange}
                        onBlur={handleBlur}
                        placeholder="votre@email.com"
                        required
                        className={`h-12 ${touched.email && errors.email ? 'border-red-500 focus:border-red-500 focus:ring-red-500' : ''}`}
                      />
                      {touched.email && errors.email && (
                        <p className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.email}</p>
                      )}
                    </div>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      {t('pages.contact.form.category') || "Catégorie"}
                      <span className="text-red-500 ml-1">*</span>
                    </label>
                    <select
                      name="category"
                      value={formData.category}
                      onChange={handleChange}
                      onBlur={handleBlur}
                      required
                      className={`w-full h-12 px-4 rounded-lg border bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-myhigh5-primary focus:border-transparent ${
                        touched.category && errors.category 
                          ? 'border-red-500 focus:border-red-500 focus:ring-red-500' 
                          : 'border-gray-300 dark:border-gray-600'
                      }`}
                    >
                      <option value="">{fl.select_category}</option>
                      <option value="general">{fl.general}</option>
                      <option value="billing">{fl.billing}</option>
                      <option value="account">{fl.account}</option>
                      <option value="technical">{fl.technical}</option>
                      <option value="partnership">{fl.partnership}</option>
                      <option value="other">{fl.other}</option>
                    </select>
                    {touched.category && errors.category && (
                      <p className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.category}</p>
                    )}
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      {t('pages.contact.form.subject') || "Sujet"}
                      <span className="text-red-500 ml-1">*</span>
                    </label>
                    <Input
                      name="subject"
                      value={formData.subject}
                      onChange={handleChange}
                      onBlur={handleBlur}
                      placeholder="Sujet de votre message"
                      required
                      className={`h-12 ${touched.subject && errors.subject ? 'border-red-500 focus:border-red-500 focus:ring-red-500' : ''}`}
                    />
                    {touched.subject && errors.subject && (
                      <p className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.subject}</p>
                    )}
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      {t('pages.contact.form.message') || "Message"}
                      <span className="text-red-500 ml-1">*</span>
                    </label>
                    <textarea
                      name="message"
                      value={formData.message}
                      onChange={handleChange}
                      onBlur={handleBlur}
                      placeholder="Décrivez votre demande en détail..."
                      required
                      rows={5}
                      className={`w-full px-4 py-3 rounded-lg border bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-myhigh5-primary focus:border-transparent resize-none ${
                        touched.message && errors.message 
                          ? 'border-red-500 focus:border-red-500 focus:ring-red-500' 
                          : 'border-gray-300 dark:border-gray-600'
                      }`}
                    />
                    {touched.message && errors.message && (
                      <p className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.message}</p>
                    )}
                  </div>
                  
                  <Button 
                    type="submit"
                    disabled={isSubmitting}
                    className="w-full h-12 bg-myhigh5-primary hover:bg-myhigh5-primary-dark text-white font-bold"
                  >
                    {isSubmitting ? (
                      <>
                        <span className="animate-spin mr-2">⏳</span>
                        {fl.sending}
                      </>
                    ) : (
                      <>
                        <Send className="w-5 h-5 mr-2" />
                        {t('pages.contact.form.submit') || "Envoyer le message"}
                      </>
                    )}
                  </Button>
                </form>
              )}
            </div>

            {/* FAQ Section */}
            <div>
              <h2 className="text-2xl md:text-3xl font-bold text-gray-900 dark:text-white mb-6">
                {t('pages.contact.faq.title') || "Questions Fréquentes"}
              </h2>
              <div className="space-y-4">
                {faqItems.map((item, index) => (
                  <details 
                    key={index}
                    className="group bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden"
                  >
                    <summary className="flex items-center justify-between p-5 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                      <span className="font-semibold text-gray-900 dark:text-white pr-4">
                        {item.question}
                      </span>
                      <span className="text-myhigh5-primary group-open:rotate-180 transition-transform">
                        ▼
                      </span>
                    </summary>
                    <div className="px-5 pb-5 text-gray-600 dark:text-gray-400 whitespace-pre-line">
                      {item.answer}
                    </div>
                  </details>
                ))}
              </div>

              {/* Support Hours */}
              <div className="mt-8 bg-gradient-to-br from-myhigh5-primary/10 to-myhigh5-secondary/10 rounded-2xl p-6 border border-myhigh5-primary/20">
                <div className="flex items-center gap-3 mb-4">
                  <Clock className="w-6 h-6 text-myhigh5-primary" />
                  <h3 className="font-bold text-gray-900 dark:text-white">
                    {t('pages.contact.hours.title') || "Heures de support"}
                  </h3>
                </div>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-600 dark:text-gray-400">{fl.weekdays}</span>
                    <span className="font-semibold text-gray-900 dark:text-white">9h - 18h (EST)</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600 dark:text-gray-400">{fl.saturday}</span>
                    <span className="font-semibold text-gray-900 dark:text-white">10h - 16h (EST)</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600 dark:text-gray-400">{fl.sunday}</span>
                    <span className="font-semibold text-gray-900 dark:text-white">{fl.closed}</span>
                  </div>
                </div>
                <div className="mt-4 pt-4 border-t border-myhigh5-primary/20 flex items-center gap-2">
                  <Globe className="w-4 h-4 text-myhigh5-primary" />
                  <span className="text-sm text-gray-600 dark:text-gray-400">
                    {fl.live_chat}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Support Categories */}
        <section className="py-16 bg-gray-50 dark:bg-gray-800/50">
          <div className="container px-4 md:px-6">
            <div className="text-center mb-10">
              <h2 className="text-2xl md:text-3xl font-bold text-gray-900 dark:text-white mb-4">
                {t('pages.contact.categories.title') || "Comment pouvons-nous vous aider ?"}
              </h2>
            </div>
            <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 max-w-5xl mx-auto">
              {supportCategories.map((category, index) => (
                <div 
                  key={index}
                  className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-200 dark:border-gray-700 hover:shadow-lg transition-all duration-300 hover:-translate-y-1 cursor-pointer group"
                >
                  <category.icon className="w-10 h-10 text-myhigh5-primary mb-4 group-hover:scale-110 transition-transform" />
                  <h3 className="font-bold text-gray-900 dark:text-white mb-2">
                    {category.title}
                  </h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    {category.description}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>
      
      <Footer />
    </div>
  )
}
