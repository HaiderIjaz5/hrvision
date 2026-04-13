import os
import smtplib
from email.mime.text import MIMEText
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, session, flash, Response
from pymongo import MongoClient
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.exceptions import RequestEntityTooLarge
from datetime import datetime
from bson.objectid import ObjectId
from itsdangerous import URLSafeTimedSerializer 
import csv
from io import StringIO
import PyPDF2
import docx
from dotenv import load_dotenv
import requests

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
# Securely load the secret key
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'default_fallback_key')
serializer = URLSafeTimedSerializer(app.secret_key)

# ==========================================
# --- DATABASE CONFIGURATION ---
# ==========================================
mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
client = MongoClient(mongo_uri)
db = client['hrvision_db']  
candidates_collection = db['candidates'] 
jobs_collection = db['jobs']  
users_collection = db['users'] 
profiles_collection = db['profiles']

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# NEW: Limit uploads to 10 Megabytes maximum
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024 

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# Initialize Super Admin if not exists
if not users_collection.find_one({"email": "admin@hrvision.com"}):
    users_collection.insert_one({
        "name": "Super Admin",
        "email": "admin@hrvision.com",
        "password": generate_password_hash("admin123"),
        "role": "admin",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

# ==========================================
# --- EMAIL ENGINE FUNCTIONS ---
# ==========================================
# Securely load email credentials
MY_EMAIL = os.getenv('MAIL_USERNAME')
MY_APP_PASSWORD = os.getenv('MAIL_PASSWORD')

def send_application_receipt_email(candidate_email, candidate_name, job_title):
    subject = f"Application Received: {job_title}"
    body = f"Dear {candidate_name},\n\nThank you for applying for the {job_title} position at HRVision.\n\nWe have successfully received your application and resume. Our AI screening engine and recruitment team will review your profile shortly. You can track your application status anytime through your Candidate Dashboard.\n\nBest regards,\nHRVision Talent Acquisition"
    
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = MY_EMAIL
    msg['To'] = candidate_email
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
        server.starttls()
        server.login(MY_EMAIL, MY_APP_PASSWORD)
        server.sendmail(MY_EMAIL, candidate_email, msg.as_string())
        server.quit()
        print(f"✅ Automated Application Receipt Email Sent to {candidate_email}")
    except Exception as e:
        print(f"❌ Failed to send application receipt email: {e}")

def send_reset_email(user_email, token):
    reset_url = url_for('reset_token', token=token, _external=True)
    msg = MIMEText(f"Hello,\n\nTo reset your HRVision password, please click the link below:\n\n{reset_url}\n\nThis link will expire in 1 hour.")
    msg['Subject'] = 'HRVision Password Reset Request'
    msg['From'] = MY_EMAIL
    msg['To'] = user_email
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
        server.starttls()
        server.login(MY_EMAIL, MY_APP_PASSWORD)
        server.sendmail(MY_EMAIL, user_email, msg.as_string())
        server.quit()
    except Exception as e:
        print(f"❌ Failed to send reset email: {e}")

def send_contact_email(user_name, user_email, user_message):
    receiver_email = MY_EMAIL 
    msg = MIMEText(f"New Contact Form Submission from HRVision!\n\nName: {user_name}\nEmail: {user_email}\n\nMessage:\n{user_message}")
    msg['Subject'] = f'HRVision Contact: Message from {user_name}'
    msg['From'] = MY_EMAIL
    msg['To'] = receiver_email
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
        server.starttls()
        server.login(MY_EMAIL, MY_APP_PASSWORD)
        server.sendmail(MY_EMAIL, receiver_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        return False

def send_status_email(candidate_email, candidate_name, job_title, new_status, hr_name, interview_details=None):
    if new_status == 'Shortlisted':
        subject = f"Congratulations! You've been shortlisted for {job_title}"
        body = f"Dear {candidate_name},\n\nGreat news! The HRVision AI and our recruitment team have reviewed your profile, and we are thrilled to inform you that you have been shortlisted for the {job_title} position.\n\nOur team will be in touch shortly regarding the next steps.\n\nBest regards,\n{hr_name}\nHRVision Talent Acquisition"
    
    elif new_status == 'Interviewing':
        subject = f"Interview Invitation: {job_title} at HRVision"
        body = f"Dear {candidate_name},\n\nFollowing a review of your exceptional profile, we would like to formally invite you to an interview for the {job_title} role.\n\n"
        
        # --- NEW: DYNAMIC INTERVIEW DETAILS ---
        if interview_details:
            if interview_details.get('inform_later') == 'true':
                body += "Our team is currently finalizing the schedule. We will be reaching out to you very soon with the exact date, time, and venue/meeting link for your interview.\n\n"
            else:
                body += f"Here are your interview details:\n"
                body += f"📅 Date: {interview_details.get('date', 'TBD')}\n"
                body += f"⏰ Time: {interview_details.get('time', 'TBD')}\n"
                body += f"📍 Venue/Link: {interview_details.get('venue', 'TBD')}\n\n"
                
        body += f"Please reply to this email to confirm your availability.\n\nBest regards,\n{hr_name}\nHRVision Talent Acquisition"
    elif new_status == 'Hired':
        subject = f"Job Offer: {job_title} at HRVision"
        body = f"Dear {candidate_name},\n\nCongratulations! After a thorough review and interview process, we are absolutely thrilled to offer you the position of {job_title} at HRVision.\n\nOur HR team will be reaching out to you shortly with your official offer letter and onboarding details.\n\nWelcome to the team!\n\nBest regards,\n{hr_name}\nHRVision Talent Acquisition"   
    elif new_status == 'Rejected':
        subject = f"Update on your application for {job_title}"
        body = f"Dear {candidate_name},\n\nThank you for applying for the {job_title} position. \n\nWhile your background is impressive, we have decided to move forward with other candidates whose profiles more closely align with the specific needs of this role at this time.\n\nWe wish you the best in your career search.\n\nSincerely,\n{hr_name}\nHRVision Talent Acquisition"
    else:
        return 
        
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = MY_EMAIL
    msg['To'] = candidate_email
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
        server.starttls()
        server.login(MY_EMAIL, MY_APP_PASSWORD)
        server.sendmail(MY_EMAIL, candidate_email, msg.as_string())
        server.quit()
        print(f"✅ Automated Email Sent to {candidate_email} for status: {new_status}")
    except Exception as e:
        print(f"❌ Failed to send status email: {e}")
    

# ==========================================
# --- FILE HANDLING ---
# ==========================================
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_dynamic_file(file_obj):
    if file_obj and file_obj.filename and allowed_file(file_obj.filename):
        filename = secure_filename(file_obj.filename)
        path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file_obj.save(path)
        return filename 
    return ""

def extract_text_from_file(filepath):
    text = ""
    try:
        ext = filepath.rsplit('.', 1)[1].lower()
        if ext == 'pdf':
            with open(filepath, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text += page.extract_text() + "\n"
        elif ext in ['doc', 'docx']:
            doc = docx.Document(filepath)
            for para in doc.paragraphs:
                text += para.text + "\n"
    except Exception as e:
        print(f"Error extracting JD text: {e}")
    return text.strip()

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.errorhandler(RequestEntityTooLarge)
def handle_file_size_error(e):
    flash("Upload failed: File size exceeds the 10MB limit. Please compress your document.")
    # Redirect them back to where they came from
    return redirect(request.referrer or url_for('index'))

# ==========================================
# --- STATIC PUBLIC ROUTES ---
# ==========================================
@app.route('/home') 
def my_custom_home():   # <--- THIS IS THE MAGIC WORD!
    return render_template('index.html')

@app.route('/')
def root():
    # Replace 'my_custom_home' with whatever your function is actually named!
    return redirect(url_for('my_custom_home'))

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        message = request.form.get('message')
        success = send_contact_email(name, email, message)
        if success:
            flash("Thank you for reaching out! Our team will get back to you shortly.")
        else:
            flash("Oops! Our mail server is currently busy. Please try again later.")
        return redirect(url_for('contact'))
    return render_template('contact.html')

# ==========================================
# --- AUTHENTICATION ROUTES ---
# ==========================================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')

        if users_collection.find_one({"email": email}):
            flash("Email already registered. Please login.")
            return redirect(url_for('login'))

        hashed_password = generate_password_hash(password)
        user_data = {
            "name": name, "email": email, "password": hashed_password,
            "role": "candidate", "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        users_collection.insert_one(user_data)
        flash("Account created successfully! Please log in.")
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('role') == 'candidate':
        return redirect(url_for('candidate_dashboard'))
    elif session.get('role') == 'admin':
        return redirect(url_for('admin_dashboard'))

    if request.method == 'GET':
        next_page = request.args.get('next')
        if next_page:
            session['next_url'] = next_page

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = users_collection.find_one({"email": email, "role": "candidate"})
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = str(user['_id'])
            session['user_name'] = user['name']
            session['email'] = user['email']
            session['role'] = user['role']
            next_url = session.pop('next_url', url_for('candidate_dashboard'))
            return redirect(next_url)
        else:
            is_admin = users_collection.find_one({"email": email, "role": "admin"})
            if is_admin:
                flash("Administrators must use the secure Admin Portal to log in.")
            else:
                flash("Invalid email or password.")
            return redirect(url_for('login'))
            
    return render_template('login.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('role') == 'admin':
        return redirect(url_for('admin_dashboard'))

    if request.method == 'GET':
        next_page = request.args.get('next')
        if next_page:
            session['next_url'] = next_page

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = users_collection.find_one({"email": email, "role": "admin"})
        if user and check_password_hash(user['password'], password):
            session['user_id'] = str(user['_id'])
            session['user_name'] = user['name']
            session['email'] = user['email']
            session['role'] = user['role']
            next_url = session.pop('next_url', url_for('admin_dashboard'))
            return redirect(next_url)
        else:
            flash("Invalid Admin Credentials or Unauthorized Access.")
            return redirect(url_for('admin_login'))
            
    return render_template('admin_login.html')

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = users_collection.find_one({"email": email})
        if user:
            token = serializer.dumps(email, salt='password-reset-salt')
            send_reset_email(email, token)
        flash("If an account with that email exists, a password reset link has been sent.")
        return redirect(url_for('login'))
    return render_template('forgot_password.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_token(token):
    try:
        email = serializer.loads(token, salt='password-reset-salt', max_age=3600)
    except Exception:
        flash("The password reset link is invalid or has expired.")
        return redirect(url_for('forgot_password'))
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        hashed_password = generate_password_hash(new_password)
        users_collection.update_one({"email": email}, {"$set": {"password": hashed_password}})
        flash("Your password has been successfully updated! Please log in.")
        return redirect(url_for('login'))
    return render_template('reset_with_token.html')

@app.route('/logout')
def logout():
    user_role = session.get('role')
    session.clear()
    previous_page = request.referrer
    if user_role == 'admin':
        flash("You have securely logged out of the Admin Portal.")
    if previous_page:
        return redirect(previous_page)
    return redirect(url_for('index'))

# ==========================================
# --- SECURE ADMIN ROUTES ---
# ==========================================
@app.route('/admin/dashboard')
def admin_dashboard():
    if session.get('role') != 'admin':
        session['next_url'] = request.url
        return redirect(url_for('admin_login'))

    if session.get('email') == 'admin@hrvision.com':
        candidates = list(candidates_collection.find())
    else:
        my_jobs = list(jobs_collection.find({"admin_id": session['user_id']}))
        my_job_ids = [str(job['_id']) for job in my_jobs]
        candidates = list(candidates_collection.find({"applied_job_id": {"$in": my_job_ids}}))
    
    status_counts = {'Applied': 0, 'Shortlisted': 0, 'Interviewing': 0, 'Hired': 0, 'Rejected': 0}
    job_popularity = {}

    for c in candidates:
        job = jobs_collection.find_one({"_id": ObjectId(c.get("applied_job_id"))})
        if job:
            admin_name = job.get('admin_name')
            if not admin_name:
                admin_user = users_collection.find_one({"_id": ObjectId(job.get("admin_id"))})
                admin_name = admin_user['name'] if admin_user else "Super Admin"
            c['real_admin_name'] = admin_name
            job_title = job.get('job_title', 'Unknown Job')
            job_popularity[job_title] = job_popularity.get(job_title, 0) + 1
        else:
            c['real_admin_name'] = "Deleted Job"

        status = c.get("status", "Applied")
        if status in status_counts:
            status_counts[status] += 1
        else:
            status_counts['Applied'] += 1

    candidates.sort(key=lambda x: x.get('ai_score') if x.get('ai_score') is not None else 0, reverse=True)
    stats = {
        "total": len(candidates),
        "shortlisted": status_counts.get('Shortlisted', 0),
        "interviewing": status_counts.get('Interviewing', 0),
        "pending": status_counts.get('Applied', 0),
        "status_labels": list(status_counts.keys()),
        "status_values": list(status_counts.values()),
        "job_labels": list(job_popularity.keys()),
        "job_values": list(job_popularity.values())
    }
    return render_template('admin_dashboard.html', candidates=candidates, stats=stats)

@app.route('/admin/jobs')
def manage_jobs():
    if session.get('role') != 'admin':
        session['next_url'] = request.url
        return redirect(url_for('admin_login'))
    if session.get('email') == 'admin@hrvision.com':
        my_jobs = list(jobs_collection.find().sort("created_at", -1))
    else:
        my_jobs = list(jobs_collection.find({"admin_id": session['user_id']}).sort("created_at", -1))
    return render_template('admin_manage_jobs.html', jobs=my_jobs)

@app.route('/admin/export_csv')
def export_csv():
    if session.get('role') != 'admin':
        session['next_url'] = request.url
        return redirect(url_for('admin_login'))
        
    if session.get('email') == 'admin@hrvision.com':
        candidates = list(candidates_collection.find())
    else:
        my_jobs = list(jobs_collection.find({"admin_id": session['user_id']}))
        my_job_ids = [str(job['_id']) for job in my_jobs]
        candidates = list(candidates_collection.find({"applied_job_id": {"$in": my_job_ids}}))
    candidates.sort(key=lambda x: x.get('ai_score') if x.get('ai_score') is not None else 0, reverse=True)

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Candidate Name', 'Email Address', 'Phone Number', 'Target Job', 'AI Match Score (%)', 'Current Status', 'Date Applied', 'Resume Link', 'Education Documents', 'Experience Letters', 'Certifications', 'Research Links'])
    base_url = request.host_url.rstrip('/')
    for c in candidates:
        name = f"{c.get('personal_info', {}).get('first_name', '')} {c.get('personal_info', {}).get('last_name', '')}"
        email = c.get('contact_info', {}).get('email', '')
        phone = c.get('contact_info', {}).get('phone', '')
        job_title = c.get('applied_job_title', 'N/A')
        score = c.get('ai_score', 'Pending')
        status = c.get('status', 'Applied')
        applied_at = c.get('applied_at', '')
        resume_link = f"{base_url}/uploads/{c.get('resume_filename')}" if c.get('resume_filename') else "Not Provided"
        edu_docs = [f"{edu.get('degree_name')}: {base_url}/uploads/{edu.get('document')}" for edu in c.get('education', []) if edu.get('document')]
        edu_links = "\n".join(edu_docs) if edu_docs else "No Documents"
        exp_docs = [f"{exp.get('company_name')}: {base_url}/uploads/{exp.get('document')}" for exp in c.get('experience', []) if exp.get('document')]
        exp_links = "\n".join(exp_docs) if exp_docs else "No Documents"
        cert_docs = [f"{cert.get('name')}: {base_url}/uploads/{cert.get('document')}" for cert in c.get('certifications', []) if cert.get('document')]
        cert_links = "\n".join(cert_docs) if cert_docs else "No Documents"
        res_docs = [f"{res.get('title')}: {res.get('link')}" for res in c.get('research', []) if res.get('link')]
        res_links = "\n".join(res_docs) if res_docs else "No Links"
        cw.writerow([name, email, phone, job_title, score, status, applied_at, resume_link, edu_links, exp_links, cert_links, res_links])
    
    output = si.getvalue()
    return Response(output, mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=HRVision_Candidates_Export.csv"})

@app.route('/admin/create_hr', methods=['GET', 'POST'])
def create_hr():
    if session.get('role') != 'admin' or session.get('email') != 'admin@hrvision.com':
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        if users_collection.find_one({"email": email}):
            return "Email already in use."
        users_collection.insert_one({
            "name": name, "email": email, "password": generate_password_hash(password),
            "role": "admin", "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        return redirect(url_for('admin_dashboard'))
    return render_template('admin_create_hr.html')

@app.route('/admin/post_job')
def post_job_form():
    if session.get('role') != 'admin':
        session['next_url'] = request.url
        return redirect(url_for('admin_login'))
    return render_template('admin_job_post.html')

@app.route('/admin/submit_job', methods=['POST'])
def submit_job():
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        mand_skills = [s.strip() for s in request.form.get('mandatory_skills', '').split(',') if s.strip()]
        opt_skills = [s.strip() for s in request.form.get('optional_skills', '').split(',') if s.strip()]

        job_description_text = request.form.get('job_description', '')
        jd_file = request.files.get('jd_file')
        jd_filename = save_dynamic_file(jd_file) if jd_file and allowed_file(jd_file.filename) else ""
        if jd_filename:
            extracted_text = extract_text_from_file(os.path.join(app.config['UPLOAD_FOLDER'], jd_filename))
            if extracted_text:
                job_description_text = extracted_text + "\n\n" + job_description_text

        exp_years = float(request.form.get('min_experience_years', 0) or 0)
        exp_months = float(request.form.get('min_experience_months', 0) or 0)
        total_min_exp = round(exp_years + (exp_months / 12.0), 1)

        job_data = {
            "admin_id": session['user_id'], 
            "admin_name": session.get('user_name'),
            "job_title": request.form.get('job_title'),
            "department": request.form.get('department'),
            "location": request.form.get('location', 'Not Specified'),
            "modality": request.form.get('modality'),
            "employment_type": request.form.get('employment_type'),
            "deadline": request.form.get('deadline'),
            "min_education": request.form.get('min_education'),
            "min_cgpa": float(request.form.get('min_cgpa', 0.0) or 0.0),
            "min_experience_years": total_min_exp,
            "requires_research_paper": request.form.get('requires_research_paper'),
            "salary_range": f"{request.form.get('salary_min')} - {request.form.get('salary_max')}",
            "mandatory_skills": mand_skills,
            "optional_skills": opt_skills,
            "job_description": job_description_text,
            "jd_filename": jd_filename,
            "status": "Open",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        jobs_collection.insert_one(job_data)
        flash("Job Posted Successfully!")
        return redirect(url_for('manage_jobs'))

@app.route('/admin/edit_job/<job_id>', methods=['GET', 'POST'])
def edit_job(job_id):
    if session.get('role') != 'admin':
        session['next_url'] = request.url
        return redirect(url_for('admin_login'))

    job = jobs_collection.find_one({"_id": ObjectId(job_id)})
    if not job:
        flash("Job not found.")
        return redirect(url_for('manage_jobs'))

    if session.get('email') != 'admin@hrvision.com' and job.get('admin_id') != session['user_id']:
        flash("Unauthorized: You can only edit your own job postings.")
        return redirect(url_for('manage_jobs'))

    if request.method == 'POST':
        mand_skills = [s.strip() for s in request.form.get('mandatory_skills', '').split(',') if s.strip()]
        opt_skills = [s.strip() for s in request.form.get('optional_skills', '').split(',') if s.strip()]

        job_description_text = request.form.get('job_description', '')
        jd_file = request.files.get('jd_file')
        jd_filename = request.form.get('existing_jd_filename', '')

        if jd_file and allowed_file(jd_file.filename):
            jd_filename = save_dynamic_file(jd_file)
            full_jd_path = os.path.join(app.config['UPLOAD_FOLDER'], jd_filename)
            extracted_text = extract_text_from_file(full_jd_path)
            if extracted_text:
                job_description_text = extracted_text + "\n\n" + job_description_text

        exp_years = float(request.form.get('min_experience_years', 0) or 0)
        exp_months = float(request.form.get('min_experience_months', 0) or 0)
        total_min_exp = round(exp_years + (exp_months / 12.0), 1)

        update_data = {
            "job_title": request.form.get('job_title'),
            "department": request.form.get('department'),
            "location": request.form.get('location', 'Not Specified'),
            "modality": request.form.get('modality'),
            "employment_type": request.form.get('employment_type'),
            "deadline": request.form.get('deadline'),
            "min_education": request.form.get('min_education'),
            "min_cgpa": float(request.form.get('min_cgpa', 0.0) or 0.0),
            "min_experience_years": total_min_exp,
            "requires_research_paper": request.form.get('requires_research_paper'),
            "salary_range": f"{request.form.get('salary_min')} - {request.form.get('salary_max')}",
            "mandatory_skills": mand_skills, 
            "optional_skills": opt_skills,  
            "job_description": job_description_text,
            "jd_filename": jd_filename
        }
        
        jobs_collection.update_one({"_id": ObjectId(job_id)}, {"$set": update_data})
        flash("Job details updated successfully!")
        return redirect(url_for('manage_jobs'))

    return render_template('admin_edit_job.html', job=job)

@app.route('/admin/update_job_status/<job_id>', methods=['POST'])
def update_job_status(job_id):
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))
    
    job = jobs_collection.find_one({"_id": ObjectId(job_id)})
    if session.get('email') != 'admin@hrvision.com' and job.get('admin_id') != session['user_id']:
        flash("Unauthorized: Cannot update jobs you did not post.")
        return redirect(url_for('manage_jobs'))

    new_status = request.form.get('status')
    if new_status:
        jobs_collection.update_one({"_id": ObjectId(job_id)}, {"$set": {"status": new_status}})
        flash(f"Job status changed to {new_status}.")
    return redirect(url_for('manage_jobs'))

@app.route('/admin/delete_job/<job_id>', methods=['POST'])
def delete_job(job_id):
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))
    
    job = jobs_collection.find_one({"_id": ObjectId(job_id)})
    if session.get('email') != 'admin@hrvision.com' and job.get('admin_id') != session['user_id']:
        flash("Unauthorized: Cannot delete jobs you did not post.")
        return redirect(url_for('manage_jobs'))

    jobs_collection.delete_one({"_id": ObjectId(job_id)})
    flash("Job posting permanently deleted.")
    return redirect(url_for('manage_jobs'))

@app.route('/admin/update_status/<candidate_id>', methods=['POST'])
def update_status(candidate_id):
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))
        
    new_status = request.form.get('status')
    if new_status:
        candidate = candidates_collection.find_one({"_id": ObjectId(candidate_id)})
        if candidate:
            candidates_collection.update_one({"_id": ObjectId(candidate_id)}, {"$set": {"status": new_status}})
            
            c_name = candidate.get('personal_info', {}).get('first_name', 'Candidate')
            c_email = candidate.get('contact_info', {}).get('email')
            j_title = candidate.get('applied_job_title', 'a position')
            hr_name = candidate.get('applied_job_admin_name', session.get('user_name', 'HR Team'))
            
            # --- NEW: EXTRACT INTERVIEW DETAILS ---
            interview_details = None
            if new_status == 'Interviewing':
                interview_details = {
                    "date": request.form.get('interview_date'),
                    "time": request.form.get('interview_time'),
                    "venue": request.form.get('interview_venue'),
                    "inform_later": request.form.get('inform_later')
                }
            
            if c_email and new_status in ['Shortlisted', 'Interviewing', 'Rejected', 'Hired']:
                # Pass the interview_details to the email function!
                send_status_email(c_email, c_name, j_title, new_status, hr_name, interview_details)
                
            flash(f"Candidate Status successfully updated to '{new_status}' and email notification sent!")
        else:
            flash("Candidate not found.")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_candidate/<candidate_id>', methods=['POST'])
def delete_candidate(candidate_id):
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))

    candidate = candidates_collection.find_one({"_id": ObjectId(candidate_id)})
    if not candidate:
        flash("Candidate not found.")
        return redirect(url_for('admin_dashboard'))

    if session.get('email') == 'admin@hrvision.com':
        candidates_collection.delete_one({"_id": ObjectId(candidate_id)})
        flash("Candidate permanently deleted from database.")
    else:
        job = jobs_collection.find_one({"_id": ObjectId(candidate.get("applied_job_id"))})
        if job and job.get("admin_id") == session.get('user_id'):
            candidates_collection.delete_one({"_id": ObjectId(candidate_id)})
            flash("Candidate permanently deleted from your job listing.")
        else:
            flash("Unauthorized: You do not have permission to delete this candidate.")
    
    return redirect(url_for('admin_dashboard'))

# ==========================================
# --- CANDIDATE ROUTES ---
# ==========================================
@app.route('/jobs')
def job_board():
    open_jobs = list(jobs_collection.find({"status": "Open"}).sort("created_at", -1))
    
    # Pass a list of saved jobs to the frontend so the bookmark buttons light up!
    saved_job_ids = []
    if session.get('role') == 'candidate':
        profile = profiles_collection.find_one({"user_id": session['user_id']})
        if profile:
            saved_job_ids = profile.get('saved_jobs', [])
            
    return render_template('job_board.html', jobs=open_jobs, saved_job_ids=saved_job_ids)

@app.route('/job_details/<job_id>')
def job_details(job_id):
    try:
        job = jobs_collection.find_one({"_id": ObjectId(job_id)})
        if not job:
            flash("Job not found or has been removed.")
            return redirect(url_for('job_board'))
        return render_template('job_details.html', job=job)
    except Exception:
        flash("Invalid Job ID.")
        return redirect(url_for('job_board'))

@app.route('/candidate/dashboard')
def candidate_dashboard():
    if 'user_id' not in session or session.get('role') != 'candidate':
        session['next_url'] = request.url
        return redirect(url_for('login'))
        
    applications = list(candidates_collection.find({"user_id": session['user_id']}).sort("applied_at", -1))

    for application in applications:
        job_id = application.get('applied_job_id')
        if job_id and job_id != 'MASTER':
            try:
                job = jobs_collection.find_one({"_id": ObjectId(job_id)})
                application['job_deadline'] = job.get('deadline', 'N/A') if job else 'Closed/Deleted'
            except Exception:
                application['job_deadline'] = 'Unknown'
        else:
            application['job_deadline'] = 'N/A'
    
    profile = profiles_collection.find_one({"user_id": session['user_id']})
    saved_job_ids = profile.get('saved_jobs', []) if profile else []
    
    # Convert string IDs back to ObjectIds to query the jobs collection
    obj_ids = [ObjectId(j_id) for j_id in saved_job_ids if ObjectId.is_valid(j_id)]
    saved_jobs = list(jobs_collection.find({"_id": {"$in": obj_ids}}))

    return render_template('candidate_dashboard.html', applications=applications, saved_jobs=saved_jobs)

@app.route('/candidate/settings', methods=['GET', 'POST'])
def candidate_settings():
    if 'user_id' not in session or session.get('role') != 'candidate':
        session['next_url'] = request.url
        return redirect(url_for('login'))

    user = users_collection.find_one({"_id": ObjectId(session['user_id'])})

    if request.method == 'POST':
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if new_password != confirm_password:
            flash("New passwords do not match.")
            return redirect(url_for('candidate_settings'))

        if check_password_hash(user['password'], old_password):
            hashed_password = generate_password_hash(new_password)
            users_collection.update_one(
                {"_id": ObjectId(session['user_id'])},
                {"$set": {"password": hashed_password}}
            )
            flash("Password updated successfully! ✅")
        else:
            flash("Incorrect current password.")
        return redirect(url_for('candidate_settings'))

    return render_template('candidate_settings.html', user=user)

@app.route('/candidate/my_profile')
def my_profile():
    if 'user_id' not in session or session.get('role') != 'candidate':
        session['next_url'] = request.url
        return redirect(url_for('login'))
        
    existing_profile = profiles_collection.find_one({"user_id": session['user_id']})
    
    if not existing_profile:
        existing_profile = candidates_collection.find_one({"user_id": session['user_id']}, sort=[("applied_at", -1)])
        
    return render_template('candidate_profile.html', job=None, profile=existing_profile)

@app.route('/apply/<job_id>')
def apply_job(job_id):
    if 'user_id' not in session:
        session['next_url'] = request.url 
        return redirect(url_for('login'))

    has_applied = candidates_collection.find_one({
        "user_id": session['user_id'],
        "applied_job_id": job_id
    })
    
    if has_applied:
        flash("You have already applied for this position! You can track your status below.")
        return redirect(url_for('candidate_dashboard'))

    job = jobs_collection.find_one({"_id": ObjectId(job_id)})
    if not job:
        return "Job not found", 404
        
    existing_profile = profiles_collection.find_one({"user_id": session['user_id']})
    if not existing_profile:
        existing_profile = candidates_collection.find_one({"user_id": session['user_id']}, sort=[("applied_at", -1)])

    return render_template('candidate_profile.html', job=job, profile=existing_profile)

@app.route('/save_job/<job_id>', methods=['POST'])
def save_job(job_id):
    if 'user_id' not in session or session.get('role') != 'candidate':
        return {"status": "error", "message": "Unauthorized"}, 401
    
    user_id = session['user_id']
    profile = profiles_collection.find_one({"user_id": user_id})
    saved_jobs = profile.get("saved_jobs", []) if profile else []
    
    if job_id in saved_jobs:
        saved_jobs.remove(job_id) # Unsave if already saved
        action = "unsaved"
    else:
        saved_jobs.append(job_id) # Save it
        action = "saved"
        
    profiles_collection.update_one(
        {"user_id": user_id},
        {"$set": {"saved_jobs": saved_jobs}},
        upsert=True
    )
    return {"status": "success", "action": action}

@app.route('/submit_profile', methods=['POST'])
def submit_profile():
    if request.method == 'POST':
        if 'user_id' not in session:
            return redirect(url_for('login'))

        applied_job_id = request.form.get('applied_job_id')
        
        if applied_job_id != 'MASTER':
            if candidates_collection.find_one({"user_id": session['user_id'], "applied_job_id": applied_job_id}):
                flash("Application blocked. You have already applied for this role.")
                return redirect(url_for('candidate_dashboard'))

            applied_job_title = request.form.get('applied_job_title')
            target_job = jobs_collection.find_one({"_id": ObjectId(applied_job_id)})
            applied_job_admin_name = target_job.get("admin_name", "HR Team") if target_job else "HR Team"
        else:
            target_job = None
            applied_job_title = "Master Profile"
            applied_job_admin_name = "N/A"

        resume_file = request.files.get('resume')
        profile_pic_file = request.files.get('profile_pic')
        
        resume_filename = save_dynamic_file(resume_file) or request.form.get('existing_resume', '')
        pic_filename = save_dynamic_file(profile_pic_file) or request.form.get('existing_profile_pic', '')

        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        dob = request.form.get('dob')
        gender = request.form.get('gender')
        nationality = request.form.get('nationality')
        email = request.form.get('email')
        phone = request.form.get('phone')
        street_address = request.form.get('street_address')
        city = request.form.get('city')
        state = request.form.get('state')
        zip_code = request.form.get('zip_code')
        country = request.form.get('country')
        linkedin_url = request.form.get('linkedin_url')
        portfolio_url = request.form.get('portfolio_url')
        skills_raw = request.form.get('skills', '')
        skills_list = [skill.strip() for skill in skills_raw.split(',') if skill.strip()]

        # --- PROCESS EDUCATION ARRAYS ---
        edu_levels = request.form.getlist('education_level[]')
        institutes = request.form.getlist('institute_name[]')
        degrees = request.form.getlist('degree_name[]')
        grades = request.form.getlist('grade[]')
        obtained = request.form.getlist('obtained_marks[]')
        totals = request.form.getlist('total_marks[]')
        degree_docs = request.files.getlist('degree_doc[]')
        existing_degree_docs = request.form.getlist('existing_degree_doc[]') 
        
        education_history = []
        for i in range(len(institutes)):
            if institutes[i].strip(): 
                new_file = degree_docs[i] if i < len(degree_docs) else None
                existing_file = existing_degree_docs[i] if i < len(existing_degree_docs) else ""
                doc_name = save_dynamic_file(new_file) or existing_file
                education_history.append({
                    "level": edu_levels[i] if i < len(edu_levels) else "",
                    "institute_name": institutes[i],
                    "degree_name": degrees[i],
                    "grade": grades[i],
                    "obtained_marks": float(obtained[i]) if obtained[i] else 0,
                    "total_marks": float(totals[i]) if totals[i] else 0,
                    "document": doc_name
                })

        # --- PROCESS EXPERIENCE ARRAYS (WITH DATE CALCULATIONS) ---
        # --- PROCESS EXPERIENCE ARRAYS (WITH DATE CALCULATIONS) ---
        designations = request.form.getlist('job_designation[]')
        companies = request.form.getlist('company_name[]')
        exp_statuses = request.form.getlist('exp_status[]')
        start_dates = request.form.getlist('exp_start_date[]')
        end_dates = request.form.getlist('exp_end_date[]')
        
        # --- NEW FIELDS ---
        locations = request.form.getlist('exp_location[]')
        modalities = request.form.getlist('exp_modality[]')
        emp_types = request.form.getlist('exp_type[]')
        
        exp_docs = request.files.getlist('exp_letter_doc[]')
        existing_exp_docs = request.form.getlist('existing_exp_doc[]') 
        
        experience_history = []
        total_years_exp = 0.0
        
        for i in range(len(designations)):
            if designations[i].strip(): 
                start_str = start_dates[i] if i < len(start_dates) else ""
                status = exp_statuses[i] if i < len(exp_statuses) else "Completed"
                end_str = end_dates[i] if i < len(end_dates) else ""
                
                exp_years_calc = 0.0
                if start_str:
                    try:
                        start_dt = datetime.strptime(start_str, '%Y-%m')
                        if status == 'Current': 
                            end_dt = datetime.now()
                        else: 
                            end_dt = datetime.strptime(end_str, '%Y-%m') if end_str else datetime.now()
                        
                        diff_days = (end_dt - start_dt).days
                        exp_years_calc = max(0.0, round(diff_days / 365.25, 1))
                    except Exception as e:
                        print("Date parse error", e)
                
                total_years_exp += exp_years_calc

                new_file = exp_docs[i] if i < len(exp_docs) else None
                existing_file = existing_exp_docs[i] if i < len(existing_exp_docs) else ""
                doc_name = save_dynamic_file(new_file) or existing_file
                experience_history.append({
                    "job_designation": designations[i],
                    "company_name": companies[i],
                    "location": locations[i] if i < len(locations) else "",            # <--- NEW
                    "modality": modalities[i] if i < len(modalities) else "",          # <--- NEW
                    "employment_type": emp_types[i] if i < len(emp_types) else "",     # <--- NEW
                    "start_date": start_str,
                    "end_date": "" if status == 'Current' else end_str,
                    "status": status,
                    "years": exp_years_calc,
                    "document": doc_name
                })

        # --- PROCESS CERTIFICATIONS ARRAYS ---
        cert_names = request.form.getlist('cert_name[]')
        cert_orgs = request.form.getlist('cert_org[]')
        cert_docs = request.files.getlist('cert_doc[]')
        existing_cert_docs = request.form.getlist('existing_cert_doc[]') 

        certifications = []
        for i in range(len(cert_names)):
            if cert_names[i].strip():
                new_file = cert_docs[i] if i < len(cert_docs) else None
                existing_file = existing_cert_docs[i] if i < len(existing_cert_docs) else ""
                doc_name = save_dynamic_file(new_file) or existing_file
                certifications.append({
                    "name": cert_names[i],
                    "organization": cert_orgs[i],
                    "document": doc_name
                })

        # --- PROCESS RECOMMENDATIONS ARRAYS ---
        rec_names = request.form.getlist('rec_name[]')
        rec_designations = request.form.getlist('rec_designation[]')
        rec_docs = request.files.getlist('rec_doc[]')
        existing_rec_docs = request.form.getlist('existing_rec_doc[]') 

        recommendations = []
        for i in range(len(rec_names)):
            if rec_names[i].strip():
                new_file = rec_docs[i] if i < len(rec_docs) else None
                existing_file = existing_rec_docs[i] if i < len(existing_rec_docs) else ""
                doc_name = save_dynamic_file(new_file) or existing_file
                recommendations.append({
                    "name": rec_names[i],
                    "designation": rec_designations[i],
                    "document": doc_name
                })

        # --- PROCESS RESEARCH ARRAYS ---
        titles = request.form.getlist('research_title[]')
        links = request.form.getlist('research_link[]')
        research_history = []
        for i in range(len(titles)):
            if titles[i].strip(): 
                research_history.append({"title": titles[i], "link": links[i]})

        # --- BUILD MASTER PROFILE DICTIONARY ---
        master_profile_data = {
            "user_id": session['user_id'],
            "personal_info": {
                "first_name": first_name, "last_name": last_name, "dob": dob,
                "gender": gender, "nationality": nationality, "profile_pic": pic_filename
            },
            "contact_info": {
                "email": email, "phone": phone,
                "address": {"street": street_address, "city": city, "state": state, "zip_code": zip_code, "country": country}
            },
            "professional_links": {"linkedin": linkedin_url, "portfolio": portfolio_url},
            "education": education_history,       
            "experience": experience_history,     
            "total_experience_years": total_years_exp,
            "certifications": certifications,     
            "recommendations": recommendations,   
            "research": research_history,         
            "skills": skills_list,
            "resume_filename": resume_filename,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # ALWAYS update the master profile database so it is always current
        profiles_collection.update_one(
            {"user_id": session['user_id']},
            {"$set": master_profile_data},
            upsert=True
        )

        # If they were ONLY updating their master profile, stop here!
        if applied_job_id == 'MASTER':
            flash("Your Master Profile has been updated successfully! It will automatically fill future job applications.")
            return redirect(url_for('candidate_dashboard'))

# --- EXPLAINABLE AI INTEGRATION (MICROSERVICE CALL) ---
        final_ai_score = None
        matched_skills = []
        missing_skills = []
        
        if target_job and resume_filename:
            full_resume_path = os.path.join(app.config['UPLOAD_FOLDER'], resume_filename)
            
            # 1. We MUST extract the text from the PDF before sending it!
            candidate_full_text = extract_text_from_file(full_resume_path)
            
            try:
                # 🛑 CONNECTING TO YOUR NEW HUGGING FACE SERVER 🛑
                ai_server_url = "https://haiderijaz-hrvision-ai-engine.hf.space/api/score"
                
                # 2. Send the text to Hugging Face to do the heavy math
                response = requests.post(ai_server_url, json={
                    "resume_text": candidate_full_text,
                    "job_description": target_job.get("job_description", ""),
                    "mandatory_skills": target_job.get("mandatory_skills", []),
                    "candidate_skills": skills_list
                }, timeout=30)
                
                # 3. Catch the answer coming back from Hugging Face!
                if response.status_code == 200:
                    ai_results = response.json()
                    final_ai_score = ai_results.get("ai_score")
                    matched_skills = ai_results.get("matched", [])
                    missing_skills = ai_results.get("missing", [])
                else:
                    print(f"AI Server returned an error: {response.status_code}")
                    final_ai_score = 0.0
                    
            except Exception as e:
                # 4. The except block catches crashes if Hugging Face is asleep
                print(f"Failed to connect to AI Server: {e}")
                final_ai_score = 0.0

        # Create the specific Job Application data block
        candidate_data = master_profile_data.copy()
        candidate_data["applied_job_id"] = applied_job_id
        candidate_data["applied_job_title"] = applied_job_title
        candidate_data["applied_job_admin_name"] = applied_job_admin_name
        candidate_data["ai_score"] = final_ai_score
        
        candidate_data["matched_skills"] = matched_skills  
        candidate_data["missing_skills"] = missing_skills  
        
        candidate_data["status"] = "Applied"
        candidate_data["applied_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        candidate_data.pop("updated_at", None) 

        candidates_collection.insert_one(candidate_data)
        send_application_receipt_email(email, first_name, applied_job_title)
        
        flash("Application submitted successfully!")
        return redirect(url_for('candidate_dashboard'))

if __name__ == '__main__':
    # Use the port Render provides, or default to 5000 locally
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)