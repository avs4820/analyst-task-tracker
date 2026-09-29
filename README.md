# Analyst Task Tracker

Internal application for tracking analysts' tasks and weekly status updates.

## Technology

- Python
- Django
- PostgreSQL

## Local development

## Testing

Use the dedicated test settings for routine test runs. They use a fast
password hasher, while focused integration tests still exercise Django's
production password hasher.

```powershell
python manage.py test tracker --settings=config.settings_test --keepdb --noinput
python manage.py test --settings=config.settings_test --keepdb --noinput
```

The production password hasher checks are included in the full suite and can
also be run separately:

```powershell
python manage.py test accounts.test_password_hashers --settings=config.settings_test --keepdb --noinput
```
