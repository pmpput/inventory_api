# database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# เช่นบน Cloud จะตั้งประมาณ:
# postgresql://user:password@host:5432/inventory_db
DATABASE_URL = os.getenv("postgresql://inventory_db_kypm_user:ny2sJD9A9UfV9Px1tOPU55HkE3ph86LH@dpg-d4lbiqeuk2gs738ablng-a.singapore-postgres.render.com/inventory_db_kypm")

if not DATABASE_URL:
    # ถ้าอยากให้ dev บนเครื่องมี default ก็ใส่ตรงนี้ เช่นใช้ SQLite ชั่วคราว
    # DATABASE_URL = "sqlite:///./inventory.db"
    # หรือถ้าคุณยังอยากใช้ PostgreSQL local บน Mac:
    # DATABASE_URL = "postgresql://postgres@localhost:5432/inventory_db"
    raise RuntimeError("DATABASE_URL is not set in environment variables")

# สร้าง engine จาก URL (ใช้กับ PostgreSQL บน Cloud ได้เลย)
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,   # กัน connection ตายเมื่อ idle นาน (มีประโยชน์บน Cloud)
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Dependency สำหรับ FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
