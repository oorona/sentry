# util/database.py
import os
from datetime import datetime, timedelta
import logging
logger = logging.getLogger(__name__)

from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import JSONB


def get_secret(name, file_var):
    # 1) Prefer direct env var
    if value := os.getenv(name):
        return value

    # 2) Next, check explicit file env var (e.g. POSTGRES_PASSWORD_FILE)
    if file_path := os.getenv(file_var):
        try:
            with open(file_path) as f:
                return f.read().strip()
        except Exception:
            pass

    # 3) Finally, check Docker secrets default location (/run/secrets/<secret_name>)
    # Try a few common name variants
    candidates = [f"/run/secrets/{name.lower()}", f"/run/secrets/{name}"]
    for path in candidates:
        try:
            if os.path.exists(path):
                with open(path) as f:
                    return f.read().strip()
        except Exception:
            continue

    raise RuntimeError(f"{name} not found")

db_password = get_secret("POSTGRES_PASSWORD", "POSTGRES_PASSWORD_FILE")
                               
db_user = os.getenv("POSTGRES_USER")
db_name = os.getenv("POSTGRES_DB")
# Defaults: container name/service is typically 'postgres-db' on the compose network; default port 5432
db_host = os.getenv("POSTGRES_HOST", "postgres-db")
db_port = os.getenv("POSTGRES_PORT", "5432")

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
        logger.info("Database tables ensured to be created (or already exist).")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")

def get_db_session():
    return SessionLocal()