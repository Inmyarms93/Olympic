from datetime import date, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import (
    Prospect, Plan, PlanTask, PlanCheckpoint, DataAnomaly,
    Student, Subject, ImportBatch,
)
from ..services.plan_status import compute_status

router = APIRouter()


def _resolve_version(db: Session, version_id: int | None) -> int | None:
    if version_id:
        return version_id
    latest = db.query(ImportBatch).order_by(ImportBatch.created_at.desc()).first()
    return latest.id if latest else None


@router.get("/kpi")
def kpi(version_id: int | None = Query(None), db: Session = Depends(get_db)):
    vid = _resolve_version(db, version_id)
    if vid is None:
        return {
            "version_id": None,
            "prospects_count": 0, "plans_in_work": 0, "goal_achieved": 0,
            "plans_overdue": 0,
            "plans_by_status": {}, "coverage_by_subject": [], "coverage_by_class": [],
            "upcoming": [], "open_anomalies": 0,
        }

    total_prospects = (db.query(func.count(Prospect.id))
                       .filter(Prospect.import_batch_id == vid)
                       .filter(or_(Prospect.auto_qualified == True, Prospect.manual_flag.isnot(None)))
                       .scalar() or 0)

    # --- статусы планов считаем через compute_status ---
    today = date.today()
    plans = db.query(Plan).filter(Plan.import_batch_id == vid).all()
    by_status: dict[str, int] = {}
    for p in plans:
        tasks = db.query(PlanTask).filter(PlanTask.plan_id == p.id).all()
        cps = db.query(PlanCheckpoint).filter(PlanCheckpoint.plan_id == p.id).all()
        s = compute_status(tasks, cps, today)
        by_status[s] = by_status.get(s, 0) + 1

    in_work = by_status.get("выполняется", 0)
    achieved = by_status.get("выполнен", 0)
    overdue = by_status.get("просрочен", 0)

    coverage_by_subject = [
        {"subject": s, "count": c}
        for s, c in db.query(Subject.name, func.count(Prospect.id))
                       .join(Subject, Subject.id == Prospect.subject_id)
                       .filter(Prospect.import_batch_id == vid)
                       .group_by(Subject.name).all()
    ]
    coverage_by_class = [
        {"class": st, "count": c}
        for st, c in db.query(Student.class_name, func.count(Prospect.id))
                         .join(Student, Student.id == Prospect.student_id)
                         .filter(Prospect.import_batch_id == vid)
                         .group_by(Student.class_name).all()
    ]

    horizon = today + timedelta(days=14)
    plan_ids = [p.id for p in plans]

    tasks = (db.query(PlanTask)
             .filter(PlanTask.plan_id.in_(plan_ids or [-1]),
                     PlanTask.is_done == False, PlanTask.due_date.isnot(None),
                     PlanTask.due_date <= horizon)
             .order_by(PlanTask.due_date).limit(20).all())
    checkpoints = (db.query(PlanCheckpoint)
                   .filter(PlanCheckpoint.plan_id.in_(plan_ids or [-1]),
                           PlanCheckpoint.is_passed == False,
                           PlanCheckpoint.due_date.isnot(None),
                           PlanCheckpoint.due_date <= horizon)
                   .order_by(PlanCheckpoint.due_date).limit(20).all())

    upcoming = []
    for t in tasks:
        upcoming.append({"kind": "task", "title": t.title, "due_date": str(t.due_date),
                         "teacher": t.responsible_teacher, "plan_id": t.plan_id})
    for c in checkpoints:
        upcoming.append({"kind": "checkpoint", "title": c.title, "due_date": str(c.due_date),
                         "teacher": None, "plan_id": c.plan_id})
    upcoming.sort(key=lambda x: x["due_date"])

    open_anomalies = (db.query(func.count(DataAnomaly.id))
                      .filter(DataAnomaly.import_batch_id == vid, DataAnomaly.status == "открыта")
                      .scalar() or 0)

    return {
        "version_id": vid,
        "prospects_count": total_prospects,
        "plans_in_work": in_work,
        "goal_achieved": achieved,
        "plans_overdue": overdue,
        "plans_by_status": by_status,
        "coverage_by_subject": coverage_by_subject,
        "coverage_by_class": coverage_by_class,
        "upcoming": upcoming,
        "open_anomalies": open_anomalies,
    }