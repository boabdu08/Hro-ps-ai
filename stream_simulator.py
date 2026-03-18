import random
import time
from datetime import datetime

from database import SessionLocal
from models import PatientFlow


def simulate_stream(interval_seconds: int = 10):
    db = SessionLocal()
    try:
        while True:
            new_value = random.randint(50, 150)
            now = datetime.now()
            db.add(
                PatientFlow(
                    datetime=now.strftime("%Y-%m-%d %H:%M:%S"),
                    patients=float(new_value),
                    day_of_week=now.weekday(),
                    month=now.month,
                    is_weekend=1 if now.weekday() >= 5 else 0,
                    holiday=0,
                    weather=0.0,
                )
            )
            db.commit()
            print(f"New patient flow: {new_value}")
            time.sleep(interval_seconds)
    finally:
        db.close()


if __name__ == "__main__":
    simulate_stream()

def inject_custom_css():
    st.markdown(f"""
    <style>
    .streaming-indicator {{
        position: fixed;
        top: 20px;
        right: 20px;
        background: #ef4444;
        color: white;
        padding: 10px 15px;
        border-radius: 8px;
        font-weight: bold;
        animation: pulse 2s infinite;
        z-index: 9999;
    }}
    @keyframes pulse {{
        0% {{ opacity: 1; }}
        50% {{ opacity: 0.5; }}
        100% {{ opacity: 1; }}
    }}