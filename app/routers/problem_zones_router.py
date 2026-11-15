from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db
from ..auth import require_admin
from ..models import (
    Prospect, Student, Subject, Result, Plan, Stage, DataAnomaly, ImportBatch,
)

router = APIRouter()


def _resolve_version(db: Session, version_id: int | None) -> int | None:
    if version_id:
        return version_id
    latest = db.query(ImportBatch).order_by(ImportBatch.created_at.desc()).first()
    return latest.id if latest else None


@router.get("/problem-zones/admitted-not-in-plan")
def admitted_not_in_plan(
    db: Session = Depends(get_db),
    version_id: int | None = Query(None),
):
    vid = _resolve_version(db, version_id)
    if vid is None:
        return {"items": []}

    stages = {s.code: s for s in db.query(Stage).all()}
    rows = (db.query(Result, Student, Subject)
            .join(Student, Student.id == Result.student_id)
            .join(Subject, Subject.id == Result.subject_id)
            .filter(Result.import_batch_id == vid,
                    Result.allowed == True,
                    Result.stage_code.in_(("municipal", "regional")))
            .all())

    out = []
    for r, st, subj in rows:
        prospect = (db.query(Prospect)
                    .filter(Prospect.import_batch_id == vid,
                            Prospect.student_id == st.id,
                            Prospect.subject_id == subj.id)
                    .first())
        has_plan = prospect and db.query(Plan).filter(Plan.prospect_id == prospect.id).first()
        if has_plan:
            continue
        out.append({
            "student": {"full_name": st.full_name, "class": st.class_name},
            "subject": subj.name,
            "stage": stages[r.stage_code].name,
            "stage_order": stages[r.stage_code].order,
            "status": r.status, "score": r.score,
            "prospect_id": prospect.id if prospect else None,
        })
    out.sort(key=lambda x: (-x["stage_order"], x["student"]["class"], x["student"]["full_name"]))
    return {"items": out, "version_id": vid}


@router.get("/anomalies")
def list_anomalies(
    db: Session = Depends(get_db),
    version_id: int | None = Query(None),
    status: str | None = None,
):
    vid = _resolve_version(db, version_id)
    if vid is None:
        return {"items": [], "count": 0}

    qy = db.query(DataAnomaly).filter(DataAnomaly.import_batch_id == vid)
    qy = qy.filter(DataAnomaly.status == (status or "открыта"))
    rows = qy.order_by(DataAnomaly.created_at.desc()).limit(500).all()

    students = {s.id: s for s in db.query(Student).all()}
    subjects = {s.id: s for s in db.query(Subject).all()}
    stages = {s.code: s for s in db.query(Stage).all()}

    return {
        "items": [{
            "id": a.id,
            "anomaly_type": a.anomaly_type,
            "student": ({"full_name": students[a.student_id].full_name,
                         "class": students[a.student_id].class_name}
                        if a.student_id in students else None),
            "subject": subjects[a.subject_id].name if a.subject_id in subjects else None,
            "stage": stages[a.stage_code].name if a.stage_code in stages else None,
            "description": a.description,
            "status": a.status,
        } for a in rows],
        "count": len(rows),
        "version_id": vid,
    }


class BulkAnomalyUpdateIn(BaseModel):
    anomaly_ids: list[int]
    status: str


@router.post("/anomalies/bulk-update", dependencies=[Depends(require_admin)])
def bulk_update_anomalies(data: BulkAnomalyUpdateIn, db: Session = Depends(get_db)):
    for aid in data.anomaly_ids:
        a = db.get(DataAnomaly, aid)
        if a:
            a.status = data.status
    db.commit()
    return {"updated": len(data.anomaly_ids)}