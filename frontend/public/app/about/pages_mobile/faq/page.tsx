"use client"

import * as React from "react"
import { useState } from "react"
import { 
  HelpCircle, 
  ChevronDown, 
  Trophy, 
  DollarSign, 
  Globe, 
  Vote, 
  Grid3x3,
  Wallet,
  Users,
  Store,
  TrendingUp,
  Award,
  Sparkles
} from "lucide-react"
import { useLanguage } from "@/contexts/language-context"

export default function FAQMobilePage() {
  const { t } = useLanguage()
  const [openIndex, setOpenIndex] = useState<number | null>(null)

  const faqs = [
    {
      question: t('landing.faq.question_1') || 'Comment puis-je gagner de l\'argent sur MyHigh5 ?',
      answer: t('landing.faq.answer_1') || 'Vous pouvez gagner de l\'argent de plusieurs façons : en participant aux concours et en remportant des prix, en rejoignant le programme d\'affiliation pour gagner des commissions sur les membres que vous référez, et en devenant membre fondateur pour participer aux pools de revenus et de profits.'
    },
    {
      question: t('landing.faq.question_2') || 'Comment fonctionne le programme d\'affiliation ?',
      answer: t('landing.faq.answer_2') || 'Le programme d\'affiliation MyHigh5 fonctionne sur 10 niveaux. Vous gagnez 20% de commission sur les activités des membres que vous référez directement (niveau 1), et 2% sur les niveaux 2 à 10. Vous pouvez gagner des commissions sur les paiements KYC, les adhésions, les achats en boutique, et plus encore.'
    },
    {
      question: t('landing.faq.question_3') || 'Qu\'est-ce que le statut de Membre Fondateur ?',
      answer: t('landing.faq.answer_3') || 'Le statut de Membre Fondateur est une opportunité limitée qui nécessite un paiement unique de 100$ et la vérification de votre compte. Les membres fondateurs participent à des pools de commissions mensuelles (10% des revenus nets) et à un pool de profits annuels (20% des profits après impôts).'
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

  const features = [
    {
      icon: Trophy,
      title: t('features.items.multi_level.title') || 'Concours Multi-Niveaux',
      description: t('features.items.multi_level.description') || 'Participez à des compétitions locales, nationales et internationales avec un système de progression unique.'
    },
    {
      icon: DollarSign,
      title: t('features.items.financial_rewards.title') || 'Récompenses Financières',
      description: t('features.items.financial_rewards.description') || 'Recevez des commissions d\'affiliation sur les revenus générés par votre réseau de parrainage, jusqu\'à 10 générations de profondeur.'
    },
    {
      icon: Globe,
      title: t('features.items.international_reach.title') || 'Portée Internationale',
      description: t('features.items.international_reach.description') || 'Vos talents peuvent être découverts et appréciés par un public mondial diversifié.'
    },
    {
      icon: Vote,
      title: t('features.items.innovative_voting.title') || 'Vote Innovant',
      description: t('features.items.innovative_voting.description') || 'Système de vote équitable et transparent avec classements en temps réel.'
    },
    {
      icon: Grid3x3,
      title: t('features.items.varied_categories.title') || 'Catégories Variées',
      description: t('features.items.varied_categories.description') || 'Trouvez les catégories de concours qui vous passionnent pour participer. Recommandez toute catégorie manquante que vous aimeriez voir ajoutée.'
    }
  ]

  const waysToEarn = [
    {
      icon: Wallet,
      title: t('landing.ways_to_earn.kyc_payments.title') || 'Paiements KYC',
      description: t('landing.ways_to_earn.kyc_payments.description') || 'Gagnez des commissions lorsque les membres de votre réseau complètent leur vérification KYC',
      commission: t('landing.ways_to_earn.kyc_payments.commission') || '20% au niveau 1, 2% aux niveaux 2-10'
    },
    {
      icon: Award,
      title: t('landing.ways_to_earn.founding_membership.title') || 'Adhésion Fondateur',
      description: t('landing.ways_to_earn.founding_membership.description') || 'Gagnez des commissions lorsque les membres de votre réseau de parrainage rejoignent le Club des Membres Fondateurs ou paient les frais d\'adhésion annuels.',
      commission: t('landing.ways_to_earn.founding_membership.commission') || '20% au niveau 1, 2% aux niveaux 2-10'
    },
    {
      icon: Users,
      title: t('landing.ways_to_earn.club_memberships.title') || 'Adhésions aux Clubs',
      description: t('landing.ways_to_earn.club_memberships.description') || 'Gagnez des commissions sur les frais d\'adhésion aux clubs payants.',
      commission: t('landing.ways_to_earn.club_memberships.commission') || '20% au niveau 1, 2% aux niveaux 2-10'
    },
    {
      icon: Store,
      title: t('landing.ways_to_earn.shop_purchases.title') || 'Achats en Boutique',
      description: t('landing.ways_to_earn.shop_purchases.description') || 'Gagnez des commissions sur les achats de contenu numérique dans la boutique MyHigh5.',
      commission: t('landing.ways_to_earn.shop_purchases.commission') || '20% au niveau 1, 2% aux niveaux 2-10'
    },
    {
      icon: TrendingUp,
      title: t('landing.ways_to_earn.ad_revenue.title') || 'Partage des Revenus Publicitaires',
      description: t('landing.ways_to_earn.ad_revenue.description') || 'Les participants aux concours gagnent 40% des revenus publicitaires générés sur leurs pages de concours.',
      commission: t('landing.ways_to_earn.ad_revenue.commission') || '10% au niveau 1, 1% aux niveaux 2-10'
    },
    {
      icon: Sparkles,
      title: t('landing.ways_to_earn.ad_campaigns.title') || 'Page Sponsors du Site',
      description: t('landing.ways_to_earn.ad_campaigns.description') || 'Les sponsors de niveau 1 gagnent une commission de 10%, et les niveaux 2 à 10 gagnent 1% chacun.',
      commission: t('landing.ways_to_earn.ad_campaigns.commission') || '10% au niveau 1, 1% aux niveaux 2-10'
    }
  ]

  const toggleFAQ = (index: number) => {
    setOpenIndex(openIndex === index ? null : index)
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-myhigh5-blue-50 via-white to-myhigh5-cyan-50 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900">
      <main className="py-8">
        <section className="relative py-12 bg-gradient-to-r from-myhigh5-primary to-myhigh5-secondary overflow-hidden">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_50%,rgba(255,255,255,0.15),transparent_50%)]" />
          <div className="container px-4 md:px-6 relative z-10">
            <div className="max-w-3xl mx-auto text-center text-white">
              <HelpCircle className="w-12 h-12 mx-auto mb-4" />
              <h1 className="text-3xl md:text-4xl font-black mb-3">
                {t('landing.faq.title') || 'Questions fréquentes'}
              </h1>
              <p className="text-base opacity-90">
                {t('landing.faq.subtitle') || 'Trouvez les réponses aux questions les plus courantes sur MyHigh5'}
              </p>
            </div>
          </div>
        </section>

        {/* Exceptional Features Section */}
        <section className="container px-4 md:px-6 py-8">
          <div className="max-w-4xl mx-auto">
            <div className="text-center mb-8">
              <h2 className="text-2xl md:text-3xl font-bold text-gray-900 dark:text-white mb-3">
                {t('features.title') || 'Fonctionnalités Exceptionnelles'}
              </h2>
              <p className="text-base text-gray-600 dark:text-gray-400">
                {t('features.subtitle') || 'Découvrez tout ce qui fait de MyHigh5 une plateforme de concours en ligne mondiale unique et passionnante.'}
              </p>
            </div>
            <div className="grid md:grid-cols-2 gap-4">
              {features.map((feature, index) => (
                <div
                  key={index}
                  className="bg-white dark:bg-gray-800 rounded-2xl p-5 shadow-lg border border-gray-200 dark:border-gray-700 hover:shadow-xl transition-shadow"
                >
                  <div className="flex items-start gap-3">
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary flex items-center justify-center flex-shrink-0">
                      <feature.icon className="w-5 h-5 text-white" />
                    </div>
                    <div className="flex-1">
                      <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-2">
                        {feature.title}
                      </h3>
                      <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
                        {feature.description}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Different Ways to Earn Section */}
        <section className="py-8 bg-gray-50 dark:bg-gray-800/50">
          <div className="container px-4 md:px-6">
            <div className="max-w-4xl mx-auto">
              <div className="text-center mb-8">
                <div className="inline-flex items-center gap-2 bg-myhigh5-primary/10 text-myhigh5-primary rounded-full px-4 py-2 text-sm font-semibold mb-4">
                  <DollarSign className="w-4 h-4" />
                  <span>{t('landing.ways_to_earn.badge') || 'Gagner de l\'Argent'}</span>
                </div>
                <h2 className="text-2xl md:text-3xl font-bold text-gray-900 dark:text-white mb-3">
                  {t('landing.ways_to_earn.title') || 'Différentes Façons de Gagner'}
                </h2>
                <p className="text-base text-gray-600 dark:text-gray-400">
                  {t('landing.ways_to_earn.subtitle') || 'Rejoignez notre programme d\'affiliation et gagnez des commissions sur plusieurs flux de revenus'}
                </p>
              </div>
              <div className="grid md:grid-cols-2 gap-4">
                {waysToEarn.map((way, index) => (
                  <div
                    key={index}
                    className="bg-white dark:bg-gray-800 rounded-2xl p-5 shadow-lg border border-gray-200 dark:border-gray-700 hover:shadow-xl transition-shadow"
                  >
                    <div className="flex items-start gap-3">
                      <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-green-500 to-emerald-600 flex items-center justify-center flex-shrink-0">
                        <way.icon className="w-5 h-5 text-white" />
                      </div>
                      <div className="flex-1">
                        <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-2">
                          {way.title}
                        </h3>
                        <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed mb-2">
                          {way.description}
                        </p>
                        <div className="inline-flex items-center gap-1 bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 px-3 py-1 rounded-full text-xs font-semibold">
                          <DollarSign className="w-3 h-3" />
                          {way.commission}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* FAQ Section */}
        <section className="container px-4 md:px-6 py-8">
          <div className="max-w-4xl mx-auto space-y-3">
            {faqs.map((faq, index) => (
              <div
                key={index}
                className="bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm rounded-2xl border border-gray-200/50 dark:border-gray-700/50 shadow-lg overflow-hidden"
              >
                <button
                  onClick={() => toggleFAQ(index)}
                  className="w-full flex items-center justify-between p-5 md:p-6 text-left hover:bg-gray-50/50 dark:hover:bg-gray-700/50 transition-colors"
                >
                  <span className="text-base md:text-lg font-bold text-gray-900 dark:text-white pr-3 flex-1">
                    {faq.question}
                  </span>
                  <ChevronDown
                    className={`w-5 h-5 text-myhigh5-primary flex-shrink-0 transition-transform duration-300 ${
                      openIndex === index ? 'rotate-180' : ''
                    }`}
                  />
                </button>
                {openIndex === index && (
                  <div className="px-5 md:px-6 pb-5 md:pb-6 text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
                    {faq.answer}
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  )
}
