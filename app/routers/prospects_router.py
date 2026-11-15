from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db
from ..auth import require_admin
from ..models import (
    Prospect, Student, Subject, Result, Plan, Stage, ImportBatch,
)

router = APIRouter()


def _resolve_version(db: Session, version_id: int | None) -> int | None:
    if version_id:
        return version_id
    latest = db.query(ImportBatch).order_by(ImportBatch.created_at.desc()).first()
    return latest.id if latest else None


@router.get("/prospects")
def list_prospects(
    db: Session = Depends(get_db),
    version_id: int | None = Query(None),
    class_name: str | None = Query(None),
    subject: str | None = Query(None),
    source: str = Query("all"),
    flag: str | None = Query(None),
    has_plan: str | None = Query(None),
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(200, ge=1, le=500),
):
    vid = _resolve_version(db, version_id)
    if vid is None:
        return {"total": 0, "items": []}

    qy = (db.query(Prospect, Student, Subject)
          .join(Student, Student.id == Prospect.student_id)
          .join(Subject, Subject.id == Prospect.subject_id)
          .filter(Prospect.import_batch_id == vid))

    if source == "auto":
        qy = qy.filter(Prospect.auto_qualified == True)
    elif source == "manual":
        qy = qy.filter(Prospect.manual_flag.isnot(None))
    if flag:
        qy = qy.filter(Prospect.manual_flag == flag)
    if class_name:
        qy = qy.filter(Student.class_name == class_name)
    if subject:
        qy = qy.filter(Subject.name == subject)
    if q:
        qy = qy.filter(Student.full_name.ilike(f"%{q}%"))
    if has_plan == "yes":
        qy = qy.filter(Prospect.id.in_(db.query(Plan.prospect_id)))
    elif has_plan == "no":
        qy = qy.filter(~Prospect.id.in_(db.query(Plan.prospect_id)))

    total = qy.count()
    rows = (qy.order_by(Prospect.auto_qualified.desc(), Student.full_name)
              .offset((page - 1) * limit).limit(limit).all())

    stages = {s.code: s for s in db.query(Stage).all()}

    result = []
    for p, st, subj in rows:
        rs = (db.query(Result)
              .filter(Result.import_batch_id == vid,
                      Result.student_id == st.id, Result.subject_id == subj.id)
              .all())
        by_stage = {r.stage_code: r for r in rs}
        cur_stage_code = None
        for code in ("regional", "municipal", "school"):
            if code in by_stage and (by_stage[code].status or by_stage[code].score is not None):
                cur_stage_code = code
                break
        cur = by_stage.get(cur_stage_code) if cur_stage_code else None
        plan = db.query(Plan).filter(Plan.prospect_id == p.id).first()

        result.append({
            "prospect_id": p.id,
            "student": {"full_name": st.full_name, "class": st.class_name},
            "subject": subj.name,
            "auto_qualified": p.auto_qualified,
            "manual_flag": p.manual_flag,
            "current": {
                "stage": stages[cur_stage_code].name if cur_stage_code else None,
                "status": cur.status if cur else None,
                "score": cur.score if cur else None,
            },
            "plan": {"id": plan.id, "status": plan.status} if plan else None,
        })
    return {"total": total, "items": result, "version_id": vid}


class BulkFlagIn(BaseModel):
    prospect_ids: list[int]
    flag: str | None


@router.post("/prospects/bulk-flag", dependencies=[Depends(require_admin)])
def bulk_flag(data: BulkFlagIn, db: Session = Depends(get_db)):
    for pid in data.prospect_ids:
        p = db.get(Prospect, pid)
        if p:
            p.manual_flag = data.flag
    db.commit()
    return {"updated": len(data.prospect_ids)}


@router.get("/filters")
def filters(db: Session = Depends(get_db)):
    classes = sorted({c for (c,) in db.query(Student.class_name).distinct().all()})
    subjects = sorted({s for (s,) in db.query(Subject.name).distinct().all()})
    return {"classes": classes, "subjects": subjects}