"use client"

import * as React from "react"
import { Card, CardContent } from "@/components/ui/card"
import { UserAvatar } from "@/components/user/user-avatar"
import { Star } from "lucide-react"
import { useLanguage } from "@/contexts/language-context"

const testimonialKeys = ['sarah_m', 'carlos_r', 'emma_l']

export function Testimonials() {
  const { t } = useLanguage()
  
  return (
    <section className="">
      <div>
        <div className="flex flex-col items-start justify-start space-y-4 text-start">
          <div className="space-y-2">
            <h2 className="text-3xl font-bold tracking-tighter sm:text-4xl md:text-5xl dsm-title">
              {t('testimonials.title')}
            </h2>
            <p className="mx-auto dsm-subtitle md:text-xl/relaxed lg:text-base/relaxed xl:text-xl/relaxed">
              {t('testimonials.subtitle')}
            </p>
          </div>
        </div>

        <div className="mx-auto grid gap-6 py-12 lg:grid-cols-3 lg:gap-8">
          {testimonialKeys.map((key, index) => (
            <Card 
              key={index} 
              className="relative overflow-hidden group dsm-bg-card dsm-hover-card rounded-2xl"
            >
              <CardContent className="p-6">
                {/* Rating */}
                <div className="flex items-center space-x-1 mb-4">
                  {[...Array(t(`testimonials.items.${key}.rating`))].map((_, i) => (
                    <Star key={i} className="h-4 w-4 fill-yellow-400 text-yellow-400" />
                  ))}
                </div>

                {/* Content */}
                <blockquote className="text-sm leading-relaxed mb-6 dsm-text-gray">
                  "{t(`testimonials.items.${key}.text`)}"
                </blockquote>

                {/* Author */}
                <div className="flex items-center space-x-3">
                  <div className="w-12 h-12 rounded-full flex items-center justify-center dsm-text-white font-bold dsm-bg-primary">
                    {t(`testimonials.items.${key}.name`).split(' ').map(n => n[0]).join('')}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-bold dsm-text-primary">
                      {t(`testimonials.items.${key}.name`)}
                    </p>
                    <p className="text-xs dsm-text-gray">
                      {t(`testimonials.items.${key}.location`)}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* CTA */}
        <div className="flex justify-center">
          <div className="text-center space-y-4">
            <p className="dsm-text-gray font-medium">
              {t('testimonials.cta')}
            </p>
            <div className="flex items-center justify-center space-x-3">
              <div className="flex -space-x-2">
                {testimonialKeys.slice(0, 3).map((key, index) => (
                  <div
                    key={index}
                    className="w-8 h-8 rounded-full flex items-center justify-center dsm-text-white text-xs font-bold border-2 border-white dsm-bg-primary"
                  >
                    {t(`testimonials.items.${key}.name`).split(' ').map(n => n[0]).join('')}
                  </div>
                ))}
              </div>
              <span className="text-sm font-semibold dsm-text-primary">{t('testimonials.users')}</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
