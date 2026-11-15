from urllib.parse import quote
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session
from ..database import get_db
from ..auth import require_admin
from ..services.importer import import_workbook, build_template

router = APIRouter()


@router.get("/template")
def download_template():
    data = build_template()
    filename = "Статистика_участники_template.xlsx"
    ascii_name = "template.xlsx"
    content_disposition = (
        f"attachment; filename=\"{ascii_name}\"; "
        f"filename*=UTF-8''{quote(filename)}"
    )
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": content_disposition},
    )


@router.post("/import", dependencies=[Depends(require_admin)])
async def do_import(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    try:
        result = import_workbook(db, content, filename=file.filename)
    except Exception as e:
        db.rollback()
        raise HTTPException(400, f"Ошибка импорта: {e}")
    return result