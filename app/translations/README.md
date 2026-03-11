# Translations

Phase 1 initializes Flask-Babel with English and Spanish locale support.

Suggested commands (inside container):
- `pybabel extract -F babel.cfg -o messages.pot .`
- `pybabel init -i messages.pot -d app/translations -l en`
- `pybabel init -i messages.pot -d app/translations -l es`
- `pybabel compile -d app/translations`
