# util/database.py
import os
from datetime import datetime, timedelta
import logging

from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import JSONB


def get_secret(name, file_var):
    if value := os.getenv(name):
        return value
    if file_path := os.getenv(file_var):
        with open(file_path) as f:
            return f.read().strip()
    raise RuntimeError(f"{name} not found")

db_password = get_secret("POSTGRES_PASSWORD", "POSTGRES_PASSWORD_FILE")
                               
db_user = os.getenv("POSTGRES_USER")
db_name = os.getenv("POSTGRES_DB")
db_host = os.getenv("POSTGRES_HOST")
db_port = os.getenv("POSTGRES_PORT")

DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

engine = create_engine(DATABASE_URL, echo=False) 
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class LogEntry(Base):
    __tablename__ = "logs"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    event_type = Column(String, index=True)
    author_id = Column(String)
    author_name = Column(String)
    description = Column(String)
    guild_id = Column(String, index=True)
    details = Column(JSONB, nullable=True)

def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        logging.info("Database tables ensured to be created (or already exist).")
    except Exception as e:
        logging.error(f"Error creating database tables: {e}")

def get_db_session():
    return SessionLocal()