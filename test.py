# test.py

import datetime as dt
from zoneinfo import ZoneInfo

# Same timezone as your main.py
KOLKATA = ZoneInfo("Asia/Kolkata")

def kolkata_now():
    now = dt.datetime.now(KOLKATA)
    return now

if __name__ == "__main__":
    now = kolkata_now()

    print("Current IST Time:", now)
    print("Date:", now.date())
    print("Time:", now.strftime("%H:%M:%S"))