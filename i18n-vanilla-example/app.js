const DEFAULT_LANG = "en";
const STORAGE_KEY = "mh5_language_preference";
const SUPPORTED_LANGS = ["en", "sw"];

let activeDict = {};

function getNestedValue(obj, keyPath) {
  return keyPath.split(".").reduce((acc, key) => (acc && key in acc ? acc[key] : undefined), obj);
}

async function loadTranslations(lang) {
  const safeLang = SUPPORTED_LANGS.includes(lang) ? lang : DEFAULT_LANG;
  const cacheBuster = Date.now();
  const url = `./lang/${safeLang}.json?v=${cacheBuster}`;

  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Failed to load ${safeLang}.json (${response.status})`);
    }
    return await response.json();
  } catch (error) {
    console.error("[i18n] Translation load error:", error);
    if (safeLang !== DEFAULT_LANG) {
      return loadTranslations(DEFAULT_LANG);
    }
    return {};
  }
}

function applyTranslations(dict) {
  activeDict = dict || {};
  const nodes = document.querySelectorAll("[data-i18n]");

  nodes.forEach((node) => {
    const key = node.getAttribute("data-i18n");
    const translated = getNestedValue(activeDict, key);

    if (typeof translated === "string" && translated.trim() !== "") {
      node.textContent = translated;
    } else {
      // Missing-key fallback: keep visible key to simplify debugging.
      node.textContent = key || "";
      console.warn(`[i18n] Missing translation key: ${key}`);
    }
  });
}

async function setLanguage(lang) {
  const safeLang = SUPPORTED_LANGS.includes(lang) ? lang : DEFAULT_LANG;
  const dict = await loadTranslations(safeLang);
  applyTranslations(dict);

  localStorage.setItem(STORAGE_KEY, safeLang);
  document.documentElement.lang = safeLang;

  const switcher = document.getElementById("languageSwitcher");
  if (switcher) {
    switcher.value = safeLang;
  }
}

function initLanguageSwitcher() {
  const switcher = document.getElementById("languageSwitcher");
  if (!switcher) return;

  switcher.addEventListener("change", (event) => {
    setLanguage(event.target.value);
  });
}

async function bootstrapI18n() {
  initLanguageSwitcher();
  const saved = localStorage.getItem(STORAGE_KEY) || DEFAULT_LANG;
  await setLanguage(saved);
}

bootstrapI18n();
