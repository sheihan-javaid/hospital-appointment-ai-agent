import datetime as dt

from sqlalchemy import Boolean, Column, DateTime, Integer, String, create_engine
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite:///./appointments_db.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Appointment(Base):
    __tablename__ = "appointments"

    id           = Column(Integer,           primary_key=True, index=True)
    patient_name = Column(String,            index=True)
    reason       = Column(String,            index=True)
    start_time   = Column(DateTime(timezone=True), default=utcnow)
    cancelled    = Column(Boolean,           default=False)
    created_at   = Column(DateTime(timezone=True), default=utcnow)


class Doctor(Base):
    __tablename__ = "doctors"

    id        = Column(Integer, primary_key=True, index=True)
    name      = Column(String,  unique=True, index=True, nullable=False)
    specialty = Column(String,  nullable=False)
    available = Column(Boolean, default=True, nullable=False)


_DEFAULT_DOCTORS = [
    {"name": "Dr. Sarah Khan",     "specialty": "Cardiology",      "available": True},
    {"name": "Dr. Michael Lee",    "specialty": "Neurology",        "available": True},
    {"name": "Dr. Aisha Rahman",   "specialty": "Pediatrics",       "available": True},
    {"name": "Dr. David Chen",     "specialty": "Orthopedics",      "available": True},
    {"name": "Dr. Emily Johnson",  "specialty": "Dermatology",      "available": True},
    {"name": "Dr. James Smith",    "specialty": "General Practice", "available": True},
    {"name": "Dr. Maria Garcia",   "specialty": "Gynecology",       "available": True},
    {"name": "Dr. Robert Brown",   "specialty": "Urology",          "available": True},
    {"name": "Dr. Linda Davis",    "specialty": "Endocrinology",    "available": True},
    {"name": "Dr. William Wilson", "specialty": "Dentistry",        "available": True},
]


def _seed_default_doctors() -> None:
    with engine.begin() as conn:
        conn.execute(
            insert(Doctor).prefix_with("OR IGNORE"),
            _DEFAULT_DOCTORS,
        )


def init_db() -> None:
    Base.metadata.create_all(bind=engine)  
    _seed_default_doctors()               

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()