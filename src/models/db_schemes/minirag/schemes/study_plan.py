import uuid
from sqlalchemy import Column, Integer, String, Date, Boolean, DateTime, ForeignKey, func, false
from sqlalchemy.dialects.postgresql import JSONB, UUID
from .minirag_base import SQLAlchemyBase


class StudyPlanRecord(SQLAlchemyBase):
    __tablename__ = "study_plans"

    plan_id = Column(Integer, primary_key=True, autoincrement=True)

    plan_uuid = Column(
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
        unique=True,
        index=True,
    )

    plan = Column(JSONB, nullable=False)
    preferences = Column(JSONB, nullable=False)
    note = Column(String(500), nullable=True)

    # True when the exam schedule changed after this plan was generated.
    is_stale = Column(Boolean, nullable=False, server_default=false())


    expires_on = Column(Date, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
