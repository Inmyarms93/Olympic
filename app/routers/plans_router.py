from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db
from ..auth import require_admin
from ..models import (
    Plan, Prospect, Student, Subject, Result, Stage,
    PlanTask, PlanCheckpoint, ImportBatch,
)

router = APIRouter()


def _resolve_version(db: Session, version_id: int | None) -> int | None:
    if version_id:
        return version_id
    latest = db.query(ImportBatch).order_by(ImportBatch.created_at.desc()).first()
    return latest.id if latest else None


def _serialize_plan(db: Session, plan: Plan) -> dict:
    prospect = db.get(Prospect, plan.prospect_id)
    if not prospect:
        raise HTTPException(404, "Перспектива не найдена")
    student = db.get(Student, prospect.student_id)
    subject = db.get(Subject, prospect.subject_id)

    stages = {s.code: s for s in db.query(Stage).all()}
    rs = (db.query(Result)
          .filter(Result.import_batch_id == plan.import_batch_id,
                  Result.student_id == student.id, Result.subject_id == subject.id)
          .all())
    by_stage = {r.stage_code: r for r in rs}
    history = []
    last_score = None
    for code in ("school", "municipal", "regional"):
        r = by_stage.get(code)
        risk = False
        if r and r.score is not None:
            if last_score is not None and r.score < last_score:
                risk = True
            last_score = r.score
        history.append({
            "stage": stages[code].name,
            "status": r.status if r else None,
            "score": r.score if r else None,
            "allowed": r.allowed if r else None,
            "participation": r.participation if r else None,
            "risk": risk,
        })

    cur = None
    for code in ("regional", "municipal", "school"):
        r = by_stage.get(code)
        if r and (r.status or r.score is not None):
            cur = {"stage": stages[code].name, "status": r.status, "score": r.score}
            break

    tasks = db.query(PlanTask).filter(PlanTask.plan_id == plan.id)\
        .order_by(PlanTask.due_date.is_(None), PlanTask.due_date).all()
    checkpoints = db.query(PlanCheckpoint).filter(PlanCheckpoint.plan_id == plan.id)\
        .order_by(PlanCheckpoint.due_date.is_(None), PlanCheckpoint.due_date).all()

    return {
        "id": plan.id,
        "version_id": plan.import_batch_id,
        "prospect_id": prospect.id,
        "student": {"full_name": student.full_name, "class": student.class_name},
        "subject": subject.name,
        "goal": plan.goal,
        "status": plan.status,
        "current": cur,
        "history": history,
        "tasks": [{
            "id": t.id, "task_type": t.task_type, "title": t.title,
            "description": t.description,
            "due_date": str(t.due_date) if t.due_date else None,
            "responsible_teacher": t.responsible_teacher,
            "is_done": t.is_done,
        } for t in tasks],
        "checkpoints": [{
            "id": c.id, "title": c.title,
            "due_date": str(c.due_date) if c.due_date else None,
            "is_passed": c.is_passed, "comment": c.comment,
        } for c in checkpoints],
    }


@router.get("/plans")
def list_plans(
    db: Session = Depends(get_db),
    version_id: int | None = Query(None),
    status: str | None = None,
    teacher: str | None = None,
    subject: str | None = None,
    class_name: str | None = None,
    q: str | None = None,
):
    vid = _resolve_version(db, version_id)
    if vid is None:
        return {"items": []}

    qy = (db.query(Plan, Prospect, Student, Subject)
          .join(Prospect, Prospect.id == Plan.prospect_id)
          .join(Student, Student.id == Prospect.student_id)
          .join(Subject, Subject.id == Prospect.subject_id)
          .filter(Plan.import_batch_id == vid))
    if status:
        qy = qy.filter(Plan.status == status)
    if subject:
        qy = qy.filter(Subject.name == subject)
    if class_name:
        qy = qy.filter(Student.class_name == class_name)
    if q:
        qy = qy.filter(Student.full_name.ilike(f"%{q}%"))
    if teacher:
        plan_ids = {pid for (pid,) in db.query(PlanTask.plan_id)
                    .filter(PlanTask.responsible_teacher == teacher).distinct().all()}
        qy = qy.filter(Plan.id.in_(plan_ids or [-1]))

    rows = qy.all()

    items = []
    for plan, prospect, student, subject_ in rows:
        tasks = db.query(PlanTask).filter(PlanTask.plan_id == plan.id).all()
        done = sum(1 for t in tasks if t.is_done)
        upcoming = [t.due_date for t in tasks if t.due_date and not t.is_done]
        next_due = min(upcoming).isoformat() if upcoming else None
        teachers = sorted({t.responsible_teacher for t in tasks if t.responsible_teacher})
        items.append({
            "id": plan.id,
            "student": {"full_name": student.full_name, "class": student.class_name},
            "subject": subject_.name,
            "goal": plan.goal,
            "status": plan.status,
            "tasks_done": done, "tasks_total": len(tasks),
            "next_due": next_due,
            "teachers": teachers,
        })
    items.sort(key=lambda x: (x["next_due"] or "9999", x["status"]))
    return {"items": items, "version_id": vid}


@router.get("/plans/{plan_id}")
def get_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = db.get(Plan, plan_id)
    if not plan:
        raise HTTPException(404, "План не найден")
    return _serialize_plan(db, plan)


class PlanCreateIn(BaseModel):
    prospect_id: int
    goal: str | None = None
    tasks: list[dict] = []
    checkpoints: list[dict] = []


@router.post("/plans", dependencies=[Depends(require_admin)])
def create_plan(data: PlanCreateIn, db: Session = Depends(get_db)):
    prospect = db.get(Prospect, data.prospect_id)
    if not prospect:
        raise HTTPException(404, "Перспектива не найдена")
    existing = db.query(Plan).filter(Plan.prospect_id == data.prospect_id).first()
    if existing:
        raise HTTPException(400, "План для этой пары уже существует")
    plan = Plan(
        import_batch_id=prospect.import_batch_id,
        prospect_id=data.prospect_id,
        goal=data.goal or "призёр регионального этапа",
        status="в работе",
    )
    db.add(plan)
    db.flush()
    for t in data.tasks:
        db.add(PlanTask(
            plan_id=plan.id, task_type=t.get("task_type"),
            title=t.get("title", ""), description=t.get("description"),
            due_date=_parse_date(t.get("due_date")),
            responsible_teacher=t.get("responsible_teacher"),
        ))
    for c in data.checkpoints:
        db.add(PlanCheckpoint(
            plan_id=plan.id, title=c.get("title", ""),
            due_date=_parse_date(c.get("due_date")),
            comment=c.get("comment"),
        ))
    prospect.manual_flag = prospect.manual_flag or "взят в план"
    db.commit()
    db.refresh(plan)
    return _serialize_plan(db, plan)


class PlanUpdateIn(BaseModel):
    status: str | None = None
    goal: str | None = None


@router.patch("/plans/{plan_id}", dependencies=[Depends(require_admin)])
def update_plan(plan_id: int, data: PlanUpdateIn, db: Session = Depends(get_db)):
    plan = db.get(Plan, plan_id)
    if not plan:
        raise HTTPException(404, "План не найден")
    if data.status:
        plan.status = data.status
    if data.goal:
        plan.goal = data.goal
    db.commit()
    return _serialize_plan(db, plan)


class TaskIn(BaseModel):
    task_type: str | None = None
    title: str
    description: str | None = None
    due_date: str | None = None
    responsible_teacher: str | None = None
    is_done: bool | None = None


@router.post("/plans/{plan_id}/tasks", dependencies=[Depends(require_admin)])
def add_task(plan_id: int, data: TaskIn, db: Session = Depends(get_db)):
    if not db.get(Plan, plan_id):
        raise HTTPException(404, "План не найден")
    t = PlanTask(plan_id=plan_id, task_type=data.task_type, title=data.title,
                 description=data.description, due_date=_parse_date(data.due_date),
                 responsible_teacher=data.responsible_teacher)
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"id": t.id}


@router.patch("/plans/{plan_id}/tasks/{task_id}", dependencies=[Depends(require_admin)])
def update_task(plan_id: int, task_id: int, data: TaskIn, db: Session = Depends(get_db)):
    t = db.get(PlanTask, task_id)
    if not t or t.plan_id != plan_id:
        raise HTTPException(404, "Задача не найдена")
    for f in ("task_type", "title", "description", "responsible_teacher"):
        v = getattr(data, f)
        if v is not None:
            setattr(t, f, v)
    if data.due_date is not None:
        t.due_date = _parse_date(data.due_date)
    if data.is_done is not None:
        t.is_done = data.is_done
        if data.is_done:
            t.done_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.delete("/plans/{plan_id}/tasks/{task_id}", dependencies=[Depends(require_admin)])
def delete_task(plan_id: int, task_id: int, db: Session = Depends(get_db)):
    t = db.get(PlanTask, task_id)
    if not t or t.plan_id != plan_id:
        raise HTTPException(404, "Задача не найдена")
    db.delete(t)
    db.commit()
    return {"ok": True}


class CheckpointIn(BaseModel):
    title: str
    due_date: str | None = None
    comment: str | None = None
    is_passed: bool | None = None


@router.post("/plans/{plan_id}/checkpoints", dependencies=[Depends(require_admin)])
def add_checkpoint(plan_id: int, data: CheckpointIn, db: Session = Depends(get_db)):
    if not db.get(Plan, plan_id):
        raise HTTPException(404, "План не найден")
    c = PlanCheckpoint(plan_id=plan_id, title=data.title,
                       due_date=_parse_date(data.due_date), comment=data.comment)
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"id": c.id}


@router.patch("/plans/{plan_id}/checkpoints/{cp_id}", dependencies=[Depends(require_admin)])
def update_checkpoint(plan_id: int, cp_id: int, data: CheckpointIn, db: Session = Depends(get_db)):
    c = db.get(PlanCheckpoint, cp_id)
    if not c or c.plan_id != plan_id:
        raise HTTPException(404, "Контрольная точка не найдена")
    if data.title is not None:
        c.title = data.title
    if data.due_date is not None:
        c.due_date = _parse_date(data.due_date)
    if data.comment is not None:
        c.comment = data.comment
    if data.is_passed is not None:
        c.is_passed = data.is_passed
        if data.is_passed:
            c.passed_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.delete("/plans/{plan_id}/checkpoints/{cp_id}", dependencies=[Depends(require_admin)])
def delete_checkpoint(plan_id: int, cp_id: int, db: Session = Depends(get_db)):
    c = db.get(PlanCheckpoint, cp_id)
    if not c or c.plan_id != plan_id:
        raise HTTPException(404, "Контрольная точка не найдена")
    db.delete(c)
    db.commit()
    return {"ok": True}


def _parse_date(v):
    if not v:
        return None
    if isinstance(v, str):
        return datetime.strptime(v, "%Y-%m-%d").date()
    return v