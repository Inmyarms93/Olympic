from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db
from ..auth import require_admin
from ..models import Result, Student, Subject, Stage, ImportBatch
from ..services.importer import (
    _rebuild_prospects_for_batch, _rebuild_anomalies_for_batch,
)

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