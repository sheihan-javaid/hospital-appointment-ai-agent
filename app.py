import datetime as dt
from zoneinfo import ZoneInfo
import streamlit as st
import requests

KOLKATA = ZoneInfo("Asia/Kolkata")
TIMEOUT = 30

st.title("Hospital Appointment Booking Portal")
BASE_URL = st.text_input("Backend URL", "https://hospital-appointment-ai-agent.onrender.com")


def api_post(endpoint: str, payload: dict) -> dict | None:
    try:
        resp = requests.post(f"{BASE_URL}/{endpoint}/", json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        st.error(str(e))
        return None


def api_get(endpoint: str, params: dict) -> dict | None:
    try:
        resp = requests.get(f"{BASE_URL}/{endpoint}/", params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        st.error(str(e))
        return None


#Schedule Appointment form
st.subheader("Schedule Appointment")
patient_name = st.text_input("Patient Name")
reason = st.text_input("Reason")
start_date = st.date_input("Date", value=dt.date.today() + dt.timedelta(days=1))
start_time = st.time_input("Time", value=dt.time(9, 0))
doctor_name = st.text_input("Preferred Doctor Name (optional)")

if st.button("Schedule Appointment"):
    if not patient_name.strip():
        st.error("Patient name is required.")
    else:
        start_dt = dt.datetime.combine(start_date, start_time, tzinfo=KOLKATA)
        payload = {
            "patient_name": patient_name.strip(),
            "reason": reason.strip() or None,
            "start_time": start_dt.isoformat(),
        }
        if doctor_name.strip():
            payload["doctor_name"] = doctor_name.strip()

        data = api_post("schedule_appointment", payload)
        if data:
            st.success(f"Appointment **{data['id']}** scheduled for **{data['patient_name']}**")

# Cancel Appointment form
st.divider()
st.subheader("Cancel Appointment")
cancel_name = st.text_input("Patient Name", key="cancel_name")
cancel_date = st.date_input("Date", value=dt.date.today(), key="cancel_date")

if st.button("Cancel Appointment"):
    if not cancel_name.strip():
        st.error("Patient name is required.")
    else:
        data = api_post("cancel_appointment", {
            "patient_name": cancel_name.strip(),
            "date": cancel_date.isoformat(),
        })
        if data:
            st.success(data.get("message", "Appointment cancelled."))

# List Appointments form
st.divider()
st.subheader("List Appointments")
list_date = st.date_input("Date", value=dt.date.today(), key="list_date")

if st.button("Load Appointments"):
    data = api_get("list_appointments", {"date": list_date.isoformat()})
    if data is None:
        pass
    elif not data:
        st.info("No appointments for this date.")
    else:
        st.dataframe(
            [{"ID": a["id"], "Patient": a["patient_name"], "Reason": a["reason"], "Start": a["start_time"]} for a in data],
            use_container_width=True,
        )