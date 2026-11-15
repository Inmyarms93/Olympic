SUBJECT_MAP = [
    ("информационная безопасность", "Информатика"),
    ("искусственный интеллект", "Информатика"),
    ("робототехника", "Информатика"),
    ("программирование", "Информатика"),
    ("информатика", "Информатика"),
    ("техника и техническое творчество", "Технология"),
    ("культура дома", "Технология"),
    ("технология", "Технология"),
    ("физическая культура", "Физическая культура"),
    ("искусство", "Искусство (МХК)"),
    ("мхк", "Искусство (МХК)"),
    ("русский", "Русский язык"),
    ("английский", "Английский язык"),
    ("немецкий", "Немецкий язык"),
    ("французский", "Французский язык"),
    ("испанский", "Испанский язык"),
    ("итальянский", "Итальянский язык"),
    ("китайский", "Китайский язык"),
    ("математика", "Математика"),
    ("физика", "Физика"),
    ("литература", "Литература"),
    ("биология", "Биология"),
    ("химия", "Химия"),
    ("география", "География"),
    ("история", "История"),
    ("обществознание", "Обществознание"),
    ("экономика", "Экономика"),
    ("право", "Право"),
    ("экология", "Экология"),
    ("астрономия", "Астрономия"),
    ("обзр", "ОБЗР"),
]

STATUS_PRIORITY = {"Победитель": 3, "Призер": 2, "Участник": 1}


def normalize_subject(raw: str) -> str:
    s = (raw or "").strip().lower()
    if s.startswith("всош по "):
        s = s[len("всош по "):]
    for key, name in SUBJECT_MAP:
        if key in s:
            return name
    return raw.strip() if raw else "Неизвестный предмет"


def status_priority(status: str | None) -> int:
    if not status:
        return 0
    return STATUS_PRIORITY.get(status.strip(), 0)


def is_winner_or_prize(status: str | None) -> bool:
    if not status:
        return False
    return status.strip() in ("Победитель", "Призер")


def parse_parallel(class_name: str) -> str | None:
    if not class_name:
        return None
    digits = ""
    for ch in class_name:
        if ch.isdigit():
            digits += ch
        else:
            break
    return digits or None


def parse_score(v):
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", "."))
    except (ValueError, TypeError):
        return None