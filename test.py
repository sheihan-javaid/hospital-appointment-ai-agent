from database import SessionLocal, Doctor, init_db

init_db()  # creates tables + seeds doctors

db = SessionLocal()
print(db.query(Doctor).all())
db.close()