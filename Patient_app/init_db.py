from sqlalchemy import create_engine
from db import Base  # Ensure Base is imported correctly from your db.py

# Database URL for SQLite database
DATABASE_URL = "sqlite:///./patients_app.db"

# Create an engine instance
engine = create_engine(DATABASE_URL)

# Create all tables in the database
Base.metadata.create_all(bind=engine)

print("Database tables created successfully.")

