# Translations

IRONCore RepairPanel uses **Flask-Babel** for internationalization (i18n).

## Supported Languages

| Code | Language |
|------|----------|
| `en` | English (source/default) |
| `es` | Spanish |

## Directory Structure

```
app/translations/
├── en/LC_MESSAGES/
│   ├── messages.po   # English catalog (source — msgstr left empty)
│   └── messages.mo   # Compiled binary
├── es/LC_MESSAGES/
│   ├── messages.po   # Spanish translations
│   └── messages.mo   # Compiled binary
└── README.md
```

## How Locale Is Selected

1. **Session** — the language switcher (`/set-language/<locale>`) stores the choice in the session.
2. **User preference** — if the user is authenticated, `preferred_language` is used.
3. **Browser** — `Accept-Language` header, best-matched against `en` / `es`.
4. **Fallback** — English (`en`).

For customer-facing generated messages (emails, SMS bodies), the system uses the customer's `preferred_language` field via `flask_babel.force_locale()`.

## How to Update Translations

### 1. Extract new strings

```bash
pybabel extract -F babel.cfg -o messages.pot .
```

### 2. Update existing catalogs

```bash
pybabel update -i messages.pot -d app/translations
```

### 3. Edit the `.po` files

Open `app/translations/es/LC_MESSAGES/messages.po` and add Spanish translations for any new `msgid` entries (they will have empty `msgstr`).

### 4. Compile

```bash
pybabel compile -d app/translations
```

### 5. Restart the app

The compiled `.mo` files are read at startup.

## How to Add a New Language

```bash
pybabel init -i messages.pot -d app/translations -l <locale_code>
```

Then edit the new `.po` file, compile, and add the locale code to `SUPPORTED_LOCALES` in `.env`.

## Conventions

- **Python code**: use `from flask_babel import gettext as _` and wrap strings with `_("...")`.
- **Forms**: use `from flask_babel import lazy_gettext as _l` and wrap labels with `_l("...")`.
- **Templates**: use `{{ _("...") }}` in Jinja2.
- **Named parameters**: use `%(name)s` style — e.g. `_("Hello %(name)s", name=user.name)`.
- Do **not** translate brand names (IRONCore) or technical identifiers.
