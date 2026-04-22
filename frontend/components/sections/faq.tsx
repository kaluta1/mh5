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
      question: t('landing.faq.question_1'),
      answer: t('landing.faq.answer_1')
    },
    {
      question: t('landing.faq.question_2'),
      answer: t('landing.faq.answer_2')
    },
    {
      question: t('landing.faq.question_3'),
      answer: t('landing.faq.answer_3')
    },
    {
      question: t('landing.faq.question_4'),
      answer: t('landing.faq.answer_4')
    },
    {
      question: t('landing.faq.question_5'),
      answer: t('landing.faq.answer_5')
    },
    {
      question: t('landing.faq.question_6'),
      answer: t('landing.faq.answer_6')
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
            <span>{t('landing.faq.badge')}</span>
          </div>
          <h2 className="text-4xl sm:text-5xl md:text-6xl font-black tracking-tight mb-6 bg-gradient-to-r from-gray-900 to-gray-700 dark:from-white dark:to-gray-300 bg-clip-text text-transparent">
            {t('landing.faq.title')}
          </h2>
          <p className="text-lg md:text-xl text-gray-600 dark:text-gray-400 leading-relaxed">
            {t('landing.faq.subtitle')}
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

