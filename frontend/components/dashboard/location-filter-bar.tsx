'use client'

import * as React from 'react'
import { useLanguage } from '@/contexts/language-context'
import { Search, Globe, MapPin, ArrowUpDown, Building2 } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { countries } from '@/lib/countries'

// Liste des continents disponibles
const CONTINENTS = [
    { value: 'all', label: 'Tous les continents' },
    { value: 'Africa', label: 'Afrique' },
    { value: 'Asia', label: 'Asie' },
    { value: 'Europe', label: 'Europe' },
    { value: 'North America', label: 'Amérique du Nord' },
    { value: 'South America', label: 'Amérique du Sud' },
    { value: 'Oceania', label: 'Océanie' },
    { value: 'Antarctica', label: 'Antarctique' }
]

// Options de tri
const SORT_OPTIONS = [
    { value: 'participants', labelKey: 'dashboard.contests.sort_participants', defaultLabel: 'Plus de participants' },
    { value: 'votes', labelKey: 'dashboard.contests.sort_votes', defaultLabel: 'Plus de votes' },
    { value: 'date', labelKey: 'dashboard.contests.sort_date', defaultLabel: 'Plus récent' },
    { value: 'name', labelKey: 'dashboard.contests.sort_name', defaultLabel: 'Nom (A-Z)' }
]

export interface LocationFilterBarProps {
    // Recherche
    searchTerm?: string
    onSearchChange?: (value: string) => void
    onSearch?: () => void
    searchPlaceholder?: string

    // Filtres de localisation
    filterContinent?: string
    onContinentChange?: (value: string) => void
    filterCountry?: string
    onCountryChange?: (value: string) => void

    // Tri
    sortBy?: string
    onSortChange?: (value: string) => void
    showSort?: boolean

    // Options d'affichage
    showSearchButton?: boolean
    showContinentFilter?: boolean
    showCountryFilter?: boolean
    showCityFilter?: boolean
    className?: string

    // Données utilisateur pour les filtres personnalisés
    user?: any // Type User
}

export function LocationFilterBar({
    searchTerm = '',
    onSearchChange,
    onSearch,
    searchPlaceholder,
    filterContinent = 'all',
    onContinentChange,
    filterCountry = '',
    onCountryChange,
    sortBy = 'participants',
    onSortChange,
    showSort = true,
    showSearchButton = true,
    showContinentFilter = true,
    showCountryFilter = true,
    showCityFilter = false,
    className = '',
    user
}: LocationFilterBarProps) {
    const { t } = useLanguage()

    // Options de continents avec "Mon continent" si disponible
    const continentOptions = React.useMemo(() => {
        // Filter out the user's continent from the standard list to avoid duplicates
        const options = CONTINENTS.filter(c => c.value !== user?.continent)

        if (user?.continent) {
            // Add explicit "My continent" option at the beginning (after 'all')
            // Find the original label to reuse or use user.continent
            const original = CONTINENTS.find(c => c.value === user.continent)
            const label = original ? original.label : user.continent

            // Insert after 'all' (index 1) or at end?
            // Let's put it as second option (after 'all')
            options.splice(1, 0, {
                value: user.continent,
                label: `${t('dashboard.contests.my_continent') || 'Mon continent'} (${label})`
            })
        }
        return options
    }, [user, t])

    // Options de pays avec "Mon pays" si disponible
    const countryOptions = React.useMemo(() => {
        let options = [...countries]
        if (user?.country) {
            // Ajouter "Mon pays"
            const myCountryOption = {
                code: 'MY_COUNTRY',
                name: user.country,
                label: `${t('dashboard.contests.my_country') || 'Mon pays'} (${user.country})`
            }
            return { hasMyCountry: true, myCountry: myCountryOption, all: options }
        }
        return { hasMyCountry: false, myCountry: null, all: options }
    }, [user, t])

    const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Enter' && onSearch) {
            onSearch()
        }
    }

    return (
        <div className={`flex flex-col sm:flex-row gap-4 flex-wrap ${className}`}>
            {/* Barre de recherche */}
            <div className="flex-1 min-w-[200px]">
                <div className="relative">
                    <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
                    <Input
                        type="text"
                        placeholder={searchPlaceholder || t('dashboard.contests.search_placeholder') || 'Rechercher...'}
                        value={searchTerm}
                        onChange={(e) => onSearchChange?.(e.target.value)}
                        onKeyPress={handleKeyPress}
                        className="pl-10 bg-gray-800 border-gray-700 text-white placeholder-gray-400 focus:border-blue-500"
                    />
                </div>
            </div>

            {/* Sélecteur de continent */}
            {showContinentFilter && (
                <div className="w-full sm:w-48">
                    <Select value={filterContinent} onValueChange={(value) => onContinentChange?.(value)}>
                        <SelectTrigger className="bg-gray-800 border-gray-700 text-white">
                            <Globe className="w-4 h-4 mr-2" />
                            <SelectValue placeholder={t('dashboard.contests.filter_continent') || 'Continent'} />
                        </SelectTrigger>
                        <SelectContent className="bg-gray-800 border-gray-700 max-h-[300px]">
                            {continentOptions.map((continent) => (
                                <SelectItem key={continent.value} value={continent.value} className={continent.value === user?.continent ? "text-blue-400 font-medium" : ""}>
                                    {continent.value === user?.continent
                                        ? continent.label
                                        : (t(`dashboard.contests.continents.${continent.value.toLowerCase().replace(/ /g, '_')}`) || continent.label)}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
            )}

            {/* Sélecteur de pays */}
            {showCountryFilter && (
                <div className="w-full sm:w-48">
                    <Select value={filterCountry || 'all'} onValueChange={(value) => onCountryChange?.(value)}>
                        <SelectTrigger className="bg-gray-800 border-gray-700 text-white">
                            <MapPin className="w-4 h-4 mr-2" />
                            <SelectValue placeholder={t('dashboard.contests.filter_country') || 'Pays'} />
                        </SelectTrigger>
                        <SelectContent className="bg-gray-800 border-gray-700 max-h-[300px]">
                            {/* Option "Mon pays" si disponible */}
                            {countryOptions.hasMyCountry && countryOptions.myCountry && (
                                <SelectItem value={countryOptions.myCountry.name} className="text-blue-400 font-medium border-b border-gray-700 mb-1 pb-1">
                                    {countryOptions.myCountry.label}
                                </SelectItem>
                            )}
                            {!user?.country && (
                                <SelectItem value="all">
                                    {t('dashboard.contests.all_countries') || 'Tous les pays'}
                                </SelectItem>
                            )}
                            {countries.map((country) => (
                                <SelectItem key={country.code} value={country.name}>
                                    {country.name}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
            )}

            {/* Sélecteur de tri */}
            {showSort && (
                <div className="w-full sm:w-44">
                    <Select value={sortBy} onValueChange={(value) => onSortChange?.(value)}>
                        <SelectTrigger className="bg-gray-800 border-gray-700 text-white">
                            <ArrowUpDown className="w-4 h-4 mr-2" />
                            <SelectValue placeholder={t('dashboard.contests.sort') || 'Trier'} />
                        </SelectTrigger>
                        <SelectContent className="bg-gray-800 border-gray-700">
                            {SORT_OPTIONS.map((option) => (
                                <SelectItem key={option.value} value={option.value}>
                                    {t(option.labelKey) || option.defaultLabel}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
            )}

            {/* Bouton Rechercher */}
            {showSearchButton && onSearch && (
                <Button
                    onClick={onSearch}
                    className="bg-blue-500 hover:bg-blue-600 dark:bg-blue-600 dark:hover:bg-blue-700 text-white px-6"
                >
                    <Search className="w-4 h-4 mr-2" />
                    {t('dashboard.contests.search_button') || 'Rechercher'}
                </Button>
            )}
        </div>
    )
}

export { CONTINENTS, SORT_OPTIONS }
