'use client'

import * as React from 'react'
import { useLanguage } from '@/contexts/language-context'
import { Search, Globe, MapPin, ArrowUpDown, Check, ChevronsUpDown } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
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
    const [countryOpen, setCountryOpen] = React.useState(false)
    const [countrySearch, setCountrySearch] = React.useState('')
    const countrySearchRef = React.useRef<HTMLInputElement>(null)

    // Focus le champ de recherche quand le popover s'ouvre
    React.useEffect(() => {
        if (countryOpen) {
            setTimeout(() => countrySearchRef.current?.focus(), 50)
        } else {
            setCountrySearch('')
        }
    }, [countryOpen])

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

    // Pays filtrés par la recherche
    const filteredCountries = React.useMemo(() => {
        if (!countrySearch.trim()) return countries
        const q = countrySearch.toLowerCase().trim()
        return countries.filter(c => c.name.toLowerCase().includes(q))
    }, [countrySearch])

    // Label affiché dans le trigger du sélecteur de pays
    const countryDisplayLabel = React.useMemo(() => {
        if (!filterCountry || filterCountry === 'all') {
            return t('dashboard.contests.all_countries') || 'Tous les pays'
        }
        if (countryOptions.hasMyCountry && countryOptions.myCountry && filterCountry === countryOptions.myCountry.name) {
            return countryOptions.myCountry.label
        }
        return filterCountry
    }, [filterCountry, countryOptions, t])

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
                        className="pl-10 bg-white border-gray-200 text-gray-900 placeholder-gray-400 focus:border-blue-500 dark:bg-gray-800 dark:border-gray-700 dark:text-white dark:placeholder-gray-400"
                    />
                </div>
            </div>

            {/* Sélecteur de continent */}
            {showContinentFilter && (
                <div className="w-full sm:w-48">
                    <Select value={filterContinent} onValueChange={(value) => onContinentChange?.(value)}>
                        <SelectTrigger className="bg-white border-gray-200 text-gray-900 dark:bg-gray-800 dark:border-gray-700 dark:text-white">
                            <Globe className="w-4 h-4 mr-2" />
                            <SelectValue placeholder={t('dashboard.contests.filter_continent') || 'Continent'} />
                        </SelectTrigger>
                        <SelectContent className="bg-white border-gray-200 dark:bg-gray-800 dark:border-gray-700 max-h-[300px]">
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

            {/* Sélecteur de pays avec recherche */}
            {showCountryFilter && (
                <div className="w-full sm:w-52">
                    <Popover open={countryOpen} onOpenChange={setCountryOpen}>
                        <PopoverTrigger asChild>
                            <button
                                type="button"
                                role="combobox"
                                aria-expanded={countryOpen}
                                className="flex h-10 w-full items-center justify-between rounded-md border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:border-gray-700 dark:bg-gray-800 dark:text-white dark:hover:bg-gray-750 dark:focus:ring-offset-gray-900"
                            >
                                <span className="flex items-center gap-2 truncate">
                                    <MapPin className="w-4 h-4 shrink-0 text-gray-500 dark:text-gray-400" />
                                    <span className="truncate">{countryDisplayLabel}</span>
                                </span>
                                <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                            </button>
                        </PopoverTrigger>
                        <PopoverContent className="w-[240px] p-0 bg-white border-gray-200 dark:bg-gray-800 dark:border-gray-700" align="start">
                            {/* Champ de recherche */}
                            <div className="p-2 border-b border-gray-200 dark:border-gray-700">
                                <div className="relative">
                                    <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                                    <input
                                        ref={countrySearchRef}
                                        type="text"
                                        placeholder={t('dashboard.contests.search_country_placeholder') || 'Rechercher un pays...'}
                                        value={countrySearch}
                                        onChange={(e) => setCountrySearch(e.target.value)}
                                        className="w-full h-9 pl-8 pr-3 rounded-md bg-gray-50 border border-gray-200 text-sm text-gray-900 placeholder-gray-500 focus:outline-none focus:border-blue-500 dark:bg-gray-900 dark:border-gray-700 dark:text-white"
                                    />
                                </div>
                            </div>
                            {/* Liste des pays */}
                            <div className="max-h-[250px] overflow-y-auto p-1">
                                {/* Option "Mon pays" */}
                                {!countrySearch && countryOptions.hasMyCountry && countryOptions.myCountry && (
                                    <button
                                        type="button"
                                        onClick={() => {
                                            onCountryChange?.(countryOptions.myCountry!.name)
                                            setCountryOpen(false)
                                        }}
                                        className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-sm text-blue-600 dark:text-blue-400 font-medium hover:bg-gray-100 dark:hover:bg-gray-700 cursor-pointer border-b border-gray-200 dark:border-gray-700 mb-1"
                                    >
                                        <Check className={`w-4 h-4 shrink-0 ${filterCountry === countryOptions.myCountry!.name ? 'opacity-100' : 'opacity-0'}`} />
                                        {countryOptions.myCountry!.label}
                                    </button>
                                )}
                                {/* Option "Tous les pays" */}
                                {!countrySearch && (
                                    <button
                                        type="button"
                                        onClick={() => {
                                            onCountryChange?.('all')
                                            setCountryOpen(false)
                                        }}
                                        className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-sm text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700 cursor-pointer"
                                    >
                                        <Check className={`w-4 h-4 shrink-0 ${(!filterCountry || filterCountry === 'all') ? 'opacity-100 text-blue-400' : 'opacity-0'}`} />
                                        {t('dashboard.contests.all_countries') || 'Tous les pays'}
                                    </button>
                                )}
                                {/* Liste filtrée */}
                                {filteredCountries.length > 0 ? (
                                    filteredCountries.map((country) => (
                                        <button
                                            type="button"
                                            key={country.code}
                                            onClick={() => {
                                                onCountryChange?.(country.name)
                                                setCountryOpen(false)
                                            }}
                                            className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-sm text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700 cursor-pointer"
                                        >
                                            <Check className={`w-4 h-4 shrink-0 ${filterCountry === country.name ? 'opacity-100 text-blue-400' : 'opacity-0'}`} />
                                            {country.name}
                                        </button>
                                    ))
                                ) : (
                                    <div className="px-2 py-4 text-center text-sm text-gray-500">
                                        {t('dashboard.contests.no_country_found' ) || 'Aucun pays trouvé'}
                                    </div>
                                )}
                            </div>
                        </PopoverContent>
                    </Popover>
                </div>
            )}

            {/* Sélecteur de tri */}
            {showSort && (
                <div className="w-full sm:w-44">
                    <Select value={sortBy} onValueChange={(value) => onSortChange?.(value)}>
                        <SelectTrigger className="bg-white border-gray-200 text-gray-900 dark:bg-gray-800 dark:border-gray-700 dark:text-white">
                            <ArrowUpDown className="w-4 h-4 mr-2" />
                            <SelectValue placeholder={t('dashboard.contests.sort') || 'Trier'} />
                        </SelectTrigger>
                        <SelectContent className="bg-white border-gray-200 dark:bg-gray-800 dark:border-gray-700">
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
