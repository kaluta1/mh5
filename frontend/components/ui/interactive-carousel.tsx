"use client"

import * as React from "react"
import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { ChevronLeft, ChevronRight, Trophy, Users, Heart, Camera, Music, Gamepad2 } from "lucide-react"
import { useLanguage } from "@/contexts/language-context"

const carouselSlides = [
  {
    id: 1,
    icon: Trophy,
    title: "Concours de Beauté",
    titleEn: "Beauty Contests",
    titleEs: "Concursos de Belleza", 
    titleDe: "Schönheitswettbewerbe",
    description: "Découvrez les plus beaux talents de votre région",
    descriptionEn: "Discover the most beautiful talents in your region",
    descriptionEs: "Descubre los talentos más hermosos de tu región",
    descriptionDe: "Entdecken Sie die schönsten Talente Ihrer Region",
    gradient: "from-pink-100 to-purple-100",
    iconColor: "text-pink-600",
    bgColor: "bg-pink-100"
  },
  {
    id: 2,
    icon: Users,
    title: "Concours de Charme",
    titleEn: "Handsome Contests",
    titleEs: "Concursos de Atractivo",
    titleDe: "Attraktivitätswettbewerbe",
    description: "Montrez votre charisme et votre personnalité",
    descriptionEn: "Show your charisma and personality",
    descriptionEs: "Muestra tu carisma y personalidad",
    descriptionDe: "Zeigen Sie Ihr Charisma und Ihre Persönlichkeit",
    gradient: "from-blue-100 to-cyan-100",
    iconColor: "text-blue-600",
    bgColor: "bg-blue-100"
  },
  {
    id: 3,
    icon: Music,
    title: "Latest Hits",
    titleEn: "Latest Hits",
    titleEs: "Últimos Éxitos",
    titleDe: "Neueste Hits",
    description: "Partagez vos créations musicales et artistiques",
    descriptionEn: "Share your musical and artistic creations",
    descriptionEs: "Comparte tus creaciones musicales y artísticas",
    descriptionDe: "Teilen Sie Ihre musikalischen und künstlerischen Kreationen",
    gradient: "from-green-100 to-emerald-100",
    iconColor: "text-green-600",
    bgColor: "bg-green-100"
  },
  {
    id: 4,
    icon: Heart,
    title: "Animaux de Compagnie",
    titleEn: "Pet Contests",
    titleEs: "Concursos de Mascotas",
    titleDe: "Haustier-Wettbewerbe",
    description: "Vos compagnons à quatre pattes méritent d'être célébrés",
    descriptionEn: "Your four-legged companions deserve to be celebrated",
    descriptionEs: "Tus compañeros de cuatro patas merecen ser celebrados",
    descriptionDe: "Ihre vierbeinigen Begleiter verdienen es, gefeiert zu werden",
    gradient: "from-orange-100 to-red-100",
    iconColor: "text-orange-600",
    bgColor: "bg-orange-100"
  },
  {
    id: 5,
    icon: Gamepad2,
    title: "Clubs Sportifs",
    titleEn: "Sports Clubs",
    titleEs: "Clubes Deportivos",
    titleDe: "Sportvereine",
    description: "Compétitions sportives et défis entre équipes",
    descriptionEn: "Sports competitions and team challenges",
    descriptionEs: "Competencias deportivas y desafíos de equipo",
    descriptionDe: "Sportwettbewerbe und Teamherausforderungen",
    gradient: "from-purple-100 to-indigo-100",
    iconColor: "text-purple-600",
    bgColor: "bg-purple-100"
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
      case 'es': return slide.titleEs
      case 'de': return slide.titleDe
      default: return slide.title
    }
  }

  const getDescription = (slide: typeof carouselSlides[0]) => {
    switch (language) {
      case 'en': return slide.descriptionEn
      case 'es': return slide.descriptionEs
      case 'de': return slide.descriptionDe
      default: return slide.description
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
        className="absolute left-4 top-1/2 transform -translate-y-1/2 bg-white/80 hover:bg-white/90 rounded-full shadow-lg transition-all duration-200 hover:scale-110"
        onClick={prevSlide}
      >
        <ChevronLeft className="h-5 w-5 text-gray-700" />
      </Button>
      
      <Button
        variant="ghost"
        size="icon"
        className="absolute right-4 top-1/2 transform -translate-y-1/2 bg-white/80 hover:bg-white/90 rounded-full shadow-lg transition-all duration-200 hover:scale-110"
        onClick={nextSlide}
      >
        <ChevronRight className="h-5 w-5 text-gray-700" />
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
