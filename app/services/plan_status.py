from datetime import date


def compute_status(tasks: list, checkpoints: list, today: date | None = None) -> str:
    """
    Возвращает: «выполнен» | «просрочен» | «выполняется».

    Приоритеты:
    1. Есть невыполненная задача/точка с дедлайном в прошлом → «просрочен»
    2. Все задачи и точки выполнены (и есть хоть что-то) → «выполнен»
    3. Иначе → «выполняется»
    """
    today = today or date.today()

    for t in tasks:
        if not t.is_done and t.due_date and t.due_date < today:
            return "просрочен"
    for c in checkpoints:
        if not c.is_passed and c.due_date and c.due_date < today:
            return "просрочен"

    if tasks or checkpoints:
        if all(t.is_done for t in tasks) and all(c.is_passed for c in checkpoints):
            return "выполнен"

    return "выполняется"