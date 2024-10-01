from sqlalchemy import Column, Integer, String, ForeignKey, Text , BLOB, DateTime
from db import Base
from sqlalchemy.orm import relationship
class Doctor(Base):
    __tablename__ = "doctors"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)
    name = Column(String)
    email = Column(String, unique=True)
    qualification = Column(String)
    position = Column(String)
    profile_pic = Column(BLOB)

class Notification(Base):
    __tablename__ = "notifications"
    
    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer)
    patient_name = Column(String)
    date = Column(DateTime)
    report = Column(String)

class Patient(Base):
    __tablename__ = 'patients'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    prediction = Column(Text, nullable=True)

    reports = relationship("PatientReport", back_populates="patient")


class PatientReport(Base):
    __tablename__ = 'patient_reports'

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey('patients.id'), nullable=False)
    report = Column(Text, nullable=False)

    patient = relationship("Patient", back_populates="reports")