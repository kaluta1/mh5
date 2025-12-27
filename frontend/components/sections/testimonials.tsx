"use client"

import * as React from "react"
import { Card, CardContent } from "@/components/ui/card"
import { UserAvatar } from "@/components/user/user-avatar"
import { Star, Quote } from "lucide-react"
import { useLanguage } from "@/contexts/language-context"

const testimonialKeys = ['sarah_m', 'carlos_r', 'emma_l']

export function Testimonials() {
  const { t } = useLanguage()
  
  return (
    <section className="py-20 md:py-24 lg:py-32 relative">
      {/* Background decoration */}
      <div className="absolute inset-0 bg-gradient-to-b from-gray-50/50 via-transparent to-gray-50/50 dark:from-gray-900/50 dark:via-transparent dark:to-gray-900/50" />
      
      <div className="container px-4 md:px-6 relative z-10">
        {/* Section Header */}
        <div className="text-center max-w-3xl mx-auto mb-16 md:mb-20">
          <div className="inline-flex items-center gap-2 bg-myhigh5-primary/10 text-myhigh5-primary rounded-full px-4 py-2 text-sm font-semibold mb-6">
            <Star className="w-4 h-4 fill-myhigh5-primary" />
            <span>Témoignages</span>
          </div>
          <h2 className="text-4xl sm:text-5xl md:text-6xl font-black tracking-tight mb-6 bg-gradient-to-r from-gray-900 to-gray-700 dark:from-white dark:to-gray-300 bg-clip-text text-transparent">
              {t('testimonials.title')}
            </h2>
          <p className="text-lg md:text-xl text-gray-600 dark:text-gray-400 leading-relaxed">
              {t('testimonials.subtitle')}
            </p>
        </div>

        {/* Testimonials Grid */}
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 lg:gap-8 mb-16">
          {testimonialKeys.map((key, index) => {
            const rating = t(`testimonials.items.${key}.rating`)
            const numRating = typeof rating === 'string' ? parseInt(rating) || 5 : rating || 5
            
            return (
            <Card 
              key={index} 
                className="group relative overflow-hidden border-0 bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm shadow-lg hover:shadow-2xl transition-all duration-500 hover:-translate-y-2 rounded-2xl"
              >
                {/* Quote icon decoration */}
                <div className="absolute top-6 right-6 w-16 h-16 bg-gradient-to-br from-myhigh5-primary/10 to-myhigh5-secondary/10 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-500">
                  <Quote className="w-8 h-8 text-myhigh5-primary/30" />
                </div>
                
                <CardContent className="p-6 md:p-8 relative z-10">
                {/* Rating */}
                  <div className="flex items-center gap-1 mb-6">
                    {[...Array(numRating)].map((_, i) => (
                      <Star key={i} className="h-5 w-5 fill-amber-400 text-amber-400" />
                  ))}
                </div>

                {/* Content */}
                  <blockquote className="text-base leading-relaxed mb-8 text-gray-700 dark:text-gray-300 font-medium relative">
                    <Quote className="absolute -top-2 -left-2 w-8 h-8 text-myhigh5-primary/20" />
                    <span className="relative z-10">"{t(`testimonials.items.${key}.text`)}"</span>
                </blockquote>

                {/* Author */}
                  <div className="flex items-center gap-4 pt-6 border-t border-gray-200 dark:border-gray-700">
                    <div className="w-14 h-14 rounded-full flex items-center justify-center bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary text-white font-bold text-lg shadow-lg">
                    {t(`testimonials.items.${key}.name`).split(' ').map(n => n[0]).join('')}
                  </div>
                  <div className="flex-1 min-w-0">
                      <p className="text-base font-bold text-gray-900 dark:text-white">
                      {t(`testimonials.items.${key}.name`)}
                    </p>
                      <p className="text-sm text-gray-500 dark:text-gray-400 flex items-center gap-1">
                        <span>{t(`testimonials.items.${key}.location`)}</span>
                        {t(`testimonials.items.${key}.role`) && (
                          <>
                            <span>•</span>
                            <span>{t(`testimonials.items.${key}.role`)}</span>
                          </>
                        )}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
            )
          })}
        </div>

        {/* CTA Section */}
        <div className="text-center">
          <div className="inline-flex flex-col items-center gap-4 bg-gradient-to-br from-white/80 to-gray-50/80 dark:from-gray-800/80 dark:to-gray-900/80 backdrop-blur-sm rounded-2xl p-8 md:p-10 border border-gray-200/50 dark:border-gray-700/50 shadow-xl">
            <p className="text-lg font-semibold text-gray-700 dark:text-gray-300">
              {t('testimonials.cta')}
            </p>
            <div className="flex items-center justify-center gap-4">
              <div className="flex -space-x-3">
                {testimonialKeys.slice(0, 3).map((key, index) => (
                  <div
                    key={index}
                    className="w-12 h-12 rounded-full flex items-center justify-center text-white text-sm font-bold border-4 border-white dark:border-gray-800 bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary shadow-lg hover:scale-110 transition-transform"
                  >
                    {t(`testimonials.items.${key}.name`).split(' ').map(n => n[0]).join('')}
                  </div>
                ))}
              </div>
              <span className="text-base font-bold text-myhigh5-primary dark:text-myhigh5-blue-400">
                {t('testimonials.users')}
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
