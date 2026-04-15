import datetime as dt
from zoneinfo import ZoneInfo
from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError(
        "Environment variable MONGO_URI is not set. Set it to your MongoDB connection string."
    )

MONGO_DB = os.environ.get("MONGO_DB", "hospital_ai_agent")

client = MongoClient(MONGO_URI)
db = client[MONGO_DB]

KOLKATA = ZoneInfo("Asia/Kolkata")
UTC = dt.timezone.utc


def kolkata_now() -> dt.datetime:
    return dt.datetime.now(KOLKATA)


def to_utc_naive(value: dt.datetime) -> dt.datetime:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value.replace(tzinfo=KOLKATA).astimezone(UTC).replace(tzinfo=None)


Doctor_name = [
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
    # Ensure unique index on name
    db.doctors.create_index("name", unique=True)
    for doc in Doctor_name:
        db.doctors.update_one({"name": doc["name"]}, {"$setOnInsert": doc}, upsert=True)


def init_db() -> None:
    # Create indexes useful for queries
    db.doctors.create_index("name", unique=True)
    db.appointments.create_index("start_time")
    _seed_default_doctors()


def get_db():
    # FastAPI-style dependency; yields the pymongo Database object
    try:
        yield db
    finally:
        # pymongo client is long-lived; do not close here
        pass