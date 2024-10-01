from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, BLOB
from db import Base
from sqlalchemy.orm import relationship


class Patient(Base):
    __tablename__ = "patients"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)
    email = Column(String, unique=True)

    
class FinalReport(Base):
    __tablename__ = 'final_reports'

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey('patients.id'), nullable=False)
    report_filename = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False)

    patient = relationship("Patient")


class Notification(Base):
    __tablename__ = "notifications"
    
    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey('doctors.id'))
    patient_id = Column(Integer, ForeignKey('patients.id'))  # Add this line
    patient_name = Column(String)
    date = Column(DateTime)
    report = Column(BLOB) 