"use client"

import * as React from "react"
import { useState } from "react"
import { Header } from "@/components/layout/header"
import { Footer } from "@/components/sections/footer"
import { useLanguage } from "@/contexts/language-context"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { 
  Mail, 
  Phone, 
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
      { title: "Email", description: "Send us an email", value: "support@myhigh5.com" },
      { title: "Phone", description: "Call us", value: "+1 (888) 555-0123" },
      { title: "Live Chat", description: "Instant response", value: "Available 24/7" },
      { title: "Headquarters", description: "Our address", value: "Montreal, QC, Canada" }
    ],
    fr: [
      { title: "Email", description: "Envoyez-nous un email", value: "support@myhigh5.com" },
      { title: "Téléphone", description: "Appelez-nous", value: "+1 (888) 555-0123" },
      { title: "Chat en direct", description: "Réponse instantanée", value: "Disponible 24/7" },
      { title: "Siège social", description: "Notre adresse", value: "Montréal, QC, Canada" }
    ],
    es: [
      { title: "Email", description: "Envíanos un email", value: "support@myhigh5.com" },
      { title: "Teléfono", description: "Llámanos", value: "+1 (888) 555-0123" },
      { title: "Chat en vivo", description: "Respuesta instantánea", value: "Disponible 24/7" },
      { title: "Sede central", description: "Nuestra dirección", value: "Montreal, QC, Canadá" }
    ],
    de: [
      { title: "E-Mail", description: "Senden Sie uns eine E-Mail", value: "support@myhigh5.com" },
      { title: "Telefon", description: "Rufen Sie uns an", value: "+1 (888) 555-0123" },
      { title: "Live-Chat", description: "Sofortige Antwort", value: "24/7 verfügbar" },
      { title: "Hauptsitz", description: "Unsere Adresse", value: "Montreal, QC, Kanada" }
    ]
  }

  const contactMethods = [
    { icon: Mail, action: "mailto:support@myhigh5.com", ...contactMethodsData[language]?.[0] || contactMethodsData.en[0] },
    { icon: Phone, action: "tel:+18885550123", ...contactMethodsData[language]?.[1] || contactMethodsData.en[1] },
    { icon: MessageSquare, action: "#chat", ...contactMethodsData[language]?.[2] || contactMethodsData.en[2] },
    { icon: MapPin, action: "#", ...contactMethodsData[language]?.[3] || contactMethodsData.en[3] }
  ]

  const faqData: Record<string, { question: string; answer: string }[]> = {
    en: [
      { question: "How to participate in a contest?", answer: "Create a free account, complete your profile and click 'Participate' on the contest of your choice." },
      { question: "How does the MyHigh5 voting system work?", answer: "Select up to 5 favorites and rank them by drag-and-drop. 1st gets 5 points, 2nd 4 points, etc." },
      { question: "How to create a Fan Club?", answer: "After identity verification, go to your dashboard and click 'Create a Club'." },
      { question: "How does the affiliate program work?", answer: "Share your unique link. Earn 20% on level 1 and 2% on levels 2 to 10 of referrals." }
    ],
    fr: [
      { question: "Comment participer à un concours ?", answer: "Créez un compte gratuit, complétez votre profil et cliquez sur 'Participer' sur le concours de votre choix." },
      { question: "Comment fonctionne le système de vote MyHigh5 ?", answer: "Sélectionnez jusqu'à 5 favoris et classez-les par glisser-déposer. Le 1er reçoit 5 points, le 2ème 4 points, etc." },
      { question: "Comment créer un Fan Club ?", answer: "Après vérification de votre identité, accédez à votre tableau de bord et cliquez sur 'Créer un Club'." },
      { question: "Comment fonctionne le programme d'affiliation ?", answer: "Partagez votre lien unique. Gagnez 20% sur le niveau 1 et 2% sur les niveaux 2 à 10 des parrainages." }
    ],
    es: [
      { question: "¿Cómo participar en un concurso?", answer: "Crea una cuenta gratis, completa tu perfil y haz clic en 'Participar' en el concurso de tu elección." },
      { question: "¿Cómo funciona el sistema de votación MyHigh5?", answer: "Selecciona hasta 5 favoritos y ordénalos arrastrando y soltando. El 1º recibe 5 puntos, el 2º 4 puntos, etc." },
      { question: "¿Cómo crear un Fan Club?", answer: "Después de verificar tu identidad, ve a tu panel y haz clic en 'Crear un Club'." },
      { question: "¿Cómo funciona el programa de afiliados?", answer: "Comparte tu enlace único. Gana 20% en el nivel 1 y 2% en los niveles 2 a 10 de referidos." }
    ],
    de: [
      { question: "Wie nehme ich an einem Wettbewerb teil?", answer: "Erstellen Sie ein kostenloses Konto, vervollständigen Sie Ihr Profil und klicken Sie auf 'Teilnehmen' beim Wettbewerb Ihrer Wahl." },
      { question: "Wie funktioniert das MyHigh5-Abstimmungssystem?", answer: "Wählen Sie bis zu 5 Favoriten aus und ordnen Sie sie per Drag-and-Drop. Der 1. erhält 5 Punkte, der 2. 4 Punkte, usw." },
      { question: "Wie erstelle ich einen Fan Club?", answer: "Nach der Identitätsüberprüfung gehen Sie zu Ihrem Dashboard und klicken Sie auf 'Club erstellen'." },
      { question: "Wie funktioniert das Partnerprogramm?", answer: "Teilen Sie Ihren einzigartigen Link. Verdienen Sie 20% auf Stufe 1 und 2% auf den Stufen 2 bis 10 der Empfehlungen." }
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

  const formLabels: Record<string, Record<string, string>> = {
    en: { select_category: "Select a category", general: "General help", billing: "Billing", account: "Account", technical: "Technical support", partnership: "Partnership", other: "Other", sending: "Sending...", sent_title: "Message sent!", sent_desc: "We will respond as soon as possible.", weekdays: "Monday - Friday", saturday: "Saturday", sunday: "Sunday", closed: "Closed", live_chat: "Live chat available 24/7" },
    fr: { select_category: "Sélectionnez une catégorie", general: "Aide générale", billing: "Facturation", account: "Compte", technical: "Support technique", partnership: "Partenariat", other: "Autre", sending: "Envoi en cours...", sent_title: "Message envoyé !", sent_desc: "Nous vous répondrons dans les plus brefs délais.", weekdays: "Lundi - Vendredi", saturday: "Samedi", sunday: "Dimanche", closed: "Fermé", live_chat: "Chat en direct disponible 24/7" },
    es: { select_category: "Selecciona una categoría", general: "Ayuda general", billing: "Facturación", account: "Cuenta", technical: "Soporte técnico", partnership: "Asociación", other: "Otro", sending: "Enviando...", sent_title: "¡Mensaje enviado!", sent_desc: "Le responderemos lo antes posible.", weekdays: "Lunes - Viernes", saturday: "Sábado", sunday: "Domingo", closed: "Cerrado", live_chat: "Chat en vivo disponible 24/7" },
    de: { select_category: "Kategorie auswählen", general: "Allgemeine Hilfe", billing: "Abrechnung", account: "Konto", technical: "Technischer Support", partnership: "Partnerschaft", other: "Andere", sending: "Wird gesendet...", sent_title: "Nachricht gesendet!", sent_desc: "Wir werden so schnell wie möglich antworten.", weekdays: "Montag - Freitag", saturday: "Samstag", sunday: "Sonntag", closed: "Geschlossen", live_chat: "Live-Chat 24/7 verfügbar" }
  }
  const fl = formLabels[language] || formLabels.en
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    subject: "",
    category: "",
    message: ""
  })
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isSubmitted, setIsSubmitted] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSubmitting(true)
    
    // Simuler l'envoi
    await new Promise(resolve => setTimeout(resolve, 1500))
    
    setIsSubmitting(false)
    setIsSubmitted(true)
    setFormData({ name: "", email: "", subject: "", category: "", message: "" })
    
    // Reset success message après 5 secondes
    setTimeout(() => setIsSubmitted(false), 5000)
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    setFormData(prev => ({
      ...prev,
      [e.target.name]: e.target.value
    }))
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-myfav-blue-50 via-white to-myfav-cyan-50 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900">
      <Header />
      
      <main className="pt-24 pb-16">
        {/* Hero Section */}
        <section className="relative py-16 bg-gradient-to-r from-myfav-primary to-myfav-secondary overflow-hidden">
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
                <method.icon className="w-10 h-10 text-myfav-primary mb-4 group-hover:scale-110 transition-transform" />
                <h3 className="font-bold text-gray-900 dark:text-white mb-1">
                  {method.title}
                </h3>
                <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">
                  {method.description}
                </p>
                <p className="text-myfav-primary font-semibold">
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
                  <div className="grid md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        {t('pages.contact.form.name') || "Nom complet"}
                      </label>
                      <Input
                        name="name"
                        value={formData.name}
                        onChange={handleChange}
                        placeholder="Votre nom"
                        required
                        className="h-12"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        {t('pages.contact.form.email') || "Email"}
                      </label>
                      <Input
                        name="email"
                        type="email"
                        value={formData.email}
                        onChange={handleChange}
                        placeholder="votre@email.com"
                        required
                        className="h-12"
                      />
                    </div>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      {t('pages.contact.form.category') || "Catégorie"}
                    </label>
                    <select
                      name="category"
                      value={formData.category}
                      onChange={handleChange}
                      required
                      className="w-full h-12 px-4 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-myfav-primary focus:border-transparent"
                    >
                      <option value="">{fl.select_category}</option>
                      <option value="general">{fl.general}</option>
                      <option value="billing">{fl.billing}</option>
                      <option value="account">{fl.account}</option>
                      <option value="technical">{fl.technical}</option>
                      <option value="partnership">{fl.partnership}</option>
                      <option value="other">{fl.other}</option>
                    </select>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      {t('pages.contact.form.subject') || "Sujet"}
                    </label>
                    <Input
                      name="subject"
                      value={formData.subject}
                      onChange={handleChange}
                      placeholder="Sujet de votre message"
                      required
                      className="h-12"
                    />
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      {t('pages.contact.form.message') || "Message"}
                    </label>
                    <textarea
                      name="message"
                      value={formData.message}
                      onChange={handleChange}
                      placeholder="Décrivez votre demande en détail..."
                      required
                      rows={5}
                      className="w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-myfav-primary focus:border-transparent resize-none"
                    />
                  </div>
                  
                  <Button 
                    type="submit"
                    disabled={isSubmitting}
                    className="w-full h-12 bg-myfav-primary hover:bg-myfav-primary-dark text-white font-bold"
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
                      <span className="text-myfav-primary group-open:rotate-180 transition-transform">
                        ▼
                      </span>
                    </summary>
                    <div className="px-5 pb-5 text-gray-600 dark:text-gray-400">
                      {item.answer}
                    </div>
                  </details>
                ))}
              </div>

              {/* Support Hours */}
              <div className="mt-8 bg-gradient-to-br from-myfav-primary/10 to-myfav-secondary/10 rounded-2xl p-6 border border-myfav-primary/20">
                <div className="flex items-center gap-3 mb-4">
                  <Clock className="w-6 h-6 text-myfav-primary" />
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
                <div className="mt-4 pt-4 border-t border-myfav-primary/20 flex items-center gap-2">
                  <Globe className="w-4 h-4 text-myfav-primary" />
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
                  <category.icon className="w-10 h-10 text-myfav-primary mb-4 group-hover:scale-110 transition-transform" />
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
