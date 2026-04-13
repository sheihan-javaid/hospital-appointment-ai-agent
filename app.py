import datetime as dt
import streamlit as st
import requests

REQUEST_TIMEOUT = 30
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

st.title("Hospital Appointment Booking Portal")
base_url = st.text_input("Backend URL", "https://hospital-appointment-ai-agent.onrender.com")

# Schedule appointment form
patient_name = st.text_input("Patient Name")
reason = st.text_input("Reason for Appointment")
start_date = st.date_input("Appointment Date", value=dt.date.today() + dt.timedelta(days=1))
start_time = st.time_input("Appointment Time", value=dt.time(hour=9, minute=0))

if st.button("Schedule Appointment"):
    start_dt = dt.datetime.combine(start_date, start_time, tzinfo=IST)  # fixed: IST-aware
    payload = {
        "patient_name": patient_name,
        "reason": reason,
        "start_time": start_dt.isoformat()
    }
    try:
        resp = requests.post(f"{base_url}/schedule_appointment/", json=payload, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        st.success(f"Scheduled appointment #{data['id']} for {data['patient_name']}")
    except requests.RequestException as exc:
        st.error(f"Schedule failed: {exc}")

st.divider()
st.subheader("Cancel Appointments")

cancel_name = st.text_input("Patient Name to Cancel", key="cancel_patient_name")
cancel_date = st.text_input(
    "Date to Cancel",
    value=dt.date.today().strftime("%d-%m-%Y"),         # fixed: hyphens
    help="Use today, tomorrow, or dd-mm-yyyy like 13-04-2026",  # fixed
    key="cancel_date",
)

if st.button("Cancel Appointment"):
    cancel_payload = {
        "patient_name": cancel_name,
        "date": cancel_date,
    }
    try:
        resp = requests.post(f"{base_url}/cancel_appointment/", json=cancel_payload, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        st.success(data.get("message", "Appointment cancelled."))
    except requests.RequestException as exc:
        st.error(f"Cancel failed: {exc}")

st.divider()
st.subheader("List Appointments")

list_date = st.text_input(
    "Date to View",
    value=dt.date.today().strftime("%d-%m-%Y"),         # fixed: hyphens
    help="Use today, tomorrow, or dd-mm-yyyy like 13-04-2026",  # fixed
    key="list_date",
)

if st.button("Load Appointments"):
    try:
        resp = requests.get(
            f"{base_url}/list_appointments/",
            params={"date": list_date},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        appointments = resp.json()
        if not appointments:
            st.info("No appointments for the selected date.")
        else:
            st.dataframe(
                [
                    {
                        "ID": appt["id"],
                        "Patient": appt["patient_name"],
                        "Reason": appt["reason"],
                        "Start": appt["start_time"],
                    }
                    for appt in appointments
                ],
                use_container_width=True,
            )
    except requests.RequestException as exc:
        st.error(f"Listing failed: {exc}")