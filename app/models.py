from datetime import datetime, date
from sqlalchemy import (
    String, Integer, Float, Boolean, ForeignKey, UniqueConstraint,
    DateTime, Date, Text,
)
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


def now():
    return datetime.utcnow()


class Student(Base):
    __tablename__ = "students"
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), index=True)
    class_name: Mapped[str] = mapped_column("class", String(50), index=True)
    parallel: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
    __table_args__ = (UniqueConstraint("full_name", "class", name="uq_student_name_class"),)


class Subject(Base):
    __tablename__ = "subjects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    raw_names: Mapped[str | None] = mapped_column(Text, nullable=True)


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    rows_count: Mapped[int] = mapped_column(Integer, default=0)


class RawResult(Base):
    __tablename__ = "raw_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    import_batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id"), index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    class_name: Mapped[str] = mapped_column("class", String(50))
    olympiad_raw: Mapped[str] = mapped_column(String(300))
    school_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    school_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    municipal_allowed: Mapped[str | None] = mapped_column(String(20), nullable=True)
    municipal_participation: Mapped[str | None] = mapped_column(String(50), nullable=True)
    municipal_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    municipal_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    regional_allowed: Mapped[str | None] = mapped_column(String(20), nullable=True)
    regional_participation: Mapped[str | None] = mapped_column(String(50), nullable=True)
    regional_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    regional_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    row_hash: Mapped[str] = mapped_column(String(64), index=True)


class Stage(Base):
    __tablename__ = "stages"
    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    order: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(50))


class Result(Base):
    __tablename__ = "results"
    id: Mapped[int] = mapped_column(primary_key=True)
    import_batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), index=True)
    stage_code: Mapped[str] = mapped_column(ForeignKey("stages.code"))
    allowed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    participation: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_row_id: Mapped[int | None] = mapped_column(ForeignKey("raw_results.id"), nullable=True)
    __table_args__ = (
        UniqueConstraint("import_batch_id", "student_id", "subject_id", "stage_code",
                         name="uq_result_version_pair_stage"),
    )


class Prospect(Base):
    __tablename__ = "prospects"
    id: Mapped[int] = mapped_column(primary_key=True)
    import_batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"))
    auto_qualified: Mapped[bool] = mapped_column(Boolean, default=False)
    manual_flag: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
    __table_args__ = (
        UniqueConstraint("import_batch_id", "student_id", "subject_id",
                         name="uq_prospect_version_pair"),
    )


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    import_batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id"), index=True)
    prospect_id: Mapped[int] = mapped_column(ForeignKey("prospects.id"), unique=True)
    goal: Mapped[str] = mapped_column(String(200), default="призёр регионального этапа")
    status: Mapped[str] = mapped_column(String(30), default="в работе")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class PlanTask(Base):
    __tablename__ = "plan_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), index=True)
    task_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    responsible_teacher: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_done: Mapped[bool] = mapped_column(Boolean, default=False)
    done_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class PlanCheckpoint(Base):
    __tablename__ = "plan_checkpoints"
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    passed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class DataAnomaly(Base):
    __tablename__ = "data_anomalies"
    id: Mapped[int] = mapped_column(primary_key=True)
    import_batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id"), index=True)
    anomaly_type: Mapped[str] = mapped_column(String(50))
    student_id: Mapped[int | None] = mapped_column(ForeignKey("students.id"), nullable=True)
    subject_id: Mapped[int | None] = mapped_column(ForeignKey("subjects.id"), nullable=True)
    stage_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source_row_id: Mapped[int | None] = mapped_column(ForeignKey("raw_results.id"), nullable=True)
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="открыта")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)