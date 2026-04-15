from fastapi import FastAPI, HTTPException, Depends
from typing import List, Optional
import datetime as dt
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator
from zoneinfo import ZoneInfo
from database import init_db, get_db, kolkata_now, to_utc_naive, KOLKATA

# Constants
DATE_INPUT_FORMAT = "%d-%m-%Y"
TIME_INPUT_FORMAT = "%H:%M"
MIN_ADVANCE_MINUTES = 15
MAX_FUTURE_DAYS = 90  # Allow appointments up to 90 days in future

START_TIME_ERROR_DETAIL = (
    "Invalid start_time. Use ISO datetime, 'today/tomorrow at time', "
    f"or 'dd-mm-yyyy HH:MM' (optionally with am/pm). Times must be at least {MIN_ADVANCE_MINUTES} minutes in future "
    f"and within {MAX_FUTURE_DAYS} days."
)

UTC = dt.timezone.utc

# Initialize database
init_db()
app = FastAPI(title="Appointment Scheduler API")


# Pydantic Models
class AppointmentRequest(BaseModel):
    patient_name: str = Field(..., min_length=1, max_length=100)
    reason: Optional[str] = Field(None, max_length=500)
    start_time: str | dt.datetime

    @field_validator('patient_name')
    @classmethod
    def validate_patient_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Patient name cannot be empty")
        return v


class AppointmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    patient_name: str
    reason: Optional[str]
    start_time: dt.datetime
    cancelled: bool
    created_at: dt.datetime


class CancelAppointmentRequest(BaseModel):
    patient_name: str = Field(..., min_length=1)
    date: str | dt.date


class CancelAppointmentResponse(BaseModel):
    success: bool
    message: str
    cancelled_count: int = 0


class DateTimeParseError(Exception):
    """Custom exception for datetime parsing errors"""
    pass


# Helper Functions
def normalize_specialty_filter(value: str) -> str:
    """Normalize specialty filter for database query"""
    cleaned = value.strip().lower()
    cleaned = re.sub(
        r"\b(dr|doctor|doctors|any|available|availability|show|check|find|finds|list|please|the|a|an|today|tomorrow|tommorow|now|tonight|speciality|specialty)\b",
        " ",
        cleaned,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def parse_request_date(value: str | dt.date | dt.datetime | None) -> dt.date:
    """Parse date from various formats with validation"""
    if value is None:
        return dt.datetime.now(KOLKATA).date()

    if isinstance(value, dt.datetime):
        return value.date()

    if isinstance(value, dt.date):
        return value

    normalized = value.strip().lower().replace("tommorow", "tomorrow")
    today = dt.datetime.now(KOLKATA).date()

    if normalized == "today":
        return today

    if normalized == "tomorrow":
        return today + dt.timedelta(days=1)

    try:
        parsed_date = dt.datetime.strptime(normalized, DATE_INPUT_FORMAT).date()
        
        # Validate date range
        if parsed_date < today:
            raise HTTPException(
                status_code=422,
                detail=f"Cannot use past dates. Today is {today.strftime(DATE_INPUT_FORMAT)}"
            )
        
        if parsed_date > today + dt.timedelta(days=MAX_FUTURE_DAYS):
            raise HTTPException(
                status_code=422,
                detail=f"Cannot schedule appointments more than {MAX_FUTURE_DAYS} days in advance"
            )
        
        return parsed_date
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid date format. Use 'today', 'tomorrow', or dd-mm-yyyy (e.g., {today.strftime(DATE_INPUT_FORMAT)})",
        ) from exc


def parse_time_component(time_str: str) -> dt.time:
    """Parse time string with support for 12/24 hour formats"""
    normalized = time_str.strip().lower().replace(".", "")
    normalized = re.sub(r"\s+", " ", normalized)

    # Handle 12-hour format with am/pm
    am_pm_match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*([ap]m)", normalized)
    if am_pm_match:
        hour = int(am_pm_match.group(1))
        minute = int(am_pm_match.group(2) or 0)
        meridiem = am_pm_match.group(3)

        if hour < 1 or hour > 12 or minute < 0 or minute > 59:
            raise ValueError("Invalid 12-hour time format")

        if meridiem == "pm" and hour != 12:
            hour += 12
        if meridiem == "am" and hour == 12:
            hour = 0
        return dt.time(hour=hour, minute=minute)

    # Handle 24-hour format
    for fmt in ("%H:%M", "%H"):
        try:
            parsed_time = dt.datetime.strptime(normalized, fmt).time()
            if parsed_time.hour > 23 or parsed_time.minute > 59:
                raise ValueError("Invalid time")
            return parsed_time
        except ValueError:
            continue

    raise ValueError(f"Unsupported time format: '{time_str}'. Use HH:MM or 12-hour format with am/pm")


def parse_iso_datetime_safe(dt_str: str) -> Optional[dt.datetime]:
    """Safely parse ISO datetime string with timezone"""
    # Try with dateutil if available
    try:
        from dateutil import parser as dateutil_parser
        return dateutil_parser.parse(dt_str)
    except ImportError:
        pass
    
    # Fallback to fromisoformat
    try:
        # Handle Zulu timezone
        if dt_str.endswith('Z'):
            dt_str = dt_str[:-1] + '+00:00'
        return dt.datetime.fromisoformat(dt_str)
    except ValueError:
        return None


def validate_datetime_range(parsed_dt: dt.datetime, now: dt.datetime) -> None:
    """Validate that datetime is within acceptable range"""
    # Check year range (reject obviously wrong years)
    if parsed_dt.year < now.year - 1:
        raise HTTPException(
            status_code=422,
            detail=f"Year {parsed_dt.year} is too far in the past. Please use {now.year} or {now.year + 1}."
        )
    
    if parsed_dt.year > now.year + 2:
        raise HTTPException(
            status_code=422,
            detail=f"Year {parsed_dt.year} is too far in the future. Please use {now.year} or {now.year + 1}."
        )
    
    # Check if date is in the past
    if parsed_dt.date() < now.date():
        raise HTTPException(
            status_code=400,
            detail=f"Cannot schedule appointments on past dates. Date {parsed_dt.strftime(DATE_INPUT_FORMAT)} is before today {now.strftime(DATE_INPUT_FORMAT)}."
        )
    
    # Check if time is too close to now
    min_allowed_time = now + dt.timedelta(minutes=MIN_ADVANCE_MINUTES)
    if parsed_dt < min_allowed_time:
        if parsed_dt.date() == now.date():
            raise HTTPException(
                status_code=400,
                detail=f"Appointments must be scheduled at least {MIN_ADVANCE_MINUTES} minutes in advance. "
                       f"Current time: {now.strftime('%H:%M')}, requested time: {parsed_dt.strftime('%H:%M')}"
            )
    
    # Check future limit
    max_allowed_date = now.date() + dt.timedelta(days=MAX_FUTURE_DAYS)
    if parsed_dt.date() > max_allowed_date:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot schedule appointments more than {MAX_FUTURE_DAYS} days in advance. "
                   f"Max allowed date: {max_allowed_date.strftime(DATE_INPUT_FORMAT)}"
        )


def parse_start_time(start_time_input: str | dt.datetime) -> dt.datetime:
    """
    Parse start_time from various formats with comprehensive validation
    
    Supported formats:
    - ISO datetime: 2026-04-15T15:30:00
    - Relative: today at 3:30pm, tomorrow at 09:00
    - Absolute: 15-04-2026 15:30, 15-04-2026 3:30pm
    """
    now = dt.datetime.now(KOLKATA)
    
    try:
        parsed = None
        
        # Case 1: Already a datetime object
        if isinstance(start_time_input, dt.datetime):
            parsed = start_time_input
        
        # Case 2: Parse from string
        elif isinstance(start_time_input, str):
            raw = start_time_input.strip()
            if not raw:
                raise HTTPException(status_code=422, detail="start_time cannot be empty")
            
            normalized = re.sub(r"\s+", " ", raw.lower()).replace("tommorow", "tomorrow")
            
            # Try ISO format first
            iso_parsed = parse_iso_datetime_safe(raw)
            if iso_parsed:
                parsed = iso_parsed
            
            # Try relative format (today/tomorrow)
            if parsed is None:
                rel_match = re.fullmatch(r"(today|tomorrow)(?:\s+at)?\s+(.+)", normalized)
                if rel_match:
                    base_date = now.date()
                    if rel_match.group(1) == "tomorrow":
                        base_date += dt.timedelta(days=1)
                    
                    try:
                        parsed_time = parse_time_component(rel_match.group(2))
                        parsed = dt.datetime.combine(base_date, parsed_time)
                    except ValueError as e:
                        raise HTTPException(status_code=422, detail=f"Invalid time format: {str(e)}")
            
            # Try absolute format (dd-mm-yyyy)
            if parsed is None:
                abs_match = re.fullmatch(r"(\d{2}-\d{2}-\d{4})(?:\s+(.+))?", normalized)
                if abs_match:
                    try:
                        parsed_date = dt.datetime.strptime(abs_match.group(1), DATE_INPUT_FORMAT).date()
                        parsed_time_str = abs_match.group(2) or "09:00"  # Default to 9 AM
                        parsed_time = parse_time_component(parsed_time_str)
                        parsed = dt.datetime.combine(parsed_date, parsed_time)
                    except ValueError as e:
                        raise HTTPException(status_code=422, detail=f"Invalid date/time format: {str(e)}")
            
            # No valid format found
            if parsed is None:
                raise HTTPException(status_code=422, detail=START_TIME_ERROR_DETAIL)
        
        # Handle timezone
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=KOLKATA)
        else:
            parsed = parsed.astimezone(KOLKATA)
        
        # Validate datetime range
        validate_datetime_range(parsed, now)
        
        return parsed
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Failed to parse start_time: {str(e)}. {START_TIME_ERROR_DETAIL}"
        ) from e


def appointment_to_response(doc: dict) -> dict:
    """Convert MongoDB document to API response format"""
    return {
        "id": str(doc["_id"]),
        "patient_name": doc["patient_name"],
        "reason": doc.get("reason"),
        "start_time": doc["start_time"].replace(tzinfo=UTC).astimezone(KOLKATA),
        "cancelled": doc.get("cancelled", False),
        "created_at": doc["created_at"].replace(tzinfo=UTC).astimezone(KOLKATA),
    }


# API Endpoints
@app.post("/schedule_appointment/", response_model=AppointmentResponse)
def schedule_appointment(appointment: AppointmentRequest, db=Depends(get_db)):
    """Schedule a new appointment"""
    # Parse and validate start time
    start_time = parse_start_time(appointment.start_time)
    now = kolkata_now()
    
    # Double-check validation (redundant but safe)
    if start_time <= now:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Start time must be later than current time",
                "parsed_start_time": start_time.isoformat(),
                "server_now": now.isoformat(),
                "time_difference_seconds": (start_time - now).total_seconds()
            },
        )
    
    # Check for duplicate appointments (optional)
    start_time_utc_naive = to_utc_naive(start_time)
    existing = db.appointments.find_one({
        "patient_name": appointment.patient_name,
        "start_time": start_time_utc_naive,
        "cancelled": False
    })
    
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Patient {appointment.patient_name} already has an appointment at {start_time.strftime('%Y-%m-%d %H:%M')}"
        )
    
    # Create appointment
    created_at_utc_naive = to_utc_naive(kolkata_now())
    
    doc = {
        "patient_name": appointment.patient_name,
        "reason": appointment.reason,
        "start_time": start_time_utc_naive,
        "cancelled": False,
        "created_at": created_at_utc_naive,
    }
    
    result = db.appointments.insert_one(doc)
    inserted = db.appointments.find_one({"_id": result.inserted_id})
    
    return appointment_to_response(inserted)


@app.post("/cancel_appointment/", response_model=CancelAppointmentResponse)
def cancel_appointment(request: CancelAppointmentRequest, db=Depends(get_db)):
    """Cancel all appointments for a patient on a specific date"""
    request_date = parse_request_date(request.date)
    
    start_dt = dt.datetime.combine(request_date, dt.time.min, tzinfo=KOLKATA)
    end_dt = dt.datetime.combine(request_date, dt.time.max, tzinfo=KOLKATA)
    
    start_dt_q = to_utc_naive(start_dt)
    end_dt_q = to_utc_naive(end_dt)
    
    result = db.appointments.update_many(
        {
            "patient_name": request.patient_name,
            "start_time": {"$gte": start_dt_q, "$lte": end_dt_q},
            "cancelled": False,
        },
        {"$set": {"cancelled": True}},
    )
    
    if result.modified_count == 0:
        raise HTTPException(
            status_code=404, 
            detail=f"No active appointments found for {request.patient_name} on {request_date.strftime(DATE_INPUT_FORMAT)}"
        )
    
    return {
        "success": True, 
        "message": f"Cancelled {result.modified_count} appointment(s) for {request.patient_name}",
        "cancelled_count": result.modified_count
    }


@app.get("/list_appointments/", response_model=List[AppointmentResponse])
def list_appointments(date: str = "today", db=Depends(get_db)):
    """List all active appointments for a specific date"""
    request_date = parse_request_date(date)
    
    start_dt = dt.datetime.combine(request_date, dt.time.min, tzinfo=KOLKATA)
    end_dt = dt.datetime.combine(request_date, dt.time.max, tzinfo=KOLKATA)
    
    start_q = to_utc_naive(start_dt)
    end_q = to_utc_naive(end_dt)
    
    cursor = db.appointments.find(
        {"cancelled": False, "start_time": {"$gte": start_q, "$lte": end_q}}
    ).sort("start_time", 1)
    
    return [appointment_to_response(doc) for doc in cursor]


@app.get("/check_doctor_availability/")
def check_doctor_availability(
    date: Optional[str] = None,
    specialty: Optional[str] = None,
    speciality: Optional[str] = None,
    doctor_name: Optional[str] = None,
    name: Optional[str] = None,
    db=Depends(get_db),
):
    """Check doctor availability with optional filters"""
    resolved_date = parse_request_date(date)
    resolved_specialty = specialty or speciality
    resolved_name = doctor_name or name
    
    query = {"available": True}
    
    if resolved_name:
        query["name"] = {"$regex": resolved_name.strip(), "$options": "i"}
    
    if resolved_specialty:
        normalized_specialty = normalize_specialty_filter(resolved_specialty)
        if normalized_specialty:
            query["specialty"] = {"$regex": normalized_specialty, "$options": "i"}
    
    cursor = db.doctors.find(query)
    available_doctors = [
        {"name": doc["name"], "specialty": doc["specialty"]} 
        for doc in cursor
    ]
    
    response = {
        "date": resolved_date.strftime(DATE_INPUT_FORMAT),
        "available_doctors": available_doctors,
        "total_available": len(available_doctors)
    }
    
    if not resolved_name and not resolved_specialty:
        response["any_available_doctor"] = available_doctors[0] if available_doctors else None
    
    return response


# Health check endpoint
@app.get("/health")
def health_check():
    """Health check endpoint"""
    now = kolkata_now()
    return {
        "status": "healthy",
        "server_time": now.isoformat(),
        "server_time_formatted": now.strftime(f"%Y-%m-%d %H:%M:%S"),
        "timezone": str(KOLKATA),
        "config": {
            "min_advance_minutes": MIN_ADVANCE_MINUTES,
            "max_future_days": MAX_FUTURE_DAYS,
            "date_format": DATE_INPUT_FORMAT
        }
    }


# Debug endpoint to test datetime parsing
@app.post("/debug/parse_datetime/")
def debug_parse_datetime(start_time: str):
    """Debug endpoint to test datetime parsing"""
    try:
        parsed = parse_start_time(start_time)
        now = kolkata_now()
        
        return {
            "input": start_time,
            "parsed": parsed.isoformat(),
            "parsed_formatted": parsed.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "server_now": now.isoformat(),
            "is_future": parsed > now,
            "time_difference_minutes": (parsed - now).total_seconds() / 60 if parsed > now else None,
            "validation_passed": parsed > now
        }
    except HTTPException as e:
        return {
            "input": start_time,
            "error": e.detail,
            "status_code": e.status_code
        }