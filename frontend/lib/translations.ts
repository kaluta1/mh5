/**
 * DEPRECATED barrel file.
 *
 * This file previously statically imported all 44 locale JSON files, adding
 * ~1.9 MB to the client bundle. It is now a thin compatibility shim.
 *
 * Import from `@/lib/locale-registry` for types/language list,
 * `@/lib/translations-loader` for runtime bundles, or
 * `@/lib/maintenance-translations` / `@/lib/seo-translations` for specific
 * static catalogs.
 */
export {
  languages,
  LANGUAGE_CODES,
  type Language,
  type LanguageInfo,
} from "./locale-registry"

/**
 * @deprecated The full in-memory translations object has been removed to keep
 * bundles small. Use `loadTranslations(lang)` from `@/lib/translations-loader`
 * for client code, or `@/lib/seo-translations` for server-side metadata.
 */
export const translations = new Proxy({} as Record<string, unknown>, {
  get(_target, prop) {
    throw new Error(
      `[translations] The synchronous translations object is deprecated and was removed to reduce bundle size. ` +
        `Requested key: "${String(prop)}". Use loadTranslations(lang) or import dedicated catalogs instead.`
    )
  },
})
