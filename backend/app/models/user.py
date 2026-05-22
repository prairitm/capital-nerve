from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import SeverityLevel, UserType


class AppUser(Base):
    __tablename__ = "app_users"

    user_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str | None] = mapped_column(String, unique=True)
    phone: Mapped[str | None] = mapped_column(String, unique=True)
    full_name: Mapped[str | None] = mapped_column(String)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    user_type: Mapped[UserType] = mapped_column(Enum(UserType, name="user_type"), default=UserType.RETAIL)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Watchlist(Base):
    __tablename__ = "watchlists"
    __table_args__ = (UniqueConstraint("user_id", "watchlist_name", name="uq_watchlists_user_name"),)

    watchlist_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_users.user_id", ondelete="CASCADE"), nullable=False)
    watchlist_name: Mapped[str] = mapped_column(String, nullable=False, default="Default Watchlist")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WatchlistCompany(Base):
    __tablename__ = "watchlist_companies"
    __table_args__ = (UniqueConstraint("watchlist_id", "company_id", name="uq_watchlist_companies"),)

    watchlist_company_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    watchlist_id: Mapped[int] = mapped_column(
        ForeignKey("watchlists.watchlist_id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.company_id"), nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserWatchItem(Base):
    __tablename__ = "user_watch_items"

    watch_item_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_users.user_id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.company_id"), nullable=False)
    card_id: Mapped[int | None] = mapped_column(ForeignKey("intelligence_cards.card_id"))
    metric_def_id: Mapped[int | None] = mapped_column(ForeignKey("metric_definitions.metric_def_id"))

    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    current_value: Mapped[float | None] = mapped_column(Numeric(24, 6))
    target_value: Mapped[float | None] = mapped_column(Numeric(24, 6))
    condition_operator: Mapped[str | None] = mapped_column(String)
    condition_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AlertRule(Base):
    __tablename__ = "alert_rules"

    alert_rule_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_users.user_id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.company_id"))
    watch_item_id: Mapped[int | None] = mapped_column(ForeignKey("user_watch_items.watch_item_id"))

    alert_name: Mapped[str] = mapped_column(String, nullable=False)
    alert_type: Mapped[str] = mapped_column(String, nullable=False)
    signal_category: Mapped[str | None] = mapped_column(String)
    severity_filter: Mapped[SeverityLevel | None] = mapped_column(Enum(SeverityLevel, name="severity_level"))
    rule_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    delivery_channels: Mapped[list] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Alert(Base):
    __tablename__ = "alerts"

    alert_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_users.user_id", ondelete="CASCADE"), nullable=False)
    alert_rule_id: Mapped[int | None] = mapped_column(ForeignKey("alert_rules.alert_rule_id"))

    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.company_id"))
    event_id: Mapped[int | None] = mapped_column(ForeignKey("company_events.event_id"))
    card_id: Mapped[int | None] = mapped_column(ForeignKey("intelligence_cards.card_id"))
    signal_id: Mapped[int | None] = mapped_column(ForeignKey("generated_signals.signal_id"))

    alert_title: Mapped[str] = mapped_column(String, nullable=False)
    alert_message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[SeverityLevel | None] = mapped_column(Enum(SeverityLevel, name="severity_level"))

    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_status: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
