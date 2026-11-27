import uuid
from sqlalchemy import Column, Integer, String, Date, Time, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from .minirag_base import SQLAlchemyBase


class ExamEntry(SQLAlchemyBase):
    __tablename__ = "exam_entries"

    exam_id = Column(Integer, primary_key=True, autoincrement=True)

    exam_uuid = Column(
        UUID(as_uuid=True),
        default=uuid.uuid4,
        unique=True,
        nullable=False,
        index=True,
    )

    project_id = Column(
        Integer,
        ForeignKey("projects.project_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    subject = Column(String(255), nullable=False)
    exam_date = Column(Date, nullable=False)
    exam_time = Column(Time, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )