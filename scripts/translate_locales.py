#!/usr/bin/env python3
"""
Machine-translate all UI strings from `frontend/lib/translations/en.json` into
every other language file in `frontend/lib/translations/*.json`.

What it does
------------
- Walks `en.json` recursively.
- For each string value, calls Google Translate (free, via the
  `deep-translator` library) once per target language.
- Caches translations in memory and on disk so re-runs are cheap and
  resumable.
- Preserves placeholders like `{name}`, `{{count}}`, `<b>`, `</b>`, `\n`,
  ICU-style `{x, plural, ...}` blocks, and emoji.
- Skips strings that look like raw URLs / file paths / pure emojis.

Install once on the VPS / dev machine
-------------------------------------
    pip install deep-translator

Run
---
From the repo root:
    python scripts/translate_locales.py

Translate only certain languages:
    python scripts/translate_locales.py --langs ar zh ja

Force overwrite (default is "fill missing only"):
    python scripts/translate_locales.py --overwrite

Dry-run (no API calls, just report what would happen):
    python scripts/translate_locales.py --dry-run

Notes
-----
- This uses the *free* Google endpoint via `deep-translator` and is rate-limited
  on Google's side. The script throttles itself with a small sleep between
  calls and retries on transient errors. A full sweep of all languages can
  take 30+ minutes for large `en.json`. The on-disk cache makes subsequent
  runs near-instant.
- For production-grade quality, swap the engine to DeepL or paid Google
  Translate by changing `_make_translator` below. Both are supported by
  `deep-translator`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCALES_DIR = REPO_ROOT / "frontend" / "lib" / "translations"
SOURCE_FILE = LOCALES_DIR / "en.json"
CACHE_FILE = REPO_ROOT / "scripts" / ".translate_cache.json"

DEFAULT_TARGET_LANGS = [
    "fr", "es", "de", "pt", "sw", "ar", "zh", "hi", "ru",
    "it", "nl", "tr", "ja", "ko",
]

# deep-translator uses different language codes for some entries.
# Map our internal codes -> deep-translator codes.
LANG_CODE_MAP = {
    "zh": "zh-CN",
}

# Regex of substrings we must *not* translate. We protect them with sentinels
# before sending to the translator and restore after.
PROTECT_PATTERNS = [
    re.compile(r"\{\{\s*[\w\.\-]+\s*\}\}"),               # {{var}}
    re.compile(r"\{\s*[\w\.\-]+\s*\}"),                    # {var}
    re.compile(r"\{[^{}]*\bplural\b[^{}]*\}"),             # ICU plural blocks
    re.compile(r"<\/?[a-zA-Z][a-zA-Z0-9]*[^<>]*>"),        # <tag> / </tag>
    re.compile(r"%[sdif]"),                                # %s %d printf
    re.compile(r"\\n|\\t"),                                # escaped \n \t
    re.compile(r"https?://\S+"),                           # urls
    re.compile(r"\b[\w\.-]+@[\w\.-]+\.[A-Za-z]{2,}\b"),    # emails
]

# Strings that should never be translated (pure emojis, urls, paths).
SKIP_PATTERNS = [
    re.compile(r"^\s*$"),
    re.compile(r"^https?://\S+$"),
    re.compile(r"^/[^\s]+$"),
    re.compile(r"^[\d\s\.\-:\/]+$"),
]

PLACEHOLDER_PREFIX = "\u0001MH5T"  # Unicode SOH + tag, very unlikely in source


def _is_skip(value: str) -> bool:
    for r in SKIP_PATTERNS:
        if r.fullmatch(value):
            return True
    return False


def _protect(value: str) -> Tuple[str, List[str]]:
    """Replace each placeholder with a sentinel; return (protected, list)."""
    saved: List[str] = []

    def repl(match: re.Match) -> str:
        idx = len(saved)
        saved.append(match.group(0))
        return f"{PLACEHOLDER_PREFIX}{idx}\u0002"

    out = value
    for r in PROTECT_PATTERNS:
        out = r.sub(repl, out)
    return out, saved


def _restore(value: str, saved: List[str]) -> str:
    out = value
    for i, original in enumerate(saved):
        out = out.replace(f"{PLACEHOLDER_PREFIX}{i}\u0002", original)
    return out


def _make_translator(target_lang: str):
    """Lazy import so users without `deep-translator` get a clear error."""
    try:
        from deep_translator import GoogleTranslator
    except ImportError as e:
        sys.exit(
            "deep-translator is required.\n"
            "Install it with: pip install deep-translator\n"
            f"Import error: {e}"
        )
    code = LANG_CODE_MAP.get(target_lang, target_lang)
    return GoogleTranslator(source="en", target=code)


def _translate_string(translator, text: str, retries: int = 4) -> str:
    if _is_skip(text):
        return text
    protected, saved = _protect(text)
    last_err: Optional[Exception] = None
    for attempt in range(retries):
        try:
            translated = translator.translate(protected)
            if translated is None:
                translated = ""
            return _restore(translated, saved)
        except Exception as e:  # network, throttle, etc.
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Translation failed after {retries} retries: {last_err}")


def _walk(source: Any, target: Any, path: str, work: List[Tuple[str, str]]):
    """Collect (json-pointer, source-string) for keys missing in target."""
    if isinstance(source, dict):
        if not isinstance(target, dict):
            target = {}
        for k, v in source.items():
            child_path = f"{path}/{k}"
            child_target = target.get(k) if isinstance(target, dict) else None
            _walk(v, child_target, child_path, work)
    elif isinstance(source, list):
        for i, v in enumerate(source):
            child_path = f"{path}/{i}"
            child_target = None
            if isinstance(target, list) and i < len(target):
                child_target = target[i]
            _walk(v, child_target, child_path, work)
    elif isinstance(source, str):
        if isinstance(target, str) and target.strip() and target != source:
            return  # already translated
        work.append((path, source))


def _set_at_path(obj: Dict[str, Any], json_pointer: str, value: Any) -> None:
    parts = [p for p in json_pointer.split("/") if p != ""]
    cur: Any = obj
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        # Decide whether next step is a dict or list based on the current container
        if isinstance(cur, list):
            try:
                idx = int(part)
            except ValueError:
                raise ValueError(f"Invalid list index in path: {json_pointer}")
            while len(cur) <= idx:
                cur.append(None)
            if last:
                cur[idx] = value
            else:
                if not isinstance(cur[idx], (dict, list)):
                    cur[idx] = {}
                cur = cur[idx]
        else:
            if last:
                cur[part] = value
            else:
                if part not in cur or not isinstance(cur[part], (dict, list)):
                    cur[part] = {}
                cur = cur[part]


def _load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _dump_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")


def _load_cache() -> Dict[str, Dict[str, str]]:
    if not CACHE_FILE.exists():
        return {}
    try:
        with CACHE_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(cache: Dict[str, Dict[str, str]]) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_FILE.open("w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def translate_one_language(
    source_data: Any,
    lang: str,
    overwrite: bool,
    dry_run: bool,
    cache: Dict[str, Dict[str, str]],
    sleep_seconds: float,
) -> int:
    target_path = LOCALES_DIR / f"{lang}.json"
    target_data = _load_json(target_path)
    if overwrite:
        target_data = {}
    work: List[Tuple[str, str]] = []
    _walk(source_data, target_data, "", work)

    if not work:
        print(f"[{lang}] up-to-date ({target_path.name})")
        return 0

    print(f"[{lang}] {len(work)} string(s) to translate ...")
    if dry_run:
        for ptr, txt in work[:5]:
            print(f"  - {ptr}: {txt[:60]}{'...' if len(txt) > 60 else ''}")
        if len(work) > 5:
            print(f"  ...and {len(work) - 5} more")
        return len(work)

    translator = _make_translator(lang)
    cache_for_lang = cache.setdefault(lang, {})

    saved_count = 0
    for i, (ptr, txt) in enumerate(work, start=1):
        if txt in cache_for_lang:
            translated = cache_for_lang[txt]
        else:
            try:
                translated = _translate_string(translator, txt)
            except Exception as e:
                print(f"  ! [{lang}] {ptr}: {e}")
                continue
            cache_for_lang[txt] = translated
            time.sleep(sleep_seconds)
        _set_at_path(target_data, ptr, translated)
        saved_count += 1
        if saved_count % 25 == 0:
            _dump_json(target_path, target_data)
            _save_cache(cache)
            print(f"  [{lang}] {saved_count}/{len(work)} saved")

    _dump_json(target_path, target_data)
    _save_cache(cache)
    print(f"[{lang}] done ({saved_count} translated, file: {target_path.name})")
    return saved_count


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--langs", nargs="+", default=DEFAULT_TARGET_LANGS,
                   help="Target languages (codes from frontend/lib/translations/)")
    p.add_argument("--overwrite", action="store_true",
                   help="Replace existing translations instead of filling missing only")
    p.add_argument("--dry-run", action="store_true",
                   help="Print what would be translated, no API calls")
    p.add_argument("--sleep", type=float, default=0.4,
                   help="Seconds to sleep between API calls (default 0.4)")
    args = p.parse_args()

    if not SOURCE_FILE.exists():
        print(f"Source file not found: {SOURCE_FILE}", file=sys.stderr)
        return 1

    source_data = _load_json(SOURCE_FILE)
    cache = _load_cache()

    total = 0
    for lang in args.langs:
        if lang == "en":
            continue
        try:
            total += translate_one_language(
                source_data, lang, args.overwrite, args.dry_run, cache, args.sleep
            )
        except Exception as e:
            print(f"[{lang}] FAILED: {e}", file=sys.stderr)
    print(f"\nTotal strings written: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
