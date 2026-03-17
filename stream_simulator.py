import time
import random
from database import SessionLocal
from models import PatientFlow


def simulate_stream():
    db = SessionLocal()

    try:
        while True:
            new_value = random.randint(50, 150)

            db.add(PatientFlow(patients=new_value))
            db.commit()

            print(f"New patient flow: {new_value}")

            time.sleep(10)  # كل 10 ثواني
    finally:
        db.close()


if __name__ == "__main__":
    simulate_stream()