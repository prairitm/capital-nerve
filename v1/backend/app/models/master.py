from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enums import CompanyStatus, ExchangeCode, PeriodType


class Sector(Base):
    __tablename__ = "sectors"

    sector_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sector_name: Mapped[str] = mapped_column(String, nullable=False)
    industry_group: Mapped[str | None] = mapped_column(String)
    industry: Mapped[str | None] = mapped_column(String)
    sub_industry: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    companies: Mapped[list["Company"]] = relationship(back_populates="sector")


class Company(Base):
    __tablename__ = "companies"

    company_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_name: Mapped[str] = mapped_column(String, nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String)
    short_name: Mapped[str | None] = mapped_column(String)

    nse_symbol: Mapped[str | None] = mapped_column(String, unique=True)
    bse_code: Mapped[str | None] = mapped_column(String, unique=True)
    isin: Mapped[str | None] = mapped_column(String, unique=True)
    cin: Mapped[str | None] = mapped_column(String)

    sector_id: Mapped[int | None] = mapped_column(ForeignKey("sectors.sector_id"))
    industry: Mapped[str | None] = mapped_column(String)
    website_url: Mapped[str | None] = mapped_column(String)
    investor_relations_url: Mapped[str | None] = mapped_column(String)

    status: Mapped[CompanyStatus] = mapped_column(
        Enum(CompanyStatus, name="company_status"), default=CompanyStatus.ACTIVE
    )

    market_cap_cr: Mapped[float | None] = mapped_column()
    last_price: Mapped[float | None] = mapped_column()

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    sector: Mapped["Sector | None"] = relationship(back_populates="companies")
    securities: Mapped[list["Security"]] = relationship(back_populates="company")


class Security(Base):
    __tablename__ = "securities"
    __table_args__ = (UniqueConstraint("exchange", "symbol", name="uq_securities_exchange_symbol"),)

    security_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.company_id"), nullable=False)
    exchange: Mapped[ExchangeCode] = mapped_column(Enum(ExchangeCode, name="exchange_code"), nullable=False)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    isin: Mapped[str | None] = mapped_column(String)
    security_name: Mapped[str | None] = mapped_column(String)
    listing_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="securities")


class FinancialPeriod(Base):
    __tablename__ = "financial_periods"
    __table_args__ = (UniqueConstraint("fy_year", "quarter", "period_type", name="uq_financial_periods"),)

    period_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    fy_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fy_label: Mapped[str] = mapped_column(String, nullable=False)
    quarter: Mapped[int | None] = mapped_column(Integer)
    period_type: Mapped[PeriodType] = mapped_column(Enum(PeriodType, name="period_type"), nullable=False)
    period_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    display_label: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
