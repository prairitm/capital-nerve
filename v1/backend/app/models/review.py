from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import SeverityLevel


class ReviewQueue(Base):
    __tablename__ = "review_queue"

    review_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.company_id"))
    event_id: Mapped[int | None] = mapped_column(ForeignKey("company_events.event_id"))
    document_id: Mapped[int | None] = mapped_column(ForeignKey("source_documents.document_id"))
    card_id: Mapped[int | None] = mapped_column(ForeignKey("intelligence_cards.card_id"))
    extracted_value_id: Mapped[int | None] = mapped_column(ForeignKey("extracted_values.extracted_value_id"))

    review_type: Mapped[str] = mapped_column(String, nullable=False)
    priority: Mapped[SeverityLevel] = mapped_column(
        Enum(SeverityLevel, name="severity_level"), default=SeverityLevel.MEDIUM
    )
    issue_description: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(String, default="OPEN")
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("app_users.user_id"))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
