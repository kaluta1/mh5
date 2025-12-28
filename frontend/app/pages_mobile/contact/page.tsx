"use client"

import * as React from "react"
import { useState } from "react"
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
  HelpCircle,
  FileText,
  Users,
  Headphones,
  CheckCircle,
  AlertCircle
} from "lucide-react"

export default function ContactMobilePage() {
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
        submit_error: "An error occurred while sending the message. Please try again."
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
        submit_error: "Une erreur est survenue lors de l'envoi du message. Veuillez réessayer."
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
        submit_error: "Ocurrió un error al enviar el mensaje. Por favor intente nuevamente."
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
        submit_error: "Beim Senden der Nachricht ist ein Fehler aufgetreten. Bitte versuchen Sie es erneut."
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

  const validateField = (name: string, value: string): string => {
    switch (name) {
      case 'name':
        if (!value.trim()) return errorMessages.name_required || 'Name is required'
        if (value.trim().length < 2) return errorMessages.name_min || 'Name must be at least 2 characters'
        break
      case 'email':
        if (!value.trim()) return errorMessages.email_required || 'Email is required'
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
        if (!emailRegex.test(value.trim())) return errorMessages.email_invalid || 'Please enter a valid email address'
        break
      case 'subject':
        if (!value.trim()) return errorMessages.subject_required || 'Subject is required'
        if (value.trim().length < 3) return errorMessages.subject_min || 'Subject must be at least 3 characters'
        break
      case 'category':
        if (!value) return errorMessages.category_required || 'Please select a category'
        break
      case 'message':
        if (!value.trim()) return errorMessages.message_required || 'Message is required'
        if (value.trim().length < 10) return errorMessages.message_min || 'Message must be at least 10 characters'
        break
    }
    return ''
  }

  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {}
    Object.keys(formData).forEach((key) => {
      const error = validateField(key, formData[key as keyof typeof formData])
      if (error) newErrors[key] = error
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
    setTouched({ name: true, email: true, subject: true, category: true, message: true })

    if (!validateForm()) return

    setIsSubmitting(true)
    try {
      await apiService.post('/contact', formData)
      setIsSubmitted(true)
      setFormData({ name: "", email: "", subject: "", category: "", message: "" })
      setTouched({})
      setTimeout(() => setIsSubmitted(false), 5000)
    } catch (error) {
      setErrors({ submit: errorMessages.submit_error })
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
    if (touched[name]) {
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
  }

  const titleLabels: Record<string, string> = {
    en: "Contact Us",
    fr: "Contactez-nous",
    es: "Contáctenos",
    de: "Kontaktieren Sie uns"
  }

  const subtitleLabels: Record<string, string> = {
    en: "We're here to help! Send us a message and we'll respond as soon as possible.",
    fr: "Nous sommes là pour vous aider ! Envoyez-nous un message et nous vous répondrons dans les plus brefs délais.",
    es: "¡Estamos aquí para ayudar! Envíanos un mensaje y te responderemos lo antes posible.",
    de: "Wir sind hier um zu helfen! Senden Sie uns eine Nachricht und wir werden so schnell wie möglich antworten."
  }

  const formTitles: Record<string, Record<string, string>> = {
    en: { name: "Full Name", email: "Email Address", subject: "Subject", category: "Category", message: "Your Message", send: "Send Message" },
    fr: { name: "Nom complet", email: "Adresse email", subject: "Sujet", category: "Catégorie", message: "Votre message", send: "Envoyer le message" },
    es: { name: "Nombre completo", email: "Dirección de email", subject: "Asunto", category: "Categoría", message: "Tu mensaje", send: "Enviar mensaje" },
    de: { name: "Vollständiger Name", email: "E-Mail-Adresse", subject: "Betreff", category: "Kategorie", message: "Ihre Nachricht", send: "Nachricht senden" }
  }

  const ft = formTitles[language] || formTitles.en

  return (
    <div className="min-h-screen bg-gradient-to-br from-myhigh5-blue-50 via-white to-myhigh5-cyan-50 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900">
      <main className="py-8">
        {/* Hero Section */}
        <section className="relative py-12 bg-gradient-to-r from-myhigh5-primary to-myhigh5-secondary overflow-hidden">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_50%,rgba(255,255,255,0.15),transparent_50%)]" />
          <div className="container px-4 md:px-6 relative z-10">
            <div className="max-w-3xl mx-auto text-center text-white">
              <Mail className="w-12 h-12 mx-auto mb-4" />
              <h1 className="text-3xl md:text-4xl font-black mb-3">
                {titleLabels[language] || titleLabels.en}
              </h1>
              <p className="text-base opacity-90">
                {subtitleLabels[language] || subtitleLabels.en}
              </p>
            </div>
          </div>
        </section>

        {/* Contact Methods */}
        <section className="container px-4 md:px-6 py-8">
          <div className="max-w-4xl mx-auto grid md:grid-cols-3 gap-4 mb-8">
            {contactMethods.map((method, index) => (
              <a
                key={index}
                href={method.action}
                className="bg-white dark:bg-gray-800 rounded-2xl p-5 shadow-lg border border-gray-200 dark:border-gray-700 hover:shadow-xl transition-all hover:-translate-y-1"
              >
                <div className="flex flex-col items-center text-center">
                  <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary flex items-center justify-center mb-3">
                    <method.icon className="w-6 h-6 text-white" />
                  </div>
                  <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-1">
                    {method.title}
                  </h3>
                  <p className="text-xs text-gray-600 dark:text-gray-400 mb-2">
                    {method.description}
                  </p>
                  <p className="text-sm font-semibold text-myhigh5-primary">
                    {method.value}
                  </p>
                </div>
              </a>
            ))}
          </div>

          {/* Contact Form */}
          <div className="max-w-2xl mx-auto">
            {isSubmitted ? (
              <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-2xl p-6 text-center">
                <CheckCircle className="w-12 h-12 text-green-600 dark:text-green-400 mx-auto mb-3" />
                <h3 className="text-xl font-bold text-green-900 dark:text-green-100 mb-2">
                  {fl.sent_title}
                </h3>
                <p className="text-green-700 dark:text-green-300">
                  {fl.sent_desc}
                </p>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-lg border border-gray-200 dark:border-gray-700">
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
                      {ft.name}
                    </label>
                    <Input
                      name="name"
                      value={formData.name}
                      onChange={handleChange}
                      onBlur={handleBlur}
                      className={errors.name && touched.name ? "border-red-500" : ""}
                    />
                    {errors.name && touched.name && (
                      <p className="text-xs text-red-500 mt-1 flex items-center gap-1">
                        <AlertCircle className="w-3 h-3" />
                        {errors.name}
                      </p>
                    )}
                  </div>

                  <div>
                    <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
                      {ft.email}
                    </label>
                    <Input
                      type="email"
                      name="email"
                      value={formData.email}
                      onChange={handleChange}
                      onBlur={handleBlur}
                      className={errors.email && touched.email ? "border-red-500" : ""}
                    />
                    {errors.email && touched.email && (
                      <p className="text-xs text-red-500 mt-1 flex items-center gap-1">
                        <AlertCircle className="w-3 h-3" />
                        {errors.email}
                      </p>
                    )}
                  </div>

                  <div>
                    <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
                      {ft.category}
                    </label>
                    <select
                      name="category"
                      value={formData.category}
                      onChange={handleChange}
                      onBlur={handleBlur}
                      className={`w-full px-3 py-2 rounded-lg border ${errors.category && touched.category ? "border-red-500" : "border-gray-300 dark:border-gray-600"} bg-white dark:bg-gray-700 text-gray-900 dark:text-white`}
                    >
                      <option value="">{fl.select_category}</option>
                      <option value="general">{fl.general}</option>
                      <option value="billing">{fl.billing}</option>
                      <option value="account">{fl.account}</option>
                      <option value="technical">{fl.technical}</option>
                      <option value="partnership">{fl.partnership}</option>
                      <option value="other">{fl.other}</option>
                    </select>
                    {errors.category && touched.category && (
                      <p className="text-xs text-red-500 mt-1 flex items-center gap-1">
                        <AlertCircle className="w-3 h-3" />
                        {errors.category}
                      </p>
                    )}
                  </div>

                  <div>
                    <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
                      {ft.subject}
                    </label>
                    <Input
                      name="subject"
                      value={formData.subject}
                      onChange={handleChange}
                      onBlur={handleBlur}
                      className={errors.subject && touched.subject ? "border-red-500" : ""}
                    />
                    {errors.subject && touched.subject && (
                      <p className="text-xs text-red-500 mt-1 flex items-center gap-1">
                        <AlertCircle className="w-3 h-3" />
                        {errors.subject}
                      </p>
                    )}
                  </div>

                  <div>
                    <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
                      {ft.message}
                    </label>
                    <textarea
                      name="message"
                      value={formData.message}
                      onChange={handleChange}
                      onBlur={handleBlur}
                      rows={5}
                      className={`w-full px-3 py-2 rounded-lg border ${errors.message && touched.message ? "border-red-500" : "border-gray-300 dark:border-gray-600"} bg-white dark:bg-gray-700 text-gray-900 dark:text-white resize-none`}
                    />
                    {errors.message && touched.message && (
                      <p className="text-xs text-red-500 mt-1 flex items-center gap-1">
                        <AlertCircle className="w-3 h-3" />
                        {errors.message}
                      </p>
                    )}
                  </div>

                  {errors.submit && (
                    <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3 text-sm text-red-700 dark:text-red-300">
                      {errors.submit}
                    </div>
                  )}

                  <Button
                    type="submit"
                    disabled={isSubmitting}
                    className="w-full bg-gradient-to-r from-myhigh5-primary to-myhigh5-secondary text-white font-semibold py-3"
                  >
                    {isSubmitting ? (
                      <>{fl.sending}</>
                    ) : (
                      <>
                        <Send className="w-4 h-4 mr-2" />
                        {ft.send}
                      </>
                    )}
                  </Button>
                </div>
              </form>
            )}
          </div>
        </section>

        {/* Support Categories */}
        <section className="py-8 bg-gray-50 dark:bg-gray-800/50">
          <div className="container px-4 md:px-6">
            <div className="max-w-4xl mx-auto">
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-6 text-center">
                {language === 'fr' ? 'Comment pouvons-nous vous aider ?' : language === 'es' ? '¿Cómo podemos ayudarte?' : language === 'de' ? 'Wie können wir Ihnen helfen?' : 'How can we help you?'}
              </h2>
              <div className="grid md:grid-cols-2 gap-4">
                {supportCategories.map((category, index) => (
                  <div
                    key={index}
                    className="bg-white dark:bg-gray-800 rounded-2xl p-5 shadow-lg border border-gray-200 dark:border-gray-700"
                  >
                    <div className="flex items-start gap-3">
                      <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary flex items-center justify-center flex-shrink-0">
                        <category.icon className="w-5 h-5 text-white" />
                      </div>
                      <div className="flex-1">
                        <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-1">
                          {category.title}
                        </h3>
                        <p className="text-sm text-gray-600 dark:text-gray-400">
                          {category.description}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  )
}
