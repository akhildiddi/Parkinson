from fastapi import FastAPI, Depends, Request, Form, File, UploadFile
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from db import get_db,SessionLocal, engine
from models import Patient
import requests
from passlib.context import CryptContext
from fastapi.responses import RedirectResponse, HTMLResponse
from starlette.status import HTTP_303_SEE_OTHER
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from datetime import datetime
from models import FinalReport
from models import Notification
app = FastAPI()
import os
# Mount the static directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Add session middleware
app.add_middleware(SessionMiddleware, secret_key="your_secret_key")

templates = Jinja2Templates(directory="templates")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Hash a password
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

# Verify a password
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

# Function to get user logged in status
def get_user_logged_in_status(request: Request) -> bool:
    return request.session.get('user_id') is not None

# Root Page (Homepage)
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    user_logged_in = get_user_logged_in_status(request)
    return templates.TemplateResponse("home.html", {"request": request, "user_logged_in": user_logged_in})

# Signup Page
@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    user_logged_in = get_user_logged_in_status(request)
    return templates.TemplateResponse("signup.html", {"request": request, "user_logged_in": user_logged_in})

@app.post("/signup")
def signup(
    request: Request, 
    username: str = Form(...), 
    password: str = Form(...), 
    email: str = Form(...), 
    db: Session = Depends(get_db)
):
    hashed_password = hash_password(password)
    patient = Patient(username=username, password=hashed_password, email=email)
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)

# Login Page
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    flash_message = request.session.get('flash_message', None)
    request.session.pop('flash_message', None)  # Remove the message after displaying it
    user_logged_in = get_user_logged_in_status(request)
    return templates.TemplateResponse("login.html", {"request": request, "user_logged_in": user_logged_in, "flash_message": flash_message})

@app.post("/login")
def login(
    request: Request, 
    username: str = Form(...), 
    password: str = Form(...), 
    db: Session = Depends(get_db)
):
    patient = db.query(Patient).filter(Patient.username == username).first()
    if not patient or not verify_password(password, patient.password):
        request.session['flash_message'] = "Invalid username or password"
        return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)
    
    # Create a session
    request.session['user_id'] = patient.id
    return RedirectResponse(url="/dashboard", status_code=HTTP_303_SEE_OTHER)

# Dashboard Page
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    if not get_user_logged_in_status(request):
        return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)

    try:
        # Fetch doctors from the doctor app running on port 5001
        response = requests.get("http://localhost:5001/doctors")
        doctors = response.json()
    except requests.RequestException:
        doctors = []

    patient_id = request.session.get('user_id')
    notifications = db.query(Notification).filter(Notification.patient_id == patient_id).all()

    user_logged_in = get_user_logged_in_status(request)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "doctors": doctors,
        "user_logged_in": user_logged_in,
        "notifications": notifications
    })


# Send Report to Doctor Page
@app.get("/send-report", response_class=HTMLResponse)
def send_report_page(request: Request):
    doctor_id = request.query_params.get("doctor_id")
    user_logged_in = get_user_logged_in_status(request)
    return templates.TemplateResponse("send_report.html", {"request": request, "doctor_id": doctor_id, "user_logged_in": user_logged_in})

@app.post("/send-report")
async def send_report(
    request: Request,
    doctor_id: int = Form(...),
    report: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    # Read the file contents
    file_content = await report.read()
    patient_id = request.session.get('user_id')
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    patient_name = patient.username  # Updated to `username` since `name` might not be a field in `Patient`

    # Send the report to the doctor
    try:
        response = requests.post(
            "http://localhost:5001/receive-report",
            data={
                "doctor_id": doctor_id,
                "patient_name": patient_name,
                "date": datetime.now().isoformat()
            },
            files={"report": ("report", file_content, "application/octet-stream")}
        )
        response.raise_for_status()
    except requests.RequestException:
        return {"error": "Failed to send report"}

    return RedirectResponse(url="/dashboard", status_code=HTTP_303_SEE_OTHER)


# Profile Page
@app.get("/profile", response_class=HTMLResponse)
def profile(request: Request, db: Session = Depends(get_db)):
    if not get_user_logged_in_status(request):
        return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)

    patient_id = request.session.get('user_id')
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    user_logged_in = get_user_logged_in_status(request)
    return templates.TemplateResponse("profile.html", {"request": request, "patient": patient, "user_logged_in": user_logged_in})

# Logout
@app.get("/logout")
def logout(request: Request):
    request.session.pop('user_id', None)
    return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)

from fastapi import FastAPI, HTTPException

from pydantic import BaseModel
class ReportData(BaseModel):
    id: int
    report: str
    
@app.get("/patient/notifications")
async def get_notifications(patient_username: str):
    db: Session = SessionLocal()
    
    # Find the patient by username
    patient = db.query(Patient).filter(Patient.username == patient_username).first()
    if not patient:
        return {"error": "Patient not found"}
    
    notifications = db.query(Notification).filter(Notification.patient_id == patient.id).all()
    
    return notifications

UPLOAD_DIR = "static/final_reports/"


@app.post("/patient/receive_report")
async def receive_report(
    patient_username: str = Form(...),
    report: UploadFile = File(...)
):
    report_filename = report.filename  # Get the filename from the UploadFile object

    # Path to save the uploaded report
    report_path = os.path.join(UPLOAD_DIR, report_filename)

    # Ensure the upload directory exists
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # Open the path in binary write mode and save the file contents
    with open(report_path, "wb") as buffer:
        buffer.write(await report.read())  # Directly write the file content

    # Add the final report entry to the database
    db: Session = SessionLocal()

    # Find the patient by username
    patient = db.query(Patient).filter(Patient.username == patient_username).first()
    if not patient:
        return {"error": "Patient not found"}

    # Create the new FinalReport entry
    new_report = FinalReport(
        patient_id=patient.id,
        report_filename=report_filename,
        created_at=datetime.now()
    )
    db.add(new_report)

    # Add notification for the patient
    notification = Notification(
        doctor_id=None,  # Assuming the report might come from the system
        patient_id=patient.id,
        patient_name=patient.username,
        date=datetime.now(),
        report=report_filename.encode()  # Store the filename as the report content
    )
    db.add(notification)

    # Commit changes to the database
    db.commit()

    return {"message": "Report received and saved successfully"}

