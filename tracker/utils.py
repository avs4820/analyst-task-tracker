from datetime import date, timedelta


def get_week_start(target_date: date) -> date:
    """
    Возвращает понедельник недели, к которой относится указанная дата.
    """
    return target_date - timedelta(days=target_date.weekday())