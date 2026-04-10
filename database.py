import datetime as dt

from sqlalchemy import Boolean, Column, DateTime, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

DATABASE_URL = "sqlite:///./appointments_db.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    patient_name = Column(String, index=True)
    reason = Column(String, index=True)
    start_time = Column(DateTime, default=dt.datetime.utcnow)
    cancelled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

def init_db():
    Base.metadata.create_all(bind=engine)

init_db()