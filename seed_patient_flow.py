import pandas as pd
from database import SessionLocal
from models import PatientFlow


def safe_int(value):
    if pd.isna(value):
        return None
    return int(value)


def safe_float(value):
    if pd.isna(value):
        return None
    return float(value)


def main():
    df = pd.read_csv("clean_data.csv")
    db = SessionLocal()

    try:
        for _, row in df.iterrows():
            record = PatientFlow(
                datetime=str(row["datetime"]) if "datetime" in df.columns and pd.notna(row["datetime"]) else None,
                patients=safe_float(row.get("patients")),
                day_of_week=safe_int(row.get("day_of_week")),
                month=safe_int(row.get("month")),
                is_weekend=safe_int(row.get("is_weekend")),
                holiday=safe_int(row.get("holiday")),
                weather=safe_float(row.get("weather")),
            )
            db.add(record)

        db.commit()
        print("Data imported to database")
    except Exception as e:
        db.rollback()
        print("Error importing patient flow:", e)
    finally:
        db.close()


if __name__ == "__main__":
    main()