# Uzbek locale audit + fix — OpenWebUI fork (260911)

**Status: DEPLOYED 260911 09:46.** Merged to `custom/main` and pushed
(`b7ab075a3` theme, `5213e9bc6` main fix, `ee6b1c777` terminology).
Image rebuilt, container recreated behind the idle gate, health 200 in 24 s,
new strings verified present in the served bundle.

Files: `openwebui/src/lib/i18n/locales/uz-Latn-UZ/translation.json` (3,046 keys),
`uz-Cyrl-UZ/translation.json` (3,053), against `en-US` (3,029).

## 0. Method

Two passes, because they catch different things.

1. **Mechanical, all 3,046 keys.** Key coverage, empty values, `{{placeholder}}`
   integrity, and a cross-script diff: transliterate the Cyrillic file with
   legal-rag's own `llamaindex/domain/script.py:translite()` and compare to the
   Latin file. The two locales are the same language in two alphabets, so any
   disagreement is a defect in one of them.
2. **Judgement, top ~150 by render frequency.** Counted `$i18n.t('…')` call
   sites in `src/` so the most-visible chrome is reviewed first.

Pass 1 cannot see a string that is wrong *identically in both files* — `Light`
-> `Nur` scores a perfect match and never surfaces. Pass 2 exists for that.

**Mechanical health is good:** 0 missing keys, 0 empty values, 0 placeholder-set
mismatches. The damage is word choice, and it is concentrated in the Latin file.

| check | uz-Latn | uz-Cyrl |
|---|---|---|
| missing vs en-US | 0 | 0 |
| value left in English | 84 (mostly brand names — correct) | 75 |
| placeholder set mismatch | 0 | 0 |
| cross-script divergence | 218 raw -> 86 after canonicalising translit quirks -> **47 genuine word choice** | |

## 1. The theme menu (the screenshot) — APPLIED, grounded

`Her` is hardcoded in `General.svelte:216` (the movie easter egg) — correctly
not translated.

### Evidence: what shipped Uzbek locales actually use

| source | `Dark` | `Light` |
|---|---|---|
| Google ChromeOS `ash/strings/ash_strings_uz.xtb` | `Tungi mavzu` (x4) | — |
| Google Chrome Android `browser_ui_strings_uz.xtb` | `Mavzu rangi: tungi` | `Mavzu rangi: kunduzgi` |
| Wikipedia uz, Vector skin `i18n/uz.json` | `Tungi mavzu` | `Yorqin mavzu` |
| GNOME Epiphany `po/uz.po` | `Tungi mavzu` | `Yorqin mavzu` |
| Linux Mint xed `po/uz.po` | `Tungi mavzu` | — |
| Reactive Resume `uz-UZ.po` | `Toʻq mavzu` | `Yorugʻ mavzu` |

(Chromium `.xtb` files carry no English; recovered by joining the `uz` file
against `en-GB` on message id — 2,835 ids matched for ChromeOS, 794 for Android.)

Three conclusions the evidence forces:

1. **`tungi` is the word for dark** — 5 of 6 sources, including both Google
   products.
2. **`tema` is attested nowhere; every source uses `mavzu`.** This file already
   has `"Theme": "Mavzu"`, so `tema` would be its only Russian loan here.
3. **`yorqin` and `yorugʻ` are already taken in Google's Uzbek.**
   `Brightness` -> `Yorqinlik`; `light sensors` -> `yorugʻlik sensorlari`.
   Google therefore uses `kunduzgi` (daytime) for the light theme, which does
   not collide.

Trap avoided: ChromeOS uses `Tungi rejim` for **Night Light** (the blue-light
filter), a different feature. Dark theme is `Tungi mavzu`, never `Tungi rejim`.

### Applied

The select already carries the label `Mavzu`, so the options are bare
adjectives — Google's own `Mavzu rangi: tungi / kunduzgi` shape.

| key | was (Latn / Cyrl) | now |
|---|---|---|
| `Light` | `Nur` / `Нур` (= a ray of light; also a personal name) | `Kunduzgi` / `Кундузги` |
| `Dark` | `Qorong'i` / `Қоронғи` (= gloomy, unlit) | `Tungi` / `Тунги` |
| `OLED Dark` | `OLED qorong'i` / `ОЛЕД қоронғи` (acronym transliterated) | `Tungi (OLED)` / `Тунги (OLED)` |
| `System` | `Tizim` / `Тизим` (bare noun) | `Tizim bo'yicha` / `Тизим бўйича` |

Both files re-parsed after the edit (3,046 / 3,053 keys); diff is 8 lines.
Wikipedia's precedent for the OS-follow option is `Avtomatik` — a valid
alternative to `Tizim bo'yicha` if you prefer it.

## 2. Outright wrong words — uz-Latn

Machine-translation damage: the English word was translated in its *everyday*
sense instead of its software sense.

| key | now | means | suggested |
|---|---|---|---|
| `Run`, `Running`, `Running...` | `Yugurish` | **jogging** | `Ishga tushirish`, `Ishlamoqda`, `Ishlamoqda...` |
| `Seed` | `Urug'` | **a plant seed / semen** | `Seed` (keep — sampling term) |
| `Gemini` | `Egizaklar` | **the zodiac sign Twins** | `Gemini` (brand name) |
| `Valves` | `Vanalar` | **plumbing valves** | `Valves` or `Sozlash parametrlari` |
| `Select a engine`, `Select Engine` | `Dvigatelni tanlang` | **car engine** (used for web-search + code-execution engines) | `Mexanizmni tanlang` |
| `Code Interpreter` | `Kod tarjimoni` | **code translator** (language interpreter) | `Kod interpretatori` |
| `Away` | `Uzoqda` | **far away in distance** (it is a presence status) | `Joyida yo'q` |
| `Pull a model from Ollama.com` | `...modelni torting` | **physically pull/drag** | `...modelni yuklab oling` |
| `Select an Ollama instance` | `Ollama misolini tanlang` | **example** (as in a maths example) | `Ollama nusxasini tanlang` |
| `Strip Existing OCR` | `Mavjud OCRni ajratib oling` | **extract** — the opposite of strip | `Mavjud OCR ni olib tashlash` |
| `Preview` | `Ko'rib chiqish` | **review / consider** | `Oldindan ko'rish` |
| `Name` (24 call sites) | `Ism` | **a person's given name** (used for models, files, folders) | `Nomi` |
| `Actions` (14 sites) | `Harakatlar` | **physical movements** | `Amallar` |
| `System Prompt` | `Tizim so'rovi` | **system request/query** | `Tizim ko'rsatmasi` |
| `Unpin` | `Yechish` | **untie / solve a problem** | `Qadashni bekor qilish` |
| `Regenerate` | `Qayta tiklash` | **restore** — and it collides with `Reset` | `Qayta yaratish` |
| `variable` | `o'zgaruvchan` | adjective "changeable"; the noun is wanted | `o'zgaruvchi` |
| `Stop` | `STOP` | untranslated, shouting | `To'xtatish` |
| `Loading...` (19 sites) | `...` | **the word is missing entirely** | `Yuklanmoqda...` |
| `PDF Extract Images (OCR)` | `PDF ekstrakti rasmlari` | not parseable | `PDF dan rasmlarni ajratib olish (OCR)` |
| `Default (Open AI)` | `Standart (Ochiq AI)` | **the brand name was translated** | `Standart (OpenAI)` |
| `Uh-oh! There was an issue with the response.` | `Uh-oh! ...` | English interjection kept | `Afsuski, javobda muammo yuz berdi.` |
| `Select an auth method` | `Auth usulini tanlang` | `Auth` untranslated | `Autentifikatsiya usulini tanlang` |
| `Knowledge` | `Bilim` | abstract knowledge; the section holds documents | `Bilimlar bazasi` |
| `Copied` | `Ko'chirildi` | inconsistent with `Copy` -> `Nusxalash` | `Nusxalandi` |

## 3. Wrong in uz-Cyrl

| key | now | problem | suggested |
|---|---|---|---|
| `Loading...` | `Кокоро.жс юкланмоқда...` | **a JS library name (Kokoro.js) transliterated into Cyrillic**, hardcoded into a generic loading string | `Юкланмоқда...` |
| `Enter Playwright WebSocket URL` | `Perplexity WebSocket URL манзилини киритинг` | **wrong product name** — Playwright became Perplexity | `Playwright WebSocket URL манзилини киритинг` |
| `Select Engine` | `ДИшловчи тизимни танланг` | stray `Д` typo + trailing space | `Механизмни танланг` |
| `API Key`, `API keys`, `API Base URL`, `API Version`, `API Key created.`, `API Key Endpoint Restrictions` | `Дастурий Илова Интерфейси(API) …` | the acronym is expanded in full on 43+ call sites; no other locale does this and it overflows narrow labels | `API калити`, `API калитлари`, `API базавий URL`, … |
| `STT Model` | `СТТ модели` | acronym transliterated | `STT модели` |
| `Away` | `Йўқ` | just "no" | `Жойида йўқ` |
| `Bocha/Bing/Brave Search API Key` | left in English | inconsistent — the Latin file translates these | `… қидирув API калити` |

## 4. Brand names and acronyms that must not be translated

Checked mechanically over every key: if a product name or acronym appears in the
English key, it must survive verbatim into the value. **20 keys in uz-Latn and
46 in uz-Cyrl lost it.**

### Must fix — product names translated or phonetically respelled

| key | uz-Latn | uz-Cyrl | should be |
|---|---|---|---|
| `Gemini` | `Egizaklar` (the zodiac Twins) | `Gemini` ok | `Gemini` |
| `Whisper (Local)` | `Shivirlash (mahalliy)` (= whispering) | `Шивирлаш (маҳаллий)` | `Whisper (Local)` |
| `Automatic1111` | `Avtomatik 1111` | `Автоматик1111` | `Automatic1111` |
| `Pipelines` | `Payplaynlar` | `Пайплайнлар` | `Pipelines` |
| `Pipelines Not Detected` | `Pipeline-lar aniqlanmadi` | `Pipeline-лар аниқланмади` | pick ONE spelling |
| `Pipelines Valves` | `Pipeline klapanlari` (`klapan` = plumbing valve) | `Pipeline клапанлари` | `Pipelines Valves` |
| `Enter Jupyter URL/Token/Password` | ok | **`Jupiter`** — the planet, not the notebook | `Jupyter` |
| `Enter Playwright WebSocket URL` | ok | **`Perplexity`** — a different company | `Playwright` |
| `Kokoro.js (Browser)`, `Kokoro.js Dtype`, `Loading Kokoro.js...` | ok | `Кокоро.жс` | `Kokoro.js` |
| `Tika Server URL` | ok | `Тика` | `Tika` |
| `Manage Ollama`, `Trouble accessing Ollama?`, `Select an Ollama instance` | ok | `Оллама` | `Ollama` |
| `YouTube` | `Youtube` | `Youtube` | `YouTube` |
| `Add/Edit Arena Model` | ok | `Арена` | `Arena` |

`Pipelines` is the clearest symptom: the same file spells it `Payplaynlar`,
`Pipeline-lar` and `Pipeline` in three adjacent strings.

### Must fix — acronyms transliterated into Cyrillic

Latin acronyms stay Latin inside Uzbek Cyrillic text. The Cyrillic file breaks
this in: `ОЛЕД` (OLED), `СТТ` (STT ×2), `СВГ` (SVG), `РАМ` (RAM ×2), `ГПУ` (GPU),
`ЛЛМ` (LLM ×2), `ДН` (DN), and `Дастурий Илова Интерфейси(API)` (API, 43+ sites,
see §3).

### Acceptable — leave alone

`UI` -> `interfeys` / `интерфейс` and `ID` -> `identifikator` /
`идентификатор` are established Uzbek renderings, not errors. `URL` ->
`manzil` is fine too, though the files alternate between `manzil` and
`URL manzili` — worth settling on one.

## 5. One real bug, not a style issue

`Version {{selectedVersion}} of {{totalVersions}}`

- Latin: `{{totalVersions}} versiyasining {{selectedVersion}} versiyasi` — correct.
- **Cyrillic: `{{selectedVersion}} версиясининг {{totalVersions}} версияси` — the
  two placeholders are swapped**, so the message renders "version 5 of 3" when
  the user is on version 3 of 5.

The placeholder check reported 0 mismatches because it compares the *set* of
placeholders. Order inversion is invisible to a set comparison — worth knowing
before trusting that column.

## 6. Systemic, whole-file

**(a) Three apostrophe characters in uz-Latn.** Uzbek `o'` / `g'` are written
with one mark; this file uses four:

| character | strings |
|---|---|
| ASCII `'` | 908 |
| `ʻ` U+02BB (official orthography) | 57 |
| `‘` U+2018 (left quotation mark) | 39 |
| `` ` `` U+0060 | 2 |
| **two styles inside one value** | **10** |

Pick one and normalise. ASCII `'` is the pragmatic choice (it is already 93% of
the file, and it is typeable and searchable); `ʻ` U+02BB is the orthographically
correct one for official copy. Either is a one-pass script — the defect is the
mixture, which makes strings fail to match in search and look inconsistent
side by side.

**(b) `Delete` and `Disable` share one word.** `Delete All` and `Disable All`
both render `Barchasini o'chirish`, and `Remove` and `Delete` both render
`O'chirish`. In Uzbek `o'chirish` legitimately means both *delete* and *switch
off*, so the label cannot tell a user whether the button destroys data or just
turns something off. Suggest: `Delete` -> `O'chirish`, `Remove` ->
`Olib tashlash`, `Disable` -> `Faolsizlantirish` (or `O'chirib qo'yish`).

Other collisions found: `Create`/`Generate`/`Generation` -> `Yaratish`;
`Updated`/`Updated at`/`Updated At` -> `Yangilangan`; `Reset`/`Regenerate` ->
`Qayta tiklash` (see §2).

**(c) 143 short labels are in the imperative.** `Allow Chat Delete` ->
`Chatni o'chirishga ruxsat bering` ("allow it!"), while the surrounding buttons
use the verbal noun (`Saqlash`, `Yopish`, `Tahrirlash`). Uzbek UI convention:
**verbal noun for buttons, toggles and menu items; imperative only for
placeholders and hint text.** Settings toggles are the worst affected —
`… ruxsat bering` should be `… ruxsat berish` throughout.

## 7. What is fine

- 84 / 75 "untranslated" values are overwhelmingly brand and protocol names
  (`Bing`, `Brave`, `ComfyUI`, `Azure OpenAI`, `Bearer`, `DD/MM/YYYY`) — correct
  as-is.
- Month names lowercase (`sentyabr`) — correct for Uzbek.
- The core verbs (`Saqlash`, `Yopish`, `Tahrirlash`, `Bekor qilish`,
  `Yuklab olish`, `Qidiruv`) are natural and consistent across both scripts.

## 8. Unresolved

- Apostrophe convention is a product decision (ASCII vs U+02BB) — not applied.
- Theme pair: `Tungi`/`Kunduzgi` (recommended) vs `Qorong'i`/`Yorug'`
  (minimal change) — not applied.
- Whether `Valves` should stay an untranslated product term (it is a
  developer-facing OpenWebUI concept) or be described — the two locales
  currently disagree.
- The 143 imperative labels were counted, not individually reviewed; some are
  genuine placeholders where the imperative is correct.

## 9. Outcome

| check | before | after |
|---|---|---|
| brand/acronym terms lost in translation | 54 keys | **0** |
| genuine cross-script word-choice divergence | 47 | **2** (long paraphrases, benign) |
| apostrophe conventions in uz-Latn | ASCII 908 / U+02BB 57 / U+2018 39 / backtick 2, 10 values mixing | **ASCII only** (2 code-span backticks left deliberately) |
| placeholder-set mismatches | 0 | 0 |
| placeholder ORDER bugs | 1 (Cyrillic) | **0** |
| broken markup tags | 1 (`<стронг>`) | **0** |
| unreachable URL paths in hints | 2 | **0** |
| delete/disable label collisions | 3 | **0** |
| imperative toggle labels | 209 | 125 (only settings toggles + buttons were moved; the rest are placeholders where the imperative is correct Uzbek) |

Diff: 291 changed lines across the two files. Key counts unchanged
(3,046 / 3,053), both files re-parse.

### Found only while fixing (not in the original audit)

- **`<strong>` had been transliterated to `<стронг>`** in the delete-confirmation
  string, so the tag rendered as literal text instead of emphasising the name
  being deleted.
- **Ollama hints pointed at `{{url}}/api/тагс` and `{{url}}/моделс`** - the URL
  paths were transliterated, so they name no reachable endpoint.
- **CPU `threads` rendered as `ip` (rope) and `mavzu` (theme)** in the worker
  -thread setting; the Cyrillic file had it right (`oqim`).
- **`endpoint` calqued as `so'nggi nuqta`** ("final point") in 7 Latin and 6
  Cyrillic strings; normalised to `manzil`, which the Cyrillic file already used.
- **Latin text sitting in the Cyrillic file** (`Ilovaning noyob aniqlovchisi(DN)`).
- **`Document Intelligence` rendered as "razvedka"** (espionage) in Cyrillic.

## 10. The alphabet reform (checked 260911, changes nothing yet)

Uzbekistan is replacing the digraph and apostrophe letters:

| current | new |
|---|---|
| `Oʻ oʻ` | `Ö ö` |
| `Gʻ gʻ` | `Ğ ğ` |
| `Sh sh` | `Ş ş` |
| `Ch ch` | `Ç ç` |

`ng` is dropped as a separate letter; the tutuq belgisi (apostrophe) stays.
Result: 28 letters + 1 apostrophe, replacing 26 letters + 3 digraphs.

**Status:** Legislative Chamber adopted it 2026-07-07; the Senate approved it
2026-09-10; **it is with the president for signature and is not yet law.**
Rollout is explicitly gradual (textbooks from 2027); existing documents,
currency and signage stay valid.

**Decision: do not adopt Ö/Ğ/Ş/Ç now.** Nothing users touch renders it - Google,
Wikipedia, GNOME and phone keyboards are all still Oʻ/Gʻ - and the whole legal
corpus is old orthography. The app would be the only thing on screen in the new
alphabet.

**But it did decide the apostrophe question.** Normalising to U+02BB would be
investing in a character being retired. ASCII was chosen instead because
the legal-rag backend's `llamaindex/domain/script.py` emits `o'` / `g'` for
every transliterated answer,
so the chrome now matches the content.

**The later migration stays mechanical:** the glottal stop never follows `o` or
`g` (`ma'lumot`, `she'r`, `san'at`), so `o'`->`ö` and `g'`->`ğ` is an
unambiguous replacement. It must move together across the locales,
`domain/script.py`, and the `legal_coverage/` markers that contain literals like
`o'g'rilik` - those match on `script.py` output, and changing one side silently
breaks retrieval with no failing test.

## 11. Unresolved

- Not deployed. The openwebui backend/frontend is baked into the image:
  rebuild via `deploy/docker-compose.yml` then recreate `open-webui`.
  `deploy/deploy.sh` pulls `custom/main`, so the branch must be merged there or
  the next deploy reverts it.
- `Theme` and chat `Thread` both render `Mavzu`. Idiomatic for each in
  isolation, and they never share a screen, so left alone.
- 125 imperative labels remain; they are placeholders and hint text where the
  imperative is correct. Not individually reviewed.
- No locale lint exists. The four checks used here (brand allow-list,
  placeholder set *and order*, markup-tag survival, cross-script divergence via
  `script.py`) would catch every functional bug found today and could be a test.
- A native-speaker review of the ~90 wording choices is still worth doing; this
  pass grounded terminology in shipped locales but did not have a human reviewer.

## 12. Terminology cluster (found by verifying the deployed bundle)

The first deploy verified clean except one leftover: `Dvigatelni` (a car engine)
still appeared once in the bundle. It was not a miss but a cluster - the audit
had only looked at the two `Select…Engine` keys.

`Engine` was rendered **five** ways: `mexanizm` (10x), `motor` (7x), `dvigatel`
(4x), `tizim` (2x), `vosita` (1x). Two were also garbled, not merely
inconsistent:

| key | was | reads as |
|---|---|---|
| `Embedding Model Engine` | `Dvigatel modelini o'rnatish` | "install the engine model" - words reversed |
| `Reranking Engine` | `Dvigatelni qayta tartiblash` | "re-sort the engine" - reversed |
| `Enter SerpApi Engine` | `SerpApi dvigateliga kiring` | "enter INTO the SerpApi engine" |
| `Google PSE Engine Id` (Cyrl) | `Google PSE Энгине...` | "Engine" transliterated |

A scan for the same signature across other UI nouns confirmed the translator had
worked key-by-key throughout:

| term | renderings before | after |
|---|---|---|
| Engine | 5 | 1 (+ `qidiruv tizimi` for Web Search Engine, which is correct) |
| Folder | `papka` 25x / `jild` 5x | `jild` |
| Tool | `vosita` 31x / `asbob` 26x | `vosita` |
| Prompt | `prompt` 41x / `so'rov` 16x / `ko'rsatma` 5x | `prompt` |
| Knowledge | `bilim` 50x / `ma'lumot` 2x | `bilim` |

`jild` over `papka` is grounded - Google's Uzbek uses `jild`; `papka` is a
Russian loan. `Web Search Engine` stays `qidiruv tizimi`, also confirmed in
Google's Uzbek. The rest follow the rendering already dominant in the file.

Mechanically this is a stem swap, which works because Uzbek is agglutinative:
`asboblarni` -> `vositalarni`, `papkaga` -> `jildga`. Capitalised forms need
their own entry - one `Ma'lumotlar` survived the first pass because only the
lowercase stem was listed.

Deliberately left (different meanings, not inconsistency): `thread` is `mavzu`
for a chat thread and `oqim` for a CPU thread; `endpoint` keeps the English term
in 3 API-settings labels; `chunk` is `bo'lak`/`chunk`.

## 13. Deploy note: the image build OOMs nondeterministically

The first rebuild **failed** with `FATAL ERROR: ... JavaScript heap out of
memory` in `npx vite build` (`deploy/Dockerfile:46`,
`NODE_OPTIONS=--max-old-space-size=4096`). It was **not** caused by this change:
the locale files got *smaller* (217,363->217,236 and 293,055->292,377 bytes) and
the host had 1,325 GB free. Re-running the identical source succeeded, as did
the later rebuild. The vite step simply sits near the 4 GB heap cap and tips
over at random; two of three builds passed today.

If it recurs, retry first. A durable fix is raising the cap in the Dockerfile -
the host has ample RAM - but that is a deploy change, not a locale one.
