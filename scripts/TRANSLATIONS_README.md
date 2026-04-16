# Translations

The web UI supports 15 languages. English is the source of truth; every other language file lives in `frontend/lib/translations/<code>.json` and falls back to English for any missing key.

## Supported languages

| Code | Language        | RTL? |
|------|-----------------|------|
| en   | English         |      |
| fr   | Français        |      |
| es   | Español         |      |
| de   | Deutsch         |      |
| pt   | Português       |      |
| sw   | Kiswahili       |      |
| ar   | العربية         | yes  |
| zh   | 中文             |      |
| hi   | हिन्दी          |      |
| ru   | Русский         |      |
| it   | Italiano        |      |
| nl   | Nederlands      |      |
| tr   | Türkçe          |      |
| ja   | 日本語           |      |
| ko   | 한국어           |      |

## How to refresh translations

1. Edit `frontend/lib/translations/en.json` (English is the source of truth).
2. From the repo root, run the machine-translation script:

   ```bash
   pip install deep-translator         # one time
   python scripts/translate_locales.py
   ```

   - Default behaviour: only fills in *missing* keys per language (resumable, cached).
   - Translate one language only: `--langs ar`
   - Re-translate everything: `--overwrite`
   - Dry run (no API calls): `--dry-run`

3. Commit the updated JSON files.

## Notes

- The script protects placeholders (`{name}`, `{{count}}`, `<tag>`, urls, emails) from being mangled.
- Cache lives in `scripts/.translate_cache.json` so re-runs of the same English string are free.
- Arabic auto-applies `dir="rtl"` on `<html>` via `LanguageProvider`.
- Many components still contain hardcoded English strings that bypass `t()`. Those need to be migrated to `t('some.key')` before they will translate. See the open follow-up audit task.
