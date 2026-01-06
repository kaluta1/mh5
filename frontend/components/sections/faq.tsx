"use client"

import * as React from "react"
import { useState } from "react"
import { HelpCircle, ChevronDown } from "lucide-react"
import { useLanguage } from "@/contexts/language-context"

export function FAQ() {
  const { t } = useLanguage()
  const [openIndex, setOpenIndex] = useState<number | null>(null)

  const faqs = [
    {
      question: t('landing.faq.question_1') || 'Comment puis-je gagner de l\'argent sur MyHigh5 ?',
      answer: t('landing.faq.answer_1') || 'Vous pouvez gagner de l\'argent de plusieurs façons : en participant aux concours et en remportant des prix, en rejoignant le programme d\'affiliation pour gagner des commissions sur les membres que vous référez, et en devenant membre fondateur pour participer aux pools de revenus et de profits.'
    },
    {
      question: t('landing.faq.question_2') || 'Comment fonctionne le programme d\'affiliation ?',
      answer: t('landing.faq.answer_2') || 'Le programme d\'affiliation MyHigh5 fonctionne sur 10 niveaux. Vous gagnez 10% de commission sur les activités des membres que vous référez directement (niveau 1), et 1% sur les niveaux 2 à 10. Vous pouvez gagner des commissions sur les paiements KYC, les adhésions, les achats en boutique, et plus encore.'
    },
    {
      question: t('landing.faq.question_3') || 'Qu\'est-ce que le statut de Membre Fondateur ?',
      answer: t('landing.faq.answer_3') || 'Le statut de Membre Fondateur est une opportunité limitée qui nécessite un paiement unique de 100$ et la vérification de votre compte. Les membres fondateurs participent à des pools de commissions mensuelles (5% des revenus nets) et à un pool de profits annuels (10% des profits après impôts).'
    },
    {
      question: t('landing.faq.question_4') || 'Comment puis-je participer aux concours ?',
      answer: t('landing.faq.answer_4') || 'Pour participer aux concours, vous devez créer un compte gratuit, compléter votre profil, et soumettre votre candidature avec des photos ou vidéos selon les exigences du concours. Certains concours peuvent nécessiter une vérification KYC.'
    },
    {
      question: t('landing.faq.question_5') || 'Les concours sont-ils gratuits ?',
      answer: t('landing.faq.answer_5') || 'Oui, la participation aux concours est gratuite. Cependant, certains concours peuvent nécessiter une vérification KYC qui peut avoir un coût. Les membres fondateurs ont accès à des avantages exclusifs et à des opportunités de revenus supplémentaires.'
    },
    {
      question: t('landing.faq.question_6') || 'Comment puis-je retirer mes gains ?',
      answer: t('landing.faq.answer_6') || 'Vous pouvez retirer vos gains via votre portefeuille dans le tableau de bord. Les paiements sont traités mensuellement avec un seuil minimum de 50$ CAD. Les méthodes de paiement incluent le virement bancaire (pour les affiliés canadiens), PayPal, ou la cryptomonnaie.'
    }
  ]

  const toggleFAQ = (index: number) => {
    setOpenIndex(openIndex === index ? null : index)
  }

  return (
    <section className="py-20 md:py-24 lg:py-32 relative">
      {/* Background decoration */}
      <div className="absolute inset-0 bg-gradient-to-b from-gray-50/50 via-transparent to-gray-50/50 dark:from-gray-900/50 dark:via-transparent dark:to-gray-900/50" />
      
      <div className="container px-4 md:px-6 relative z-10">
        {/* Section Header */}
        <div className="text-center max-w-3xl mx-auto mb-16 md:mb-20">
          <div className="inline-flex items-center gap-2 bg-myhigh5-primary/10 text-myhigh5-primary rounded-full px-4 py-2 text-sm font-semibold mb-6">
            <HelpCircle className="w-4 h-4" />
            <span>{t('landing.faq.badge') || 'Questions fréquentes'}</span>
          </div>
          <h2 className="text-4xl sm:text-5xl md:text-6xl font-black tracking-tight mb-6 bg-gradient-to-r from-gray-900 to-gray-700 dark:from-white dark:to-gray-300 bg-clip-text text-transparent">
            {t('landing.faq.title') || 'Questions fréquentes'}
          </h2>
          <p className="text-lg md:text-xl text-gray-600 dark:text-gray-400 leading-relaxed">
            {t('landing.faq.subtitle') || 'Trouvez les réponses aux questions les plus courantes sur MyHigh5'}
          </p>
        </div>

        {/* FAQ Items */}
        <div className="max-w-4xl mx-auto space-y-4">
          {faqs.map((faq, index) => (
            <div
              key={index}
              className="group bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm rounded-2xl border border-gray-200/50 dark:border-gray-700/50 shadow-lg hover:shadow-xl transition-all duration-300 overflow-hidden"
            >
              <button
                onClick={() => toggleFAQ(index)}
                className="w-full flex items-center justify-between p-6 md:p-8 text-left hover:bg-gray-50/50 dark:hover:bg-gray-700/50 transition-colors"
              >
                <span className="text-lg md:text-xl font-bold text-gray-900 dark:text-white pr-4 flex-1">
                  {faq.question}
                </span>
                <ChevronDown
                  className={`w-6 h-6 text-myhigh5-primary flex-shrink-0 transition-transform duration-300 ${
                    openIndex === index ? 'rotate-180' : ''
                  }`}
                />
              </button>
              {openIndex === index && (
                <div className="px-6 md:px-8 pb-6 md:pb-8 text-gray-600 dark:text-gray-400 leading-relaxed animate-in slide-in-from-top-2 duration-300 whitespace-pre-line">
                  {faq.answer}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

