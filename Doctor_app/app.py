from fastapi import FastAPI, Depends, Request, HTTPException, Form, UploadFile, File
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from db import get_db,SessionLocal
from models import Doctor, Notification, Patient
from passlib.context import CryptContext
from fastapi.responses import RedirectResponse, StreamingResponse, HTMLResponse
from starlette.status import HTTP_303_SEE_OTHER
from fastapi.staticfiles import StaticFiles
from io import BytesIO
from datetime import datetime
import os
import pickle
import logging
from fpdf import FPDF
import numpy as np
import requests
from PyPDF2 import PdfReader
import re
from flask import Flask, request, render_template, redirect, url_for, flash

app = FastAPI()
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Or restrict to specific domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Secret key for session management
SECRET_KEY = "your_super_secret_key"

# Configure templates and static files
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# In-memory session storage (simulated)
active_sessions = {}

# Hash password
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

# Verify password
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

# Check login status
def is_logged_in(request: Request) -> bool:
    return request.cookies.get("session_id") in active_sessions

# Middleware to check if user is logged in and pass it to templates
@app.middleware("http")
async def add_logged_in_status(request: Request, call_next):
    request.state.logged_in = is_logged_in(request)
    response = await call_next(request)
    return response

# Root Page
@app.get("/", response_class=RedirectResponse)
def root():
    return RedirectResponse(url="/home", status_code=HTTP_303_SEE_OTHER)

# Home Page
@app.get("/home")
def home_page(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})

# Signup Page
@app.get("/signup")
def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})

@app.post("/signup")
def signup(
    username: str = Form(...),
    password: str = Form(...),
    name: str = Form(...),
    email: str = Form(...),
    qualification: str = Form(...),
    position: str = Form(...),
    db: Session = Depends(get_db)
):
    hashed_password = hash_password(password)
    new_doctor = Doctor(
        username=username,
        password=hashed_password,
        name=name,
        email=email,
        qualification=qualification,
        position=position
    )
    db.add(new_doctor)
    db.commit()
    db.refresh(new_doctor)
    return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)

# Login Page
@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    doctor = db.query(Doctor).filter(Doctor.username == username).first()
    if not doctor or not verify_password(password, doctor.password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})

    session_id = str(doctor.id)
    active_sessions[session_id] = doctor.id  # Store doctor ID in session
    response = RedirectResponse(url="/dashboard", status_code=HTTP_303_SEE_OTHER)
    response.set_cookie(key="session_id", value=session_id)  # Set cookie for session management
    return response

# Logout Route
@app.get("/logout")
def logout(request: Request):
    session_id = request.cookies.get("session_id")
    if session_id in active_sessions:
        del active_sessions[session_id]
    response = RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)
    response.delete_cookie("session_id")  # Remove session cookie
    return response

# Dashboard Page
@app.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)

    session_id = request.cookies.get("session_id")
    doctor_id = active_sessions.get(session_id)
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    notifications = db.query(Notification).filter(Notification.doctor_id == doctor_id).all()

    return templates.TemplateResponse("dashboard.html", {"request": request, "doctor": doctor, "notifications": notifications})

# Profile Page
@app.get("/profile")
def profile(request: Request, db: Session = Depends(get_db)):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)

    session_id = request.cookies.get("session_id")
    doctor_id = active_sessions.get(session_id)
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    return templates.TemplateResponse("profile.html", {"request": request, "doctor": doctor})

# API to fetch list of doctors
@app.get("/doctors")
def get_doctors(db: Session = Depends(get_db)):
    return db.query(Doctor).all()

# API to receive reports from patients
@app.post("/receive-report")
def receive_report(
    doctor_id: int = Form(...),
    patient_name: str = Form(...),
    date: str = Form(...),
    report: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    # Save the report and create a notification
    file_content = report.file.read()
    notification = Notification(
        doctor_id=doctor_id,
        patient_name=patient_name,
        date=datetime.fromisoformat(date),
        report=file_content
    )
    db.add(notification)
    db.commit()

    return {"message": "Report received successfully"}

# Download Report API
@app.get("/download-report")
def download_report(notification_id: int, db: Session = Depends(get_db)):
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    return StreamingResponse(
        BytesIO(notification.report),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=report_{notification_id}.pdf"}
    )

# Delete Notification API
@app.post("/delete-notification")
def delete_notification(notification_id: int = Form(...), db: Session = Depends(get_db)):
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    db.delete(notification)
    db.commit()

    return RedirectResponse(url="/dashboard", status_code=HTTP_303_SEE_OTHER)



columns = [
    "MDVP:Fo(Hz)", "MDVP:Fhi(Hz)", "MDVP:Flo(Hz)", "MDVP:Jitter(%)", "MDVP:Jitter(Abs)",
    "MDVP:RAP", "MDVP:PPQ", "Jitter:DDP", "MDVP:Shimmer", "MDVP:Shimmer(dB)",
    "Shimmer:APQ3", "Shimmer:APQ5", "MDVP:APQ", "Shimmer:DDA", "NHR", "HNR",
    "RPDE", "DFA", "spread1", "spread2", "D2", "PPE"
]

@app.post("/detect-text", response_class=HTMLResponse)
async def detect_text(
    request: Request,
    notification_id: int = Form(...),
    pdf_file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    detected_data = {col: "" for col in columns}

    if pdf_file.content_type != 'application/pdf':
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDF files are accepted.")

    try:
        pdf_content = await pdf_file.read()
        pdf_io = BytesIO(pdf_content)
        pdf_reader = PdfReader(pdf_io)
        text = ""

        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text

        text = text.replace('\n', ' ').strip()
        text = re.sub(r'\s+', ' ', text)

        # Log the extracted text for debugging
        logging.info(f"Extracted text: {text}")

        for column in columns:
            # Updated regex pattern to be more flexible
            pattern = rf"{re.escape(column)}\s*[:]*\s*([-+]?\d*\.\d+|\d+)"
            match = re.search(pattern, text)
            if match:
                detected_data[column] = match.group(1)

        return templates.TemplateResponse(
            "analyze_report.html",
            {
                "request": request,
                "notification_id": notification_id,
                "detected_data": detected_data
            }
        )

    except Exception as e:
        logging.error(f"Error processing file: {e}")
        raise HTTPException(status_code=500, detail="An error occurred while processing the PDF file.")
# Analyze Report Route
@app.post("/analyze-report", response_class=HTMLResponse)
async def analyze_report(
    request: Request,
    notification_id: int = Form(...),
    db: Session = Depends(get_db)
):
    # Fetch the notification from the database
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    # Use PyPDF2 to extract text from the report
    pdf_reader = PdfReader(BytesIO(notification.report))
    detected_text = ""
    for page in pdf_reader.pages:
        detected_text += page.extract_text() + "\n"

    return templates.TemplateResponse(
        "analyze_report.html",
        {
            "request": request,
            "notification_id": notification_id,
            "detected_data": detected_text
        }
    )

import joblib
model = joblib.load('model.pkl')
# Final Report Generation
@app.post("/final-report")
async def final_report(
    request: Request,
    notification_id: int = Form(...),
    mdvp_fo: float = Form(...),
    mdvp_fhi: float = Form(...),
    mdvp_flo: float = Form(...),
    mdvp_jitter: float = Form(...),
    mdvp_jitter_abs: float = Form(...),
    mdvp_rap: float = Form(...),
    mdvp_ppq: float = Form(...),
    jitter_ddp: float = Form(...),
    mdvp_shimmer: float = Form(...),
    mdvp_shimmer_db: float = Form(...),
    shimmer_apq3: float = Form(...),
    shimmer_apq5: float = Form(...),
    mdvp_apq: float = Form(...),
    shimmer_dda: float = Form(...),
    nhr: float = Form(...),
    hnr: float = Form(...),
    rpde: float = Form(...),
    dfa: float = Form(...),
    spread1: float = Form(...),
    spread2: float = Form(...),
    d2: float = Form(...),
    ppe: float = Form(...),
    db: Session = Depends(get_db)
):
    # Get session ID and doctor ID
    session_id = request.cookies.get("session_id")
    doctor_id = active_sessions.get(session_id)

    if not doctor_id:
        raise HTTPException(status_code=403, detail="User not logged in")

    # Retrieve notification to get patient name and ID
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    patient_name = notification.patient_name
    patient_id = notification.id  # Assuming you have this in the Notification model
    doctor_name = db.query(Doctor).filter(Doctor.id == doctor_id).first().name  # Retrieve doctor name
    report_filename = f"{patient_name.replace(' ', '_')}_parkinsons_report.pdf"
    report_path = f"static/final_reports/{report_filename}"

    # Prepare input for prediction
    input_features = np.array([[mdvp_fo, mdvp_fhi, mdvp_flo, mdvp_jitter, mdvp_jitter_abs,
                                mdvp_rap, mdvp_ppq, jitter_ddp, mdvp_shimmer,
                                mdvp_shimmer_db, shimmer_apq3, shimmer_apq5,
                                mdvp_apq, shimmer_dda, nhr, hnr, rpde, dfa,
                                spread1, spread2, d2, ppe]])

    # Perform prediction
    prediction = model.predict(input_features)
    prediction_result = "Positive" if prediction[0] == 1 else "Negative"

    # Generate and save report
    # Generate and save report
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    # Center the title
    pdf.cell(0, 10, "Parkinson Disease Detection Report", ln=True, align='C')
    pdf.ln(10)  # Add a line break for spacing

    # Add patient name
    pdf.cell(0, 10, f"Patient Name: {patient_name}", ln=True)
    pdf.cell(0, 10, f"Prediction Result: {prediction_result}", ln=True)
    pdf.cell(0, 10, f"Report by: Dr. {doctor_name}", ln=True, align='R')
    pdf.ln(10)  # Line break for spacing

    # Add input feature values
    pdf.cell(0, 10, f"MDVP:Fo(Hz): {mdvp_fo}", ln=True)
    pdf.cell(0, 10, f"MDVP:Fhi(Hz): {mdvp_fhi}", ln=True)
    pdf.cell(0, 10, f"MDVP:Flo(Hz): {mdvp_flo}", ln=True)
    pdf.cell(0, 10, f"MDVP:Jitter(%): {mdvp_jitter}", ln=True)
    pdf.cell(0, 10, f"MDVP:Jitter(Abs): {mdvp_jitter_abs}", ln=True)
    pdf.cell(0, 10, f"MDVP:RAP: {mdvp_rap}", ln=True)
    pdf.cell(0, 10, f"MDVP:PPQ: {mdvp_ppq}", ln=True)
    pdf.cell(0, 10, f"Jitter:DDP: {jitter_ddp}", ln=True)
    pdf.cell(0, 10, f"MDVP:Shimmer: {mdvp_shimmer}", ln=True)
    pdf.cell(0, 10, f"MDVP:Shimmer(dB): {mdvp_shimmer_db}", ln=True)
    pdf.cell(0, 10, f"Shimmer:APQ3: {shimmer_apq3}", ln=True)
    pdf.cell(0, 10, f"Shimmer:APQ5: {shimmer_apq5}", ln=True)
    pdf.cell(0, 10, f"MDVP:APQ: {mdvp_apq}", ln=True)
    pdf.cell(0, 10, f"Shimmer:DDA: {shimmer_dda}", ln=True)
    pdf.cell(0, 10, f"NHR: {nhr}", ln=True)
    pdf.cell(0, 10, f"HNR: {hnr}", ln=True)
    pdf.cell(0, 10, f"RPDE: {rpde}", ln=True)
    pdf.cell(0, 10, f"DFA: {dfa}", ln=True)
    pdf.cell(0, 10, f"Spread1: {spread1}", ln=True)
    pdf.cell(0, 10, f"Spread2: {spread2}", ln=True)
    pdf.cell(0, 10, f"D2: {d2}", ln=True)
    pdf.cell(0, 10, f"PPE: {ppe}", ln=True)
    # Save the PDF to the specified path
    pdf.output(report_path)

    # Here you can store the report info in the database if needed

    # Prepare the list of generated reports
    reports = [f for f in os.listdir("static/final_reports") if f.endswith(".pdf")]

    # Render the final report HTML page
    return templates.TemplateResponse("final_report.html", {
        "request": request,
        "patient": {"name": patient_name},
        "prediction": prediction_result,
        "reports": reports
    })

# PATIENT_APP_URL = "http://localhost:5002/receive_report"  # Patient app URL

@app.route('/send_to_patient', methods=['POST'])
def send_to_patient():
    # Accessing form data from the request
    patient_username = request.form.get('patient_username')
    selected_report = request.form.get('report')

    if not patient_username or not selected_report:
        flash("Patient username and selected report must be provided.", "danger")
        return redirect(url_for('final_report', username=patient_username))

    report_path = f"static/final_reports/{selected_report}"

    if not os.path.isfile(report_path):
        flash("The selected report file does not exist.", "danger")
        return redirect(url_for('final_report', username=patient_username))

    patient_api_url = "http://localhost:5002/patient/receive_report"

    with open(report_path, 'rb') as report_file:
        files = {'report': report_file}
        data = {
            'patient_username': patient_username,
            'report_filename': selected_report
        }
        try:
            response = requests.post(patient_api_url, files=files, data=data)
            if response.status_code == 200:
                flash("Report sent to patient successfully!", "success")
                
                # Create notification after successfully sending the report
                create_notification(patient_username, selected_report)
                
            else:
                flash("Failed to send report to patient.", "danger")
        except requests.exceptions.RequestException as e:
            flash(f"An error occurred while sending the report: {e}", "danger")

    return redirect(url_for('final_report', username=patient_username))

def create_notification(patient_username, report_filename):
    # Assuming you have access to the database session here
    db: Session = SessionLocal()
    
    # Find the patient by username
    patient = db.query(Patient).filter(Patient.name == patient_username).first()
    if patient:
        notification = Notification(
            doctor_id=None,  # Set this if you have doctor ID available
            patient_id=patient.id,
            patient_name=patient.username,
            date=datetime.now(),
            report=report_filename.encode()  # Store the filename as the report content
        )
        db.add(notification)
        db.commit()
