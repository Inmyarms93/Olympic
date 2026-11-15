from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from ..database import get_db
from ..auth import require_admin
from ..models import (
    ImportBatch, Prospect, Plan, Result, RawResult, DataAnomaly,
    PlanTask, PlanCheckpoint,
)

router = APIRouter()


@router.get("/versions")
def list_versions(db: Session = Depends(get_db)):
    batches = db.query(ImportBatch).order_by(ImportBatch.created_at.desc()).all()
    items = []
    for b in batches:
        items.append({
            "id": b.id,
            "created_at": b.created_at.isoformat() if b.created_at else None,
            "filename": b.filename,
            "rows_count": b.rows_count,
            "prospects_count": db.query(func.count(Prospect.id))
                .filter(Prospect.import_batch_id == b.id).scalar() or 0,
            "plans_count": db.query(func.count(Plan.id))
                .filter(Plan.import_batch_id == b.id).scalar() or 0,
        })
    return {
        "items": items,
        "latest_id": items[0]["id"] if items else None,
    }


@router.delete("/versions/{version_id}", dependencies=[Depends(require_admin)])
def delete_version(version_id: int, db: Session = Depends(get_db)):
    batch = db.get(ImportBatch, version_id)
    if not batch:
        raise HTTPException(404, "Версия не найдена")

    plan_ids = [pid for (pid,) in db.query(Plan.id)
                .filter(Plan.import_batch_id == version_id).all()]
    if plan_ids:
        db.query(PlanTask).filter(PlanTask.plan_id.in_(plan_ids)).delete(synchronize_session=False)
        db.query(PlanCheckpoint).filter(PlanCheckpoint.plan_id.in_(plan_ids)).delete(synchronize_session=False)
        db.query(Plan).filter(Plan.id.in_(plan_ids)).delete(synchronize_session=False)

    db.query(DataAnomaly).filter(DataAnomaly.import_batch_id == version_id).delete(synchronize_session=False)
    db.query(Prospect).filter(Prospect.import_batch_id == version_id).delete(synchronize_session=False)
    db.query(Result).filter(Result.import_batch_id == version_id).delete(synchronize_session=False)
    db.query(RawResult).filter(RawResult.import_batch_id == version_id).delete(synchronize_session=False)
    db.delete(batch)
    db.commit()
    return {"ok": True, "deleted_version_id": version_id}