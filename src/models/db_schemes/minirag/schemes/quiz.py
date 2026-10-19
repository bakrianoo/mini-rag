import uuid
from sqlalchemy import Column, Integer, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from .minirag_base import SQLAlchemyBase


class Quiz(SQLAlchemyBase):
    __tablename__ = "quizzes"

    quiz_id = Column(Integer, primary_key=True, autoincrement=True)

    quiz_uuid = Column(
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

    title = Column(String(255), nullable=True)

    status = Column(
        String(30),
        nullable=False,
        server_default="draft",
        index=True,
    )

    questions = Column(JSONB, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationship
    project = relationship("Project", back_populates="quizzes")