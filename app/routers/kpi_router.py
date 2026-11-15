from datetime import date, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Prospect, Plan, PlanTask, PlanCheckpoint, DataAnomaly, Student, Subject

router = APIRouter()


@router.get("/kpi")
def kpi(db: Session = Depends(get_db)):
    total_prospects = (db.query(func.count(Prospect.id))
                       .filter(or_(Prospect.auto_qualified == True, Prospect.manual_flag.isnot(None)))
                       .scalar() or 0)
    in_work = db.query(func.count(Plan.id)).filter(Plan.status == "в работе").scalar() or 0
    achieved = db.query(func.count(Plan.id)).filter(Plan.status == "цель достигнута").scalar() or 0

    by_status_rows = db.query(Plan.status, func.count(Plan.id)).group_by(Plan.status).all()
    by_status = {s: c for s, c in by_status_rows}

    coverage_by_subject = [
        {"subject": s, "count": c}
        for s, c in db.query(Subject.name, func.count(Prospect.id))
                       .join(Subject, Subject.id == Prospect.subject_id)
                       .group_by(Subject.name).all()
    ]
    coverage_by_class = [
        {"class": st, "count": c}
        for st, c in db.query(Student.class_name, func.count(Prospect.id))
                         .join(Student, Student.id == Prospect.student_id)
                         .group_by(Student.class_name).all()
    ]

    today = date.today()
    horizon = today + timedelta(days=14)

    tasks = (db.query(PlanTask)
             .filter(PlanTask.is_done == False, PlanTask.due_date.isnot(None),
                     PlanTask.due_date <= horizon)
             .order_by(PlanTask.due_date).limit(20).all())
    checkpoints = (db.query(PlanCheckpoint)
                   .filter(PlanCheckpoint.is_passed == False, PlanCheckpoint.due_date.isnot(None),
                           PlanCheckpoint.due_date <= horizon)
                   .order_by(PlanCheckpoint.due_date).limit(20).all())

    upcoming = []
    for t in tasks:
        upcoming.append({
            "kind": "task", "title": t.title, "due_date": str(t.due_date),
            "teacher": t.responsible_teacher, "plan_id": t.plan_id,
        })
    for c in checkpoints:
        upcoming.append({
            "kind": "checkpoint", "title": c.title, "due_date": str(c.due_date),
            "teacher": None, "plan_id": c.plan_id,
        })
    upcoming.sort(key=lambda x: x["due_date"])

    open_anomalies = db.query(func.count(DataAnomaly.id)).filter(
        DataAnomaly.status == "открыта").scalar() or 0

    return {
        "prospects_count": total_prospects,
        "plans_in_work": in_work,
        "goal_achieved": achieved,
        "plans_by_status": by_status,
        "coverage_by_subject": coverage_by_subject,
        "coverage_by_class": coverage_by_class,
        "upcoming": upcoming,
        "open_anomalies": open_anomalies,
    }