from db import Base  # Import Base from your db.py file
from sqlalchemy import create_engine

DATABASE_URL = "sqlite:///./doctor_app.db"

engine = create_engine(DATABASE_URL)
Base.metadata.create_all(bind=engine)
