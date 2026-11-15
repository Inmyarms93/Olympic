import hashlib
import json
from datetime import datetime
from io import BytesIO

from openpyxl import Workbook, load_workbook
from sqlalchemy.orm import Session

from ..models import (
    Student, Subject, RawResult, Result, ImportBatch, Stage,
    Prospect, DataAnomaly, Plan,
)
from .normalize import (
    normalize_subject, is_winner_or_prize, parse_score, parse_parallel,
    status_priority,
)

HEADERS = [
    "Название олимпиады",
    "ФИО",
    "Класс обучения школьного этапа",
    "Статус школьного этапа",
    "Балл школьного этапа",
    "Есть на муниципальном этапе",
    "Муниципальный этап, участие",
    "Статус муниципального этапа",
    "Балл муниципального этапа",
    "Есть на региональном этапе",
    "Региональный этап, участие",
    "Статус регионального этапа",
    "Балл регионального этапа",
]


def build_template() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Статистика_ОО_МСУ"
    ws.append(HEADERS)
    rows = [
        ["ВсОШ по математике", "Иванов Иван Иванович", "10-А", "Участник", 10, "Нет", "", "", "", "Нет", "", "", ""],
        ["ВсОШ по литературе", "Петрова Анна Сергеевна", "10-А", "Победитель", 42, "Есть", "Участвовал", "Победитель", 58, "Есть", "Участвовал", "Призер", 71.05],
        ["ВсОШ по русскому языку", "Петрова Анна Сергеевна", "10-А", "Призер", 94, "Есть", "Участвовал", "Участник", 43.5, "Есть", "Участвовал", "Участник", 11],
        ["ВсОШ по информатике \"Робототехника\"", "Сидоров Петр Алексеевич", "10-А", "Призер", 70, "Есть", "Участвовал", "Участник", 3, "Нет", "", "", ""],
        ["ВсОШ по технологии «Культура дома»", "Кузнецова Мария Ивановна", "11-А", "Победитель", 76, "Есть", "Участвовал", "Призер", 130.5, "Нет", "", "", ""],
    ]
    for r in rows:
        ws.append(r)

    instr = wb.create_sheet("Инструкция")
    for line in [
        "Колонки: см. лист «Статистика_ОО_МСУ».",
        "Ключ ученика — пара «ФИО + класс обучения школьного этапа».",
        "Статусы: Победитель / Призер / Участник (пусто — если нет).",
        "«Есть на … этапе»: Есть / Нет (пусто — если неизвестно).",
        "«… участие»: Участвовал / Отсутствовал (пусто).",
        "Подтипы Информатики и Технологии сворачиваются в один предмет при импорте.",
        "Каждая загрузка файла создаёт новую версию данных.",
    ]:
        instr.append([line])

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _row_hash(full_name, class_name, olympiad_raw, *vals) -> str:
    raw = "|".join([str(x or "") for x in (full_name, class_name, olympiad_raw, *vals)])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _get_or_create_student(db: Session, full_name: str, class_name: str) -> Student:
    st = (db.query(Student)
          .filter(Student.full_name == full_name, Student.class_name == class_name)
          .first())
    if st is None:
        st = Student(full_name=full_name, class_name=class_name,
                     parallel=parse_parallel(class_name))
        db.add(st)
        db.flush()
    return st


def _get_or_create_subject(db: Session, raw_name: str) -> Subject:
    name = normalize_subject(raw_name)
    subj = db.query(Subject).filter(Subject.name == name).first()
    if subj is None:
        subj = Subject(name=name, raw_names=json.dumps([raw_name], ensure_ascii=False))
        db.add(subj)
        db.flush()
    else:
        try:
            raws = json.loads(subj.raw_names or "[]")
        except Exception:
            raws = []
        if raw_name not in raws:
            raws.append(raw_name)
            subj.raw_names = json.dumps(raws, ensure_ascii=False)
    return subj


STAGE_FIELDS = {
    "school": ("school_status", "school_score", None, None),
    "municipal": ("municipal_status", "municipal_score", "municipal_participation", "municipal_allowed"),
    "regional": ("regional_status", "regional_score", "regional_participation", "regional_allowed"),
}


def import_workbook(db: Session, file_bytes: bytes, filename: str | None = None) -> dict:
    wb = load_workbook(filename=BytesIO(file_bytes), data_only=True)
    ws = wb["Статистика_ОО_МСУ"] if "Статистика_ОО_МСУ" in wb.sheetnames else wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ValueError("Файл пуст")

    header = [str(c or "").strip() for c in rows[0]]
    for h in HEADERS:
        if h not in header:
            raise ValueError(f"В шапке отсутствует колонка: {h}")

    idx = {h: header.index(h) for h in HEADERS}

    batch = ImportBatch(filename=filename, rows_count=0)
    db.add(batch)
    db.flush()

    seen_hashes = set()
    duplicate_count = 0

    for r in rows[1:]:
        if not any(v is not None and str(v).strip() != "" for v in r):
            continue
        full_name = str(r[idx["ФИО"]] or "").strip()
        class_name = str(r[idx["Класс обучения школьного этапа"]] or "").strip()
        olympiad_raw = str(r[idx["Название олимпиады"]] or "").strip()
        if not full_name or not class_name or not olympiad_raw:
            continue

        school_status = (str(r[idx["Статус школьного этапа"]] or "").strip() or None)
        school_score = parse_score(r[idx["Балл школьного этапа"]])
        m_allowed = (str(r[idx["Есть на муниципальном этапе"]] or "").strip() or None)
        m_part = (str(r[idx["Муниципальный этап, участие"]] or "").strip() or None)
        m_status = (str(r[idx["Статус муниципального этапа"]] or "").strip() or None)
        m_score = parse_score(r[idx["Балл муниципального этапа"]])
        r_allowed = (str(r[idx["Есть на региональном этапе"]] or "").strip() or None)
        r_part = (str(r[idx["Региональный этап, участие"]] or "").strip() or None)
        r_status = (str(r[idx["Статус регионального этапа"]] or "").strip() or None)
        r_score = parse_score(r[idx["Балл регионального этапа"]])

        rh = _row_hash(full_name, class_name, olympiad_raw,
                       school_status, school_score, m_allowed, m_part, m_status, m_score,
                       r_allowed, r_part, r_status, r_score)
        if rh in seen_hashes:
            duplicate_count += 1
            continue
        seen_hashes.add(rh)

        db.add(RawResult(
            import_batch_id=batch.id,
            full_name=full_name, class_name=class_name, olympiad_raw=olympiad_raw,
            school_status=school_status, school_score=school_score,
            municipal_allowed=m_allowed, municipal_participation=m_part,
            municipal_status=m_status, municipal_score=m_score,
            regional_allowed=r_allowed, regional_participation=r_part,
            regional_status=r_status, regional_score=r_score,
            row_hash=rh,
        ))
        batch.rows_count += 1

        _get_or_create_student(db, full_name, class_name)
        _get_or_create_subject(db, olympiad_raw)

    db.flush()
    _rebuild_results_for_batch(db, batch.id)
    _rebuild_prospects_for_batch(db, batch.id)
    _rebuild_anomalies_for_batch(db, batch.id)
    db.commit()

    return {
        "version_id": batch.id,
        "imported": batch.rows_count,
        "duplicates_skipped": duplicate_count,
    }


def _rebuild_results_for_batch(db: Session, batch_id: int):
    db.query(Result).filter(Result.import_batch_id == batch_id).delete()
    db.flush()

    students = {(s.full_name, s.class_name): s.id for s in db.query(Student).all()}
    subjects = {s.name: s.id for s in db.query(Subject).all()}

    grouped: dict[tuple[int, int, str], dict] = {}

    for raw in db.query(RawResult).filter(RawResult.import_batch_id == batch_id).all():
        sid = students.get((raw.full_name, raw.class_name))
        subj_id = subjects.get(normalize_subject(raw.olympiad_raw))
        if sid is None or subj_id is None:
            continue

        for stage, fields in STAGE_FIELDS.items():
            status_field, score_field, part_field, allowed_field = fields
            status = getattr(raw, status_field)
            score = getattr(raw, score_field)
            part = getattr(raw, part_field) if part_field else None
            allowed_str = getattr(raw, allowed_field) if allowed_field else None

            if not (status or score is not None or part or allowed_str):
                continue

            if allowed_str == "Есть":
                allowed_bool: bool | None = True
            elif allowed_str == "Нет":
                allowed_bool = False
            else:
                allowed_bool = None

            candidate = {
                "status": status, "score": score, "participation": part,
                "allowed": allowed_bool, "source_row_id": raw.id,
            }
            gkey = (sid, subj_id, stage)
            prev = grouped.get(gkey)
            if prev is None or _better(candidate, prev):
                grouped[gkey] = candidate

    for (sid, subj_id, stage), c in grouped.items():
        db.add(Result(
            import_batch_id=batch_id,
            student_id=sid, subject_id=subj_id, stage_code=stage,
            allowed=c["allowed"], participation=c["participation"],
            status=c["status"], score=c["score"],
            source_row_id=c["source_row_id"],
        ))
    db.flush()


def _better(a: dict, b: dict) -> bool:
    sa = a["score"] if a["score"] is not None else -1
    sb = b["score"] if b["score"] is not None else -1
    if sa != sb:
        return sa > sb
    return status_priority(a["status"]) > status_priority(b["status"])


def _rebuild_prospects_for_batch(db: Session, batch_id: int):
    qualified: set[tuple[int, int]] = set()
    for r in db.query(Result).filter(
            Result.stage_code == "municipal",
            Result.import_batch_id == batch_id).all():
        if is_winner_or_prize(r.status):
            qualified.add((r.student_id, r.subject_id))

    existing = {(p.student_id, p.subject_id): p
                for p in db.query(Prospect).filter(Prospect.import_batch_id == batch_id).all()}

    for key in qualified:
        p = existing.get(key)
        if p is None:
            db.add(Prospect(
                import_batch_id=batch_id,
                student_id=key[0], subject_id=key[1],
                auto_qualified=True, manual_flag="взят в план",
            ))
        else:
            p.auto_qualified = True

    for key, p in existing.items():
        if key in qualified:
            continue
        p.auto_qualified = False
        has_plan = db.query(Plan).filter(Plan.prospect_id == p.id).first() is not None
        if not has_plan and not p.manual_flag:
            db.delete(p)

    db.flush()


def _rebuild_anomalies_for_batch(db: Session, batch_id: int):
    db.query(DataAnomaly).filter(DataAnomaly.import_batch_id == batch_id).delete()
    db.flush()

    students = {(s.full_name, s.class_name): s.id for s in db.query(Student).all()}
    subjects = {s.name: s.id for s in db.query(Subject).all()}

    for raw in db.query(RawResult).filter(RawResult.import_batch_id == batch_id).all():
        sid = students.get((raw.full_name, raw.class_name))
        subj_id = subjects.get(normalize_subject(raw.olympiad_raw))

        for stage, fields in STAGE_FIELDS.items():
            status_field, score_field, part_field, allowed_field = fields
            status = getattr(raw, status_field)
            score = getattr(raw, score_field)
            part = getattr(raw, part_field) if part_field else None
            allowed_str = getattr(raw, allowed_field) if allowed_field else None

            if allowed_str == "Есть" and (not part or part == "Отсутствовал"):
                db.add(DataAnomaly(
                    import_batch_id=batch_id,
                    anomaly_type="allowed_participation_mismatch",
                    student_id=sid, subject_id=subj_id, stage_code=stage,
                    source_row_id=raw.id,
                    description=f"«Есть на {stage} этапе», но участие: {part or 'пусто'}",
                ))
            if status and score is None:
                db.add(DataAnomaly(
                    import_batch_id=batch_id,
                    anomaly_type="status_score_missing",
                    student_id=sid, subject_id=subj_id, stage_code=stage,
                    source_row_id=raw.id,
                    description=f"Статус «{status}» на {stage} этапе, но балл пуст",
                ))
    db.flush()