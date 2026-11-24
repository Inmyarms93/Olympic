from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db
from ..auth import require_admin
from ..models import (
    Result, Student, Subject, Stage, ImportBatch,
    Prospect, Plan, PlanTask, PlanCheckpoint
)
from ..services.importer import (
    _rebuild_prospects_for_batch, _rebuild_anomalies_for_batch,
)
from ..services.normalize import parse_parallel, normalize_subject

router = APIRouter()


def _resolve_version(db: Session, version_id: int | None) -> int | None:
    if version_id:
        return version_id
    latest = db.query(ImportBatch).order_by(ImportBatch.created_at.desc()).first()
    return latest.id if latest else None


@router.get("/results")
def list_results(
        db: Session = Depends(get_db),
        version_id: int | None = Query(None),
        class_name: str | None = Query(None),
        subject: str | None = Query(None),
        stage_code: str | None = Query(None),
        q: str | None = Query(None),
        page: int = Query(1, ge=1),
        limit: int = Query(100, ge=1, le=500),
):
    vid = _resolve_version(db, version_id)
    if vid is None:
        return {"total": 0, "items": [], "version_id": None}

    qy = (db.query(Result, Student, Subject, Stage)
          .join(Student, Student.id == Result.student_id)
          .join(Subject, Subject.id == Result.subject_id)
          .join(Stage, Stage.code == Result.stage_code)
          .filter(Result.import_batch_id == vid))

    if class_name:
        qy = qy.filter(Student.class_name == class_name)
    if subject:
        qy = qy.filter(Subject.name == subject)
    if stage_code:
        qy = qy.filter(Result.stage_code == stage_code)
    if q:
        qy = qy.filter(Student.full_name.ilike(f"%{q}%"))

    total = qy.count()
    rows = (qy.order_by(Student.full_name, Subject.name, Stage.order)
            .offset((page - 1) * limit).limit(limit).all())

    items = []
    for r, st, subj, stage in rows:
        items.append({
            "id": r.id,
            "student": {"full_name": st.full_name, "class": st.class_name},
            "subject": subj.name,
            "stage": {"code": stage.code, "name": stage.name},
            "allowed": r.allowed,
            "participation": r.participation,
            "status": r.status,
            "score": r.score,
        })
    return {"total": total, "items": items, "version_id": vid}


class ResultCreateIn(BaseModel):
    version_id: int
    full_name: str
    class_name: str
    subject_name: str
    stage_code: str
    allowed: bool | None = None
    participation: str | None = None
    status: str | None = None
    score: float | None = None


@router.post("/results", dependencies=[Depends(require_admin)])
def create_result(data: ResultCreateIn, db: Session = Depends(get_db)):
    # 1. Найти или создать ученика
    student = db.query(Student).filter(
        Student.full_name == data.full_name,
        Student.class_name == data.class_name
    ).first()
    if not student:
        student = Student(
            full_name=data.full_name,
            class_name=data.class_name,
            parallel=parse_parallel(data.class_name)
        )
        db.add(student)
        db.flush()

    # 2. Найти или создать предмет (используем нормализацию)
    norm_name = normalize_subject(data.subject_name)
    subject = db.query(Subject).filter(Subject.name == norm_name).first()
    if not subject:
        subject = Subject(name=norm_name)
        db.add(subject)
        db.flush()

    # 3. Проверить на дубликат
    existing = db.query(Result).filter(
        Result.import_batch_id == data.version_id,
        Result.student_id == student.id,
        Result.subject_id == subject.id,
        Result.stage_code == data.stage_code
    ).first()
    if existing:
        raise HTTPException(400, "Результат для этого ученика, предмета и этапа уже существует в этой версии")

    # 4. Создать результат
    r = Result(
        import_batch_id=data.version_id,
        student_id=student.id,
        subject_id=subject.id,
        stage_code=data.stage_code,
        allowed=data.allowed,
        participation=data.participation,
        status=data.status,
        score=data.score
    )
    db.add(r)
    db.flush()

    # 5. Пересчитать бизнес-логику
    _rebuild_prospects_for_batch(db, data.version_id)
    _rebuild_anomalies_for_batch(db, data.version_id)
    db.commit()

    return {"id": r.id}


class ResultPatchIn(BaseModel):
    allowed: bool | None = None
    participation: str | None = None
    status: str | None = None
    score: float | None = None


@router.patch("/results/{result_id}", dependencies=[Depends(require_admin)])
def update_result(result_id: int, data: ResultPatchIn, db: Session = Depends(get_db)):
    r = db.get(Result, result_id)
    if not r:
        raise HTTPException(404, "Результат не найден")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(r, field, value)

    db.flush()
    _rebuild_prospects_for_batch(db, r.import_batch_id)
    _rebuild_anomalies_for_batch(db, r.import_batch_id)
    db.commit()

    st = db.get(Student, r.student_id)
    subj = db.get(Subject, r.subject_id)
    stage = db.get(Stage, r.stage_code)
    return {
        "id": r.id,
        "student": {"full_name": st.full_name, "class": st.class_name},
        "subject": subj.name,
        "stage": {"code": stage.code, "name": stage.name},
        "allowed": r.allowed,
        "participation": r.participation,
        "status": r.status,
        "score": r.score,
    }


@router.delete("/results/{result_id}", dependencies=[Depends(require_admin)])
def delete_result(result_id: int, db: Session = Depends(get_db)):
    r = db.get(Result, result_id)
    if not r:
        raise HTTPException(404, "Результат не найден")

    # Каскадное удаление плана (если он привязан к этой паре ученик+предмет)
    prospect = db.query(Prospect).filter(
        Prospect.import_batch_id == r.import_batch_id,
        Prospect.student_id == r.student_id,
        Prospect.subject_id == r.subject_id
    ).first()

    if prospect:
        plan = db.query(Plan).filter(Plan.prospect_id == prospect.id).first()
        if plan:
            db.query(PlanTask).filter(PlanTask.plan_id == plan.id).delete()
            db.query(PlanCheckpoint).filter(PlanCheckpoint.plan_id == plan.id).delete()
            db.delete(plan)
        db.delete(prospect)

    batch_id = r.import_batch_id
    db.delete(r)
    db.flush()

    # Пересчитываем
    _rebuild_prospects_for_batch(db, batch_id)
    _rebuild_anomalies_for_batch(db, batch_id)
    db.commit()

    return {"ok": True}