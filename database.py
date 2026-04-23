import datetime as dt
from zoneinfo import ZoneInfo
from pymongo import MongoClient
from dotenv import load_dotenv
import os
import hashlib

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
    db.doctors.create_index("name", unique=True)
    for doc in Doctor_name:
        # deterministic doctor_id based on name to keep IDs stable across restarts
        name = doc["name"].strip().lower()
        digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8].upper()
        doc_copy = doc.copy()
        doc_copy["doctor_id"] = f"DR-{digest}"
        db.doctors.update_one({"name": doc["name"]}, {"$setOnInsert": doc_copy}, upsert=True)


def init_db() -> None:
    db.doctors.create_index("name", unique=True)
    db.appointments.create_index("start_time")
    # Ensure appointment_id is unique when present
    db.appointments.create_index("appointment_id", unique=True, sparse=True)
    _seed_default_doctors()
    # Ensure doctors have a unique doctor_id and index it
    db.doctors.create_index("doctor_id", unique=True, sparse=True)
    for d in db.doctors.find({}):
        if "doctor_id" not in d:
            name = d.get("name", "").strip().lower()
            digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8].upper()
            new_id = f"DR-{digest}"
            db.doctors.update_one({"_id": d["_id"]}, {"$set": {"doctor_id": new_id}})


def get_db():
    try:
        yield db
    finally:
        pass