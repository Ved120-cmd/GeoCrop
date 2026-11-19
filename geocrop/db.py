"""PostgreSQL storage for farmer profiles (portable PostgreSQL 17 on localhost:5433, credentials in .env).

Personal data is kept minimal: name, optional phone, farm location and farming details. Nothing is sent
to third parties.
"""
import os
import uuid
from datetime import date, datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import (CheckConstraint, Date, DateTime, Float, ForeignKey, Integer, String, create_engine)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from geocrop.config import ROOT

load_dotenv(ROOT / ".env")


def db_url():
    e = os.environ
    return (f"postgresql+psycopg://{e['GEOCROP_DB_USER']}:{e['GEOCROP_DB_PASSWORD']}@{e.get('GEOCROP_DB_HOST', 'localhost')}:"
            f"{e.get('GEOCROP_DB_PORT', '5433')}/{e.get('GEOCROP_DB_NAME', 'geocrop')}")


engine = create_engine(db_url(), pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def _now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Farmer(Base):
    __tablename__ = "farmers"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(20))
    language: Mapped[str] = mapped_column(String(2), default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    farms: Mapped[list["Farm"]] = relationship(back_populates="farmer", cascade="all, delete-orphan", order_by="Farm.created_at")
    __table_args__ = (CheckConstraint("language in ('en','mr')"),)


class Farm(Base):
    __tablename__ = "farms"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    farmer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farmers.id", ondelete="CASCADE"), index=True)
    name: Mapped[str | None] = mapped_column(String(120))
    district_id: Mapped[int] = mapped_column(Integer)
    taluka: Mapped[str | None] = mapped_column(String(80))
    village: Mapped[str | None] = mapped_column(String(80))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    area_value: Mapped[float | None] = mapped_column(Float)
    area_unit: Mapped[str] = mapped_column(String(10), default="acre")
    irrigation_source: Mapped[str] = mapped_column(String(20), default="rainfed")
    soil_type_reported: Mapped[str] = mapped_column(String(20), default="unknown")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    farmer: Mapped[Farmer] = relationship(back_populates="farms")
    crops: Mapped[list["CropPlanting"]] = relationship(back_populates="farm", cascade="all, delete-orphan", order_by="CropPlanting.sowing_date")
    irrigation: Mapped[list["IrrigationEvent"]] = relationship(back_populates="farm", cascade="all, delete-orphan", order_by="IrrigationEvent.date")
    __table_args__ = (CheckConstraint("district_id between 1 and 36"), CheckConstraint("area_unit in ('acre','hectare','guntha')"),
                      CheckConstraint("lat is null or (lat between 15 and 23)"), CheckConstraint("lon is null or (lon between 72 and 81.5)"))


class CropPlanting(Base):
    __tablename__ = "crop_plantings"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    farm_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farms.id", ondelete="CASCADE"), index=True)
    crop: Mapped[str] = mapped_column(String(40))
    crop_other: Mapped[str | None] = mapped_column(String(80))
    season: Mapped[str] = mapped_column(String(10))
    sowing_date: Mapped[date | None] = mapped_column(Date)
    farm: Mapped[Farm] = relationship(back_populates="crops")


class IrrigationEvent(Base):
    __tablename__ = "irrigation_events"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    farm_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farms.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date)
    amount_mm: Mapped[float] = mapped_column(Float)
    method: Mapped[str | None] = mapped_column(String(20))
    farm: Mapped[Farm] = relationship(back_populates="irrigation")
    __table_args__ = (CheckConstraint("amount_mm > 0 and amount_mm <= 300"),)


def init_db():
    Base.metadata.create_all(engine)


if __name__ == "__main__":
    init_db()
    print("tables:", list(Base.metadata.tables))
