UI_THEME_SESSION_KEY = "ui_theme"
UI_THEMES = {"light", "dark"}


def ui_theme(request):
    theme = request.session.get(UI_THEME_SESSION_KEY, "light")

    if theme not in UI_THEMES:
        theme = "light"

    return {
        "ui_theme": theme,
        "alternate_ui_theme": "light" if theme == "dark" else "dark",
        "alternate_ui_theme_label": (
            "Светлая тема" if theme == "dark" else "Тёмная тема"
        ),
    }
