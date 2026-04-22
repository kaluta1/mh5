"use client"

import * as React from "react"
import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { ChevronLeft, ChevronRight, Trophy, Users, Heart, Camera, Music, Gamepad2, Zap, Mountain, Star } from "lucide-react"
import { useLanguage } from "@/contexts/language-context"

const carouselSlides = [
  {
    id: 1,
    icon: Trophy,
    title: "Concours de Beauté",
    titleEn: "Beauty Contests",
    titleSw: "Mashindano ya Urembo",
    titleEs: "Concursos de Belleza", 
    titleDe: "Schönheitswettbewerbe",
    description: "Découvrez les plus belles femmes",
    descriptionEn: "Discover the most attractive women",
    descriptionSw: "Gundua vipaji bora vya urembo",
    descriptionEs: "Descubre las mujeres más atractivas",
    descriptionDe: "Entdecken Sie die attraktivsten Frauen",
    gradient: "from-pink-100 to-purple-100",
    iconColor: "text-pink-600",
    bgColor: "bg-pink-100"
  },
  {
    id: 2,
    icon: Users,
    title: "Concours de Charme",
    titleEn: "Handsome Contests",
    titleSw: "Mashindano ya Mvuto",
    titleEs: "Concursos de Atractivo",
    titleDe: "Attraktivitätswettbewerbe",
    description: "Montrez votre charisme et votre personnalité",
    descriptionEn: "Show your charisma and personality",
    descriptionSw: "Onyesha haiba na utu wako",
    descriptionEs: "Muestra tu carisma y personalidad",
    descriptionDe: "Zeigen Sie Ihr Charisma und Ihre Persönlichkeit",
    gradient: "from-blue-100 to-cyan-100",
    iconColor: "text-blue-600",
    bgColor: "bg-blue-100"
  },
  {
    id: 3,
    icon: Music,
    title: "Musiques",
    titleEn: "Musics",
    titleSw: "Muziki",
    titleEs: "Músicas",
    titleDe: "Musik",
    description: "Promouvez votre musique et votez pour les chansons que vous aimez",
    descriptionEn: "Promote your music and vote for the songs you like",
    descriptionSw: "Tangaza muziki wako na piga kura kwa nyimbo unazopenda",
    descriptionEs: "Promociona tu música y vota por las canciones que te gustan",
    descriptionDe: "Bewerben Sie Ihre Musik und stimmen Sie für die Songs, die Ihnen gefallen",
    gradient: "from-green-100 to-emerald-100",
    iconColor: "text-green-600",
    bgColor: "bg-green-100"
  },
  {
    id: 4,
    icon: Heart,
    title: "Animaux de Compagnie",
    titleEn: "Pet Contests",
    titleSw: "Mashindano ya Wanyama wa Kufugwa",
    titleEs: "Concursos de Mascotas",
    titleDe: "Haustier-Wettbewerbe",
    description: "Vos animaux de compagnie préférés méritent d'être célébrés",
    descriptionEn: "Your favorite pets deserve to be celebrated",
    descriptionSw: "Wanyama wako wa kufugwa wanastahili kusherehekewa",
    descriptionEs: "Tus mascotas favoritas merecen ser celebradas",
    descriptionDe: "Ihre Lieblingshaustiere verdienen es, gefeiert zu werden",
    gradient: "from-orange-100 to-red-100",
    iconColor: "text-orange-600",
    bgColor: "bg-orange-100"
  },
  {
    id: 5,
    icon: Gamepad2,
    title: "Sports",
    titleEn: "Sports",
    titleSw: "Michezo",
    titleEs: "Deportes",
    titleDe: "Sport",
    description: "Promouvez votre sport favori et votez pour vos équipes et joueurs préférés",
    descriptionEn: "Promote your favorite sport and vote for your favorite teams and players.",
    descriptionSw: "Tangaza mchezo unaoupenda na piga kura kwa timu na wachezaji unaowapenda",
    descriptionEs: "Promociona tu deporte favorito y vota por tus equipos y jugadores favoritos",
    descriptionDe: "Bewerben Sie Ihren Lieblingssport und stimmen Sie für Ihre Lieblingsteams und -spieler",
    gradient: "from-purple-100 to-indigo-100",
    iconColor: "text-purple-600",
    bgColor: "bg-purple-100"
  },
  {
    id: 6,
    icon: Zap,
    title: "Danseurs",
    titleEn: "Dancers",
    titleSw: "Wachezaji wa Ngoma",
    titleEs: "Bailarines",
    titleDe: "Tänzer",
    description: "Montrez vos talents de danse et votez pour vos danseurs préférés",
    descriptionEn: "Showcase your dancing skills and vote for your favorite dancers",
    descriptionSw: "Onyesha kipaji chako cha kucheza na piga kura kwa wachezaji unaowapenda",
    descriptionEs: "Muestra tus habilidades de baile y vota por tus bailarines favoritos",
    descriptionDe: "Zeigen Sie Ihre Tanzfähigkeiten und stimmen Sie für Ihre Lieblingstänzer",
    gradient: "from-yellow-100 to-amber-100",
    iconColor: "text-yellow-600",
    bgColor: "bg-yellow-100"
  },
  {
    id: 7,
    icon: Mountain,
    title: "Merveille Naturelle",
    titleEn: "Natural Wonder",
    titleSw: "Maajabu ya Asili",
    titleEs: "Maravilla Natural",
    titleDe: "Naturwunder",
    description: "Promouvez votre lieu naturel préféré pour que d'autres puissent le découvrir",
    descriptionEn: "Promote your favorite natural scenic location for others to discover",
    descriptionSw: "Tangaza eneo lako la asili unalolipenda ili wengine waligundue",
    descriptionEs: "Promociona tu lugar natural favorito para que otros lo descubran",
    descriptionDe: "Bewerben Sie Ihren Lieblingsort in der Natur, damit andere ihn entdecken können",
    gradient: "from-teal-100 to-cyan-100",
    iconColor: "text-teal-600",
    bgColor: "bg-teal-100"
  },
  {
    id: 8,
    icon: Star,
    title: "Personne Célèbre",
    titleEn: "Famous Person",
    titleSw: "Mtu Maarufu",
    titleEs: "Persona Famoso",
    titleDe: "Berühmte Person",
    description: "Faites-nous connaître qui est votre modèle",
    descriptionEn: "Let's know who is your role model",
    descriptionSw: "Tuambie ni nani anayekutia moyo",
    descriptionEs: "Hagamos saber quién es tu modelo a seguir",
    descriptionDe: "Lassen Sie uns wissen, wer Ihr Vorbild ist",
    gradient: "from-rose-100 to-pink-100",
    iconColor: "text-rose-600",
    bgColor: "bg-rose-100"
  }
]

export function InteractiveCarousel() {
  const { language } = useLanguage()
  const [currentSlide, setCurrentSlide] = useState(0)
  const [isAutoPlaying, setIsAutoPlaying] = useState(true)

  // Auto-play functionality
  useEffect(() => {
    if (!isAutoPlaying) return

    const interval = setInterval(() => {
      setCurrentSlide((prev) => (prev + 1) % carouselSlides.length)
    }, 4000) // Change slide every 4 seconds

    return () => clearInterval(interval)
  }, [isAutoPlaying])

  const nextSlide = () => {
    setCurrentSlide((prev) => (prev + 1) % carouselSlides.length)
    setIsAutoPlaying(false) // Stop auto-play when user interacts
  }

  const prevSlide = () => {
    setCurrentSlide((prev) => (prev - 1 + carouselSlides.length) % carouselSlides.length)
    setIsAutoPlaying(false) // Stop auto-play when user interacts
  }

  const goToSlide = (index: number) => {
    setCurrentSlide(index)
    setIsAutoPlaying(false) // Stop auto-play when user interacts
  }

  const getTitle = (slide: typeof carouselSlides[0]) => {
    switch (language) {
      case 'en': return slide.titleEn
      case 'sw': return slide.titleSw
      case 'es': return slide.titleEs
      case 'de': return slide.titleDe
      default: return slide.titleEn
    }
  }

  const getDescription = (slide: typeof carouselSlides[0]) => {
    switch (language) {
      case 'en': return slide.descriptionEn
      case 'sw': return slide.descriptionSw
      case 'es': return slide.descriptionEs
      case 'de': return slide.descriptionDe
      default: return slide.descriptionEn
    }
  }

  const currentSlideData = carouselSlides[currentSlide]

  return (
    <div className="relative overflow-hidden rounded-xl shadow-xl">
      {/* Main carousel content */}
      <div 
        className={`h-80 bg-gradient-to-br ${currentSlideData.gradient} flex items-center justify-center transition-all duration-500 ease-in-out`}
        onMouseEnter={() => setIsAutoPlaying(false)}
        onMouseLeave={() => setIsAutoPlaying(true)}
      >
        <div className="text-center space-y-4 px-8">
          <div className={`w-20 h-20 ${currentSlideData.bgColor} rounded-full flex items-center justify-center mx-auto shadow-lg transition-transform duration-300 hover:scale-110`}>
            <currentSlideData.icon className={`h-10 w-10 ${currentSlideData.iconColor}`} />
          </div>
          <h3 className="text-2xl font-bold text-gray-800 transition-opacity duration-300">
            {getTitle(currentSlideData)}
          </h3>
          <p className="text-gray-600 max-w-md transition-opacity duration-300">
            {getDescription(currentSlideData)}
          </p>
        </div>
      </div>

      {/* Navigation arrows */}
      <Button
        variant="ghost"
        size="icon"
        className="absolute left-4 top-1/2 transform -translate-y-1/2 bg-blue-500 hover:bg-blue-600 rounded-full shadow-lg transition-all duration-200 hover:scale-110"
        onClick={prevSlide}
      >
        <ChevronLeft className="h-5 w-5 text-white" />
      </Button>
      
      <Button
        variant="ghost"
        size="icon"
        className="absolute right-4 top-1/2 transform -translate-y-1/2 bg-blue-500 hover:bg-blue-600 rounded-full shadow-lg transition-all duration-200 hover:scale-110"
        onClick={nextSlide}
      >
        <ChevronRight className="h-5 w-5 text-white" />
      </Button>

      {/* Indicators */}
      <div className="absolute bottom-4 left-1/2 transform -translate-x-1/2 flex space-x-2">
        {carouselSlides.map((_, index) => (
          <button
            key={index}
            className={`w-3 h-3 rounded-full transition-all duration-300 hover:scale-125 ${
              index === currentSlide 
                ? 'bg-white opacity-100 shadow-lg' 
                : 'bg-white/50 hover:bg-white/70'
            }`}
            onClick={() => goToSlide(index)}
          />
        ))}
      </div>

      {/* Progress bar */}
      <div className="absolute bottom-0 left-0 w-full h-1 bg-white/20">
        <div 
          className="h-full bg-white/60 transition-all duration-100 ease-linear"
          style={{
            width: isAutoPlaying ? `${((currentSlide + 1) / carouselSlides.length) * 100}%` : '0%'
          }}
        />
      </div>
    </div>
  )
}
