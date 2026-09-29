# Analyst Task Tracker

## Project overview

Django-приложение для управления задачами аналитиков.

## Working rules

- Вносить только изменения, относящиеся к текущей задаче.
- Не делать unrelated refactoring.
- Сохранять существующую модель permissions и access checks.
- Не менять существующее AJAX-поведение без прямого требования.
- Перед изменениями изучать текущую реализацию и тесты.
- Для новых функций добавлять или адаптировать тесты.
- После изменений запускать релевантные тесты приложения `tracker`.
- Если возможно, дополнительно запускать полный test suite.
- Не редактировать файлы внутри `sources/`: это справочные материалы проекта.

## Commands

- Relevant tests: `python manage.py test tracker --settings=config.settings_test --keepdb --noinput`
- Full test suite: `python manage.py test --settings=config.settings_test --keepdb --noinput`
- Production password hasher checks: `python manage.py test accounts.test_password_hashers --settings=config.settings_test --keepdb --noinput`
