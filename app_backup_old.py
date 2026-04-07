import os
import smtplib
from email.mime.text import MIMEText
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, session, flash
from pymongo import MongoClient
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from bson.objectid import ObjectId
from itsdangerous import URLSafeTimedSerializer # NEW: For secure email tokens

from ai_engine import calculate_resume_score

app = Flask(__name__)
app.secret_key = 'super_secret_fyp_key_replace_later'

# NEW: Initialize the token generator
serializer = URLSafeTimedSerializer(app.secret_key)

# --- Configuration ---
client = MongoClient('mongodb://localhost:27017/')
db = client['hrvision_db']  
candidates_collection = db['candidates'] 
jobs_collection = db['jobs']  
users_collection = db['users'] 

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ==========================================
# --- INITIALIZE DEFAULT SUPER ADMIN ---
# ==========================================
if not users_collection.find_one({"email": "admin@hrvision.com"}):
    users_collection.insert_one({
        "name": "Super Admin",
        "email": "admin@hrvision.com",
        "password": generate_password_hash("admin123"),
        "role": "admin",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

# ==========================================
# --- EMAIL SENDING HELPER FUNCTION ---
# ==========================================
# ==========================================
# --- EMAIL SENDING HELPER FUNCTION ---
# ==========================================
def send_reset_email(user_email, token):
    # Replace these with your actual Gmail details!
    sender_email = "2020n02892@gmail.com" 
    sender_password = "sutq vsdg zdnu zxjx" 
    
    reset_url = url_for('reset_token', token=token, _external=True)
    
    msg = MIMEText(f"Hello,\n\nTo reset your HRVision password, please click the link below:\n\n{reset_url}\n\nThis link will expire in 1 hour.\nIf you did not make this request, simply ignore this email.")
    msg['Subject'] = 'HRVision Password Reset Request'
    msg['From'] = sender_email
    msg['To'] = user_email
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, user_email, msg.as_string())
        server.quit()
        print(f"✅ Reset email sent successfully to {user_email}!")
    except Exception as e:
        print(f"❌ Failed to send email via Gmail: {e}")
        print("\n" + "="*50)
        print("🛡️ FYP FAILSAFE: OFFLINE MODE TRIGGERED")
        print(f"Copy and paste this link into your browser to reset the password:")
        print(f"{reset_url}")
        print("="*50 + "\n")

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_dynamic_file(file_obj):
    if file_obj and file_obj.filename and allowed_file(file_obj.filename):
        filename = secure_filename(file_obj.filename)
        path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file_obj.save(path)
        return filename 
    return ""

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

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
            return "Email already registered. Please login." 

        hashed_password = generate_password_hash(password)
        
        user_data = {
            "name": name,
            "email": email,
            "password": hashed_password,
            "role": "candidate",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        users_collection.insert_one(user_data)
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = users_collection.find_one({"email": email})
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = str(user['_id'])
            session['user_name'] = user['name']
            session['email'] = user['email']
            session['role'] = user['role']
            
            if user['role'] == 'admin':
                return redirect(url_for('dashboard'))
            else:
                return redirect(url_for('candidate_dashboard'))
        else:
            flash("Invalid email or password.")
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = users_collection.find_one({"email": email, "role": "admin"})
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = str(user['_id'])
            session['user_name'] = user['name']
            session['email'] = user['email']
            session['role'] = user['role']
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid Admin Credentials or Unauthorized Access.")
            return redirect(url_for('admin_login'))

    return render_template('admin_login.html')

# --- PROFESSIONAL PASSWORD RESET FLOW ---
@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = users_collection.find_one({"email": email})
        
        if user:
            # Generate a secure token with the user's email
            token = serializer.dumps(email, salt='password-reset-salt')
            send_reset_email(email, token)
            
        # We always show the same message for security (prevents email enumeration)
        flash("If an account with that email exists, a password reset link has been sent.")
        return redirect(url_for('login'))

    return render_template('forgot_password.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_token(token):
    try:
        # Token expires after 3600 seconds (1 hour)
        email = serializer.loads(token, salt='password-reset-salt', max_age=3600)
    except Exception:
        flash("The password reset link is invalid or has expired.")
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        new_password = request.form.get('new_password')
        hashed_password = generate_password_hash(new_password)
        
        users_collection.update_one(
            {"email": email},
            {"$set": {"password": hashed_password}}
        )
        flash("Your password has been successfully updated! Please log in.")
        return redirect(url_for('login'))

    return render_template('reset_with_token.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('job_board'))

# ==========================================
# --- SECURE ADMIN ROUTES ---
# ==========================================

@app.route('/')
def dashboard():
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))

    if session.get('email') == 'admin@hrvision.com':
        candidates = list(candidates_collection.find())
    else:
        my_jobs = list(jobs_collection.find({"admin_id": session['user_id']}))
        my_job_ids = [str(job['_id']) for job in my_jobs]
        candidates = list(candidates_collection.find({"applied_job_id": {"$in": my_job_ids}}))
    
    candidates.sort(key=lambda x: x.get('ai_score') if x.get('ai_score') is not None else 0, reverse=True)

    total_candidates = len(candidates)
    shortlisted = sum(1 for c in candidates if c.get("status") == "Shortlisted")
    rejected = sum(1 for c in candidates if c.get("status") == "Rejected")
    pending = total_candidates - (shortlisted + rejected)
    
    stats = {
        "total": total_candidates,
        "shortlisted": shortlisted,
        "pending": pending
    }
    
    return render_template('admin_dashboard.html', candidates=candidates, stats=stats)

@app.route('/admin/create_hr', methods=['GET', 'POST'])
def create_hr():
    if session.get('role') != 'admin' or session.get('email') != 'admin@hrvision.com':
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if users_collection.find_one({"email": email}):
            return "Email already in use."
            
        users_collection.insert_one({
            "name": name,
            "email": email,
            "password": generate_password_hash(password),
            "role": "admin", 
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        return redirect(url_for('dashboard'))
        
    return render_template('admin_create_hr.html')

@app.route('/admin/post_job')
def post_job_form():
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))
    return render_template('admin_job_post.html')

@app.route('/admin/submit_job', methods=['POST'])
def submit_job():
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        mand_skills_raw = request.form.get('mandatory_skills', '')
        opt_skills_raw = request.form.get('optional_skills', '')
        
        mandatory_skills = [s.strip() for s in mand_skills_raw.split(',') if s.strip()]
        optional_skills = [s.strip() for s in opt_skills_raw.split(',') if s.strip()]

        job_data = {
            "admin_id": session['user_id'], 
            "job_title": request.form.get('job_title'),
            "department": request.form.get('department'),
            "modality": request.form.get('modality'),
            "employment_type": request.form.get('employment_type'),
            "min_education": request.form.get('min_education'),
            "min_cgpa": float(request.form.get('min_cgpa', 0.0) or 0.0),
            "min_experience_years": float(request.form.get('min_experience', 0)),
            "requires_research_paper": request.form.get('requires_research_paper'),
            "salary_range": f"{request.form.get('salary_min')} - {request.form.get('salary_max')}",
            "mandatory_skills": mandatory_skills,
            "optional_skills": optional_skills,
            "job_description": request.form.get('job_description'),
            "status": "Open",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        jobs_collection.insert_one(job_data)
        return redirect(url_for('dashboard'))

@app.route('/admin/update_status/<candidate_id>', methods=['POST'])
def update_status(candidate_id):
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))

    new_status = request.form.get('status')
    if new_status:
        candidates_collection.update_one(
            {"_id": ObjectId(candidate_id)},
            {"$set": {"status": new_status}}
        )
    return redirect(url_for('dashboard'))

# ==========================================
# --- PUBLIC & CANDIDATE ROUTES ---
# ==========================================

@app.route('/jobs')
def job_board():
    open_jobs = list(jobs_collection.find({"status": "Open"}).sort("created_at", -1))
    return render_template('job_board.html', jobs=open_jobs)

@app.route('/candidate/dashboard')
def candidate_dashboard():
    if 'user_id' not in session or session.get('role') != 'candidate':
        return redirect(url_for('login'))
        
    applications = list(candidates_collection.find({"user_id": session['user_id']}).sort("applied_at", -1))
    return render_template('candidate_dashboard.html', applications=applications)

@app.route('/apply/<job_id>')
def apply_job(job_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    job = jobs_collection.find_one({"_id": ObjectId(job_id)})
    if not job:
        return "Job not found", 404
    return render_template('candidate_profile.html', job=job)

@app.route('/submit_profile', methods=['POST'])
def submit_profile():
    if request.method == 'POST':
        if 'user_id' not in session:
            return redirect(url_for('login'))

        applied_job_id = request.form.get('applied_job_id')
        applied_job_title = request.form.get('applied_job_title')

        resume_file = request.files.get('resume')
        profile_pic_file = request.files.get('profile_pic')
        
        resume_filename = save_dynamic_file(resume_file)
        pic_filename = save_dynamic_file(profile_pic_file)

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

        edu_levels = request.form.getlist('education_level[]')
        institutes = request.form.getlist('institute_name[]')
        degrees = request.form.getlist('degree_name[]')
        grades = request.form.getlist('grade[]')
        obtained = request.form.getlist('obtained_marks[]')
        totals = request.form.getlist('total_marks[]')
        degree_docs = request.files.getlist('degree_doc[]')
        
        education_history = []
        for i in range(len(institutes)):
            if institutes[i].strip(): 
                doc_name = save_dynamic_file(degree_docs[i]) if i < len(degree_docs) else ""
                education_history.append({
                    "level": edu_levels[i] if i < len(edu_levels) else "",
                    "institute_name": institutes[i],
                    "degree_name": degrees[i],
                    "grade": grades[i],
                    "obtained_marks": float(obtained[i]) if obtained[i] else 0,
                    "total_marks": float(totals[i]) if totals[i] else 0,
                    "document": doc_name
                })

        designations = request.form.getlist('job_designation[]')
        companies = request.form.getlist('company_name[]')
        exp_years = request.form.getlist('experience_years[]')
        exp_docs = request.files.getlist('exp_letter_doc[]')
        
        experience_history = []
        total_years_exp = 0.0
        for i in range(len(designations)):
            if designations[i].strip(): 
                years = float(exp_years[i]) if exp_years[i] else 0
                total_years_exp += years
                doc_name = save_dynamic_file(exp_docs[i]) if i < len(exp_docs) else ""
                experience_history.append({
                    "job_designation": designations[i],
                    "company_name": companies[i],
                    "years": years,
                    "document": doc_name
                })

        cert_names = request.form.getlist('cert_name[]')
        cert_orgs = request.form.getlist('cert_org[]')
        cert_docs = request.files.getlist('cert_doc[]')

        certifications = []
        for i in range(len(cert_names)):
            if cert_names[i].strip():
                doc_name = save_dynamic_file(cert_docs[i]) if i < len(cert_docs) else ""
                certifications.append({
                    "name": cert_names[i],
                    "organization": cert_orgs[i],
                    "document": doc_name
                })

        rec_names = request.form.getlist('rec_name[]')
        rec_designations = request.form.getlist('rec_designation[]')
        rec_docs = request.files.getlist('rec_doc[]')

        recommendations = []
        for i in range(len(rec_names)):
            if rec_names[i].strip():
                doc_name = save_dynamic_file(rec_docs[i]) if i < len(rec_docs) else ""
                recommendations.append({
                    "name": rec_names[i],
                    "designation": rec_designations[i],
                    "document": doc_name
                })

        titles = request.form.getlist('research_title[]')
        links = request.form.getlist('research_link[]')
        research_history = []
        for i in range(len(titles)):
            if titles[i].strip(): 
                research_history.append({"title": titles[i], "link": links[i]})

        final_ai_score = None
        target_job = None
        if applied_job_id:
            target_job = jobs_collection.find_one({"_id": ObjectId(applied_job_id)})
        
        if target_job and resume_filename:
            full_resume_path = os.path.join(app.config['UPLOAD_FOLDER'], resume_filename)
            final_ai_score = calculate_resume_score(
                resume_path=full_resume_path,
                job_description=target_job.get("job_description", ""),
                mandatory_skills=target_job.get("mandatory_skills", []),
                candidate_skills=skills_list
            )

        candidate_data = {
            "user_id": session['user_id'],          
            "applied_job_id": applied_job_id,       
            "applied_job_title": applied_job_title, 
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
            "ai_score": final_ai_score, 
            "status": "Applied",
            "applied_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        candidates_collection.insert_one(candidate_data)
        return redirect(url_for('candidate_dashboard'))

if __name__ == '__main__':
    app.run(debug=True)