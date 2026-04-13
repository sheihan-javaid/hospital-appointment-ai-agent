# import datetime as dt
# import streamlit as st
# import requests

# st.set_page_config(page_title="Hospital Appointment Booking Portal", page_icon="🏥", layout="wide")

# st.markdown(
#     """
#     <style>
#         @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;700;800&family=Source+Serif+4:wght@600;700&display=swap');

#         .stApp {
#             background:
#                 radial-gradient(circle at top left, rgba(19, 92, 161, 0.12), transparent 25%),
#                 radial-gradient(circle at top right, rgba(20, 184, 166, 0.10), transparent 22%),
#                 linear-gradient(180deg, #f8fbfe 0%, #edf4f8 100%);
#             font-family: 'Manrope', sans-serif;
#             color: #102033;
#         }

#         .hero {
#             padding: 2.3rem 2.3rem 1.5rem 2.3rem;
#             border-radius: 28px;
#             background:
#                 linear-gradient(135deg, rgba(8, 27, 54, 0.98), rgba(14, 95, 153, 0.94)),
#                 radial-gradient(circle at top right, rgba(255, 255, 255, 0.13), transparent 22%);
#             color: white;
#             box-shadow: 0 24px 60px rgba(7, 20, 40, 0.26);
#             border: 1px solid rgba(255, 255, 255, 0.12);
#             position: relative;
#             overflow: hidden;
#         }

#         .hero::after {
#             content: '';
#             position: absolute;
#             inset: auto -10% -30% auto;
#             width: 260px;
#             height: 260px;
#             background: radial-gradient(circle, rgba(255,255,255,0.14), transparent 68%);
#             pointer-events: none;
#         }

#         .hero h1 {
#             margin: 0;
#             font-family: 'Source Serif 4', serif;
#             font-size: 2.45rem;
#             line-height: 1.1;
#         }

#         .hero p {
#             margin: 0.85rem 0 0 0;
#             font-size: 1.02rem;
#             opacity: 0.92;
#             max-width: 54rem;
#         }

#         .pill-row {
#             display: flex;
#             flex-wrap: wrap;
#             gap: 0.6rem;
#             margin-top: 1.2rem;
#         }

#         .pill {
#             display: inline-flex;
#             align-items: center;
#             gap: 0.45rem;
#             padding: 0.45rem 0.8rem;
#             border-radius: 999px;
#             border: 1px solid rgba(255, 255, 255, 0.16);
#             background: rgba(255, 255, 255, 0.08);
#             font-size: 0.84rem;
#             font-weight: 700;
#             letter-spacing: 0.01em;
#         }

#         .section-title {
#             font-size: 0.78rem;
#             text-transform: uppercase;
#             letter-spacing: 0.14em;
#             color: #44607f;
#             margin-bottom: 0.35rem;
#             font-weight: 700;
#         }

#         .card {
#             padding: 1.4rem 1.4rem 1.1rem 1.4rem;
#             border-radius: 22px;
#             background: rgba(255, 255, 255, 0.84);
#             border: 1px solid rgba(149, 170, 197, 0.22);
#             box-shadow: 0 14px 34px rgba(30, 52, 77, 0.08);
#             backdrop-filter: blur(12px);
#         }

#         .stat {
#             padding: 1rem 1.1rem;
#             border-radius: 18px;
#             background: linear-gradient(180deg, #ffffff 0%, #f6fbfd 100%);
#             border: 1px solid rgba(149, 170, 197, 0.24);
#             box-shadow: 0 8px 24px rgba(30, 52, 77, 0.06);
#         }

#         .stat-label {
#             color: #51687f;
#             font-size: 0.82rem;
#             font-weight: 700;
#             text-transform: uppercase;
#             letter-spacing: 0.08em;
#             margin-bottom: 0.35rem;
#         }

#         .stat-value {
#             color: #0d223a;
#             font-size: 1.42rem;
#             font-weight: 800;
#         }

#         .subtle-note {
#             color: #5b718c;
#             font-size: 0.94rem;
#             margin-top: 0.25rem;
#         }

#         .helper-strip {
#             margin-top: 0.9rem;
#             padding: 0.85rem 1rem;
#             border-radius: 16px;
#             background: rgba(255, 255, 255, 0.72);
#             border: 1px solid rgba(149, 170, 197, 0.20);
#             color: #415870;
#             font-size: 0.95rem;
#         }

#         .stButton > button {
#             border: none;
#             border-radius: 14px;
#             padding: 0.7rem 1.1rem;
#             font-weight: 700;
#             background: linear-gradient(135deg, #1159b7 0%, #1c7ae6 100%);
#             color: white;
#             box-shadow: 0 12px 24px rgba(14, 97, 181, 0.20);
#             transition: transform 0.15s ease, box-shadow 0.15s ease;
#         }

#         .stButton > button:hover {
#             transform: translateY(-1px);
#             box-shadow: 0 16px 28px rgba(14, 97, 181, 0.26);
#         }

#         .stTabs [data-baseweb="tab-list"] {
#             gap: 0.5rem;
#             background: rgba(255, 255, 255, 0.55);
#             padding: 0.35rem;
#             border-radius: 16px;
#             border: 1px solid rgba(149, 170, 197, 0.18);
#         }

#         .stTabs [data-baseweb="tab"] {
#             border-radius: 12px;
#             padding: 0.6rem 0.9rem;
#             font-weight: 700;
#         }

#         .stDataFrame {
#             border-radius: 18px;
#             overflow: hidden;
#         }

#         div[data-baseweb="input"] > div,
#         div[data-baseweb="textarea"] > div,
#         div[data-baseweb="select"] > div {
#             border-radius: 14px !important;
#             border-color: rgba(149, 170, 197, 0.30) !important;
#             background: rgba(255, 255, 255, 0.95) !important;
#         }

#         input, textarea, div[data-baseweb="input"] input, div[data-baseweb="textarea"] textarea {
#             color: #102033 !important;
#             -webkit-text-fill-color: #102033 !important;
#         }

#         input::placeholder, textarea::placeholder {
#             color: #7b8da3 !important;
#             opacity: 1 !important;
#         }

#         label, .stMarkdown, .stText, .stCaption {
#             color: #102033;
#         }

#         .stTabs [data-baseweb="tab"] p {
#             color: #2b4058;
#         }
#     </style>
#     """,
#     unsafe_allow_html=True,
# )


# def fetch_appointments(api_base_url: str, date_value: dt.date):
#     response = requests.get(
#         f"{api_base_url}/list_appointment/",
#         params={"date": date_value.isoformat()},
#         timeout=10,
#     )
#     response.raise_for_status()
#     return response.json()


# def build_time_slots(start_hour: int = 8, end_hour: int = 17, step_minutes: int = 30):
#     slots = []
#     current = dt.datetime.combine(dt.date.today(), dt.time(hour=start_hour, minute=0))
#     end_time = dt.datetime.combine(dt.date.today(), dt.time(hour=end_hour, minute=0))

#     while current <= end_time:
#         slots.append(current.time())
#         current += dt.timedelta(minutes=step_minutes)

#     return slots


# st.markdown(
#     """
#     <div class="hero">
#         <h1>Hospital Appointment Booking Portal</h1>
#         <p>Schedule, manage, and review appointments in a clean workflow designed for fast front-desk use.</p>
#         <div class="pill-row">
#             <div class="pill">Care team ready</div>
#             <div class="pill">Fast scheduling</div>
#             <div class="pill">Daily appointment view</div>
#         </div>
#     </div>
#     """,
#     unsafe_allow_html=True,
# )

# st.write("")

# st.markdown('<div class="section-title">Connection</div>', unsafe_allow_html=True)
# base_url = st.text_input("Backend URL", "http://127.0.0.1:8000", label_visibility="collapsed")
# st.markdown(
#     '<div class="helper-strip">Set the backend URL above, then use the tabs below to manage appointments.</div>',
#     unsafe_allow_html=True,
# )

# tab_schedule, tab_cancel, tab_list = st.tabs(["Schedule", "Cancel", "View Appointments"])

# with tab_schedule:
#     st.markdown('<div class="card">', unsafe_allow_html=True)
#     st.markdown('<div class="section-title">New Appointment</div>', unsafe_allow_html=True)
#     st.markdown('<div class="subtle-note">Fill in the details below, then submit to create the booking.</div>', unsafe_allow_html=True)
#     with st.form("schedule_form", clear_on_submit=False):
#         patient_name = st.text_input("Patient Name", placeholder="Enter patient name")
#         reason = st.text_input("Reason for Appointment", placeholder="Follow-up, checkup, consultation...")
#         col1, col2 = st.columns(2)
#         with col1:
#             start_date = st.date_input(
#                 "Appointment Date",
#                 value=dt.date.today() + dt.timedelta(days=1),
#             )
#         with col2:
#             time_options = build_time_slots()
#             start_time = st.selectbox(
#                 "Appointment Time",
#                 time_options,
#                 index=2,
#                 format_func=lambda value: value.strftime("%I:%M %p"),
#             )

#         submitted = st.form_submit_button("Schedule Appointment", type="primary", use_container_width=True)
#         if submitted:
#             start_dt = dt.datetime.combine(start_date, start_time)
#             payload = {
#                 "patient_name": patient_name,
#                 "reason": reason,
#                 "start_time": start_dt.isoformat(),
#             }
#             try:
#                 with st.spinner("Scheduling appointment..."):
#                     resp = requests.post(f"{base_url}/schedule_appointment/", json=payload, timeout=10)
#                     resp.raise_for_status()
#                 data = resp.json()
#                 st.success(f"Scheduled appointment #{data['id']} for {data['patient_name']}")
#             except requests.RequestException as exc:
#                 st.error(f"Schedule failed: {exc}")
#     st.markdown("</div>", unsafe_allow_html=True)

# with tab_cancel:
#     st.markdown('<div class="card">', unsafe_allow_html=True)
#     st.markdown('<div class="section-title">Cancel Appointment</div>', unsafe_allow_html=True)
#     with st.form("cancel_form", clear_on_submit=False):
#         cancel_name = st.text_input("Patient Name", key="cancel_patient_name", placeholder="Name on the booking")
#         cancel_date = st.date_input("Date", value=dt.date.today(), key="cancel_date")
#         submitted = st.form_submit_button("Cancel Appointment")
#         if submitted:
#             cancel_payload = {
#                 "patient_name": cancel_name,
#                 "date": cancel_date.isoformat(),
#             }
#             try:
#                 with st.spinner("Cancelling appointment..."):
#                     resp = requests.post(f"{base_url}/cancel_appointment/", json=cancel_payload, timeout=10)
#                     resp.raise_for_status()
#                 data = resp.json()
#                 st.success(data.get("message", "Appointment cancelled."))
#             except requests.RequestException as exc:
#                 st.error(f"Cancel failed: {exc}")
#     st.markdown("</div>", unsafe_allow_html=True)

# with tab_list:
#     st.markdown('<div class="card">', unsafe_allow_html=True)
#     st.markdown('<div class="section-title">Daily Schedule</div>', unsafe_allow_html=True)
#     st.markdown('<div class="subtle-note">Use a date to review the day’s bookings and confirm the clinic flow.</div>', unsafe_allow_html=True)
#     list_date = st.date_input("View appointments for", value=dt.date.today(), key="list_date")

#     if "appointments" not in st.session_state:
#         st.session_state.appointments = []

#     col1, col2, col3 = st.columns([1, 1, 2])
#     with col1:
#         load_clicked = st.button("Load Appointments")
#     with col2:
#         refresh_clicked = st.button("Refresh")

#     if load_clicked or refresh_clicked:
#         try:
#             with st.spinner("Loading appointments..."):
#                 st.session_state.appointments = fetch_appointments(base_url, list_date)
#         except requests.RequestException as exc:
#             st.error(f"Listing failed: {exc}")

#     appointments = st.session_state.appointments
#     if appointments:
#         sorted_appointments = sorted(appointments, key=lambda item: item["start_time"])
#         metric_a, metric_b, metric_c = st.columns(3)
#         with metric_a:
#             st.markdown(
#                 f'<div class="stat"><div class="stat-label">Total Appointments</div><div class="stat-value">{len(sorted_appointments)}</div></div>',
#                 unsafe_allow_html=True,
#             )
#         with metric_b:
#             st.markdown(
#                 f'<div class="stat"><div class="stat-label">First Slot</div><div class="stat-value">{sorted_appointments[0]["start_time"][11:16]}</div></div>',
#                 unsafe_allow_html=True,
#             )
#         with metric_c:
#             st.markdown(
#                 f'<div class="stat"><div class="stat-label">Latest Slot</div><div class="stat-value">{sorted_appointments[-1]["start_time"][11:16]}</div></div>',
#                 unsafe_allow_html=True,
#             )

#         st.dataframe(
#             [
#                 {
#                     "ID": appt["id"],
#                     "Patient": appt["patient_name"],
#                     "Reason": appt["reason"],
#                     "Start Time": appt["start_time"],
#                 }
#                 for appt in sorted_appointments
#             ],
#             use_container_width=True,
#             hide_index=True,
#         )
#     else:
#         st.info("Load a date to view appointments for that day.")
#     st.markdown("</div>", unsafe_allow_html=True)



# def count_substring(string, sub_string):
#     count = 0
#     for i in range(0, len(string)-len(sub_string)+1):
#         if string[i:i+len(sub_string)] == sub_string:
#             count += 1

#         return count
        
#     return

# if __name__ == '__main__':
#     string = input().strip()
#     sub_string = input().strip()
    
#     count = count_substring(string, sub_string)
#     print(count)

    