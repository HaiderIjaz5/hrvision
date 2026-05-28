import os
import requests
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash

from config import jobs_collection, profiles_collection, candidates_collection, users_collection, UPLOAD_FOLDER
from utils import save_dynamic_file, extract_text_from_file, send_application_receipt_email

candidate_bp = Blueprint('candidate', __name__)

@candidate_bp.route('/jobs')
def job_board():
    all_open_jobs = list(jobs_collection.find({"status": "Open"}).sort("created_at", -1))
    today_str = datetime.now().strftime('%Y-%m-%d')
    valid_jobs = []
    
    for job in all_open_jobs:
        deadline = job.get('deadline', '')
        if not deadline or deadline >= today_str:
            valid_jobs.append(job)

    saved_job_ids = []
    if session.get('role') == 'candidate':
        profile = profiles_collection.find_one({"user_id": session['user_id']})
        if profile:
            saved_job_ids = profile.get('saved_jobs', [])
            
    return render_template('job_board.html', jobs=valid_jobs, saved_job_ids=saved_job_ids)

@candidate_bp.route('/job_details/<job_id>')
def job_details(job_id):
    try:
        job = jobs_collection.find_one({"_id": ObjectId(job_id)})
        if not job:
            flash("Job not found or has been removed.")
            return redirect(request.referrer or url_for('candidate.job_board'))
            
        deadline = job.get('deadline', '')
        today_str = datetime.now().strftime('%Y-%m-%d')
        
        if deadline and deadline < today_str:
            flash("Sorry, the deadline to apply for this position has passed.", "flash-error")
            return redirect(request.referrer or url_for('candidate.job_board'))
            
        return render_template('job_details.html', job=job)
    except Exception:
        flash("Invalid Job ID.")
        return redirect(request.referrer or url_for('candidate.job_board'))

@candidate_bp.route('/candidate/dashboard')
def candidate_dashboard():
    if 'user_id' not in session or session.get('role') != 'candidate':
        session['next_url'] = request.url
        return redirect(url_for('auth.login'))
        
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
    
    obj_ids = [ObjectId(j_id) for j_id in saved_job_ids if ObjectId.is_valid(j_id)]
    saved_jobs = list(jobs_collection.find({"_id": {"$in": obj_ids}}))

    return render_template('candidate_dashboard.html', applications=applications, saved_jobs=saved_jobs)

@candidate_bp.route('/candidate/settings', methods=['GET', 'POST'])
def candidate_settings():
    if 'user_id' not in session or session.get('role') != 'candidate':
        session['next_url'] = request.url
        return redirect(url_for('auth.login'))

    user = users_collection.find_one({"_id": ObjectId(session['user_id'])})

    if request.method == 'POST':
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if new_password != confirm_password:
            flash("New passwords do not match.", "error")
            return redirect(url_for('candidate.candidate_settings'))

        if check_password_hash(user['password'], old_password):
            hashed_password = generate_password_hash(new_password)
            users_collection.update_one(
                {"_id": ObjectId(session['user_id'])},
                {"$set": {"password": hashed_password}}
            )
            flash("Password updated successfully! ✅")
        else:
            flash("Incorrect current password.", "error")
        return redirect(url_for('candidate.candidate_settings'))

    return render_template('candidate_settings.html', user=user)

@candidate_bp.route('/candidate/my_profile')
def my_profile():
    if 'user_id' not in session or session.get('role') != 'candidate':
        session['next_url'] = request.url
        # FIX: Added 'auth.' prefix to avoid a BuildError
        return redirect(url_for('auth.login')) 
        
    existing_profile = profiles_collection.find_one({"user_id": session['user_id']})
    
    # FIX: If the profile exists but only contains 'saved_jobs', ignore it
    if existing_profile and 'personal_info' not in existing_profile:
        existing_profile = None
    
    if not existing_profile:
        existing_profile = candidates_collection.find_one({"user_id": session['user_id']}, sort=[("applied_at", -1)])
        
    return render_template('candidate_profile.html', job=None, profile=existing_profile)

@candidate_bp.route('/apply/<job_id>')
def apply_job(job_id):
    if 'user_id' not in session:
        session['next_url'] = request.url 
        return redirect(url_for('auth.login'))

    has_applied = candidates_collection.find_one({
        "user_id": session['user_id'],
        "applied_job_id": job_id
    })
    
    if has_applied:
        flash("You have already applied for this position! You can track your status below.")
        return redirect(url_for('candidate.candidate_dashboard'))

    job = jobs_collection.find_one({"_id": ObjectId(job_id)})
    if not job:
        flash("Job not found or has been removed.")
        return redirect(url_for('candidate.job_board'))
        
    deadline = job.get('deadline', '')
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    if deadline and deadline < today_str:
        flash("Sorry, the deadline to apply for this position has passed.", "flash-error")
        return redirect(url_for('candidate.job_board'))
        
    existing_profile = profiles_collection.find_one({"user_id": session['user_id']})
    
    # FIX: If the profile exists but only contains 'saved_jobs', ignore it
    if existing_profile and 'personal_info' not in existing_profile:
        existing_profile = None

    if not existing_profile:
        existing_profile = candidates_collection.find_one({"user_id": session['user_id']}, sort=[("applied_at", -1)])

    return render_template('candidate_profile.html', job=job, profile=existing_profile)

@candidate_bp.route('/save_job/<job_id>', methods=['POST'])
def save_job(job_id):
    if 'user_id' not in session or session.get('role') != 'candidate':
        return {"status": "error", "message": "Unauthorized"}, 401
    
    user_id = session['user_id']
    profile = profiles_collection.find_one({"user_id": user_id})
    saved_jobs = profile.get("saved_jobs", []) if profile else []
    
    if job_id in saved_jobs:
        saved_jobs.remove(job_id) 
        action = "unsaved"
    else:
        saved_jobs.append(job_id) 
        action = "saved"
        
    profiles_collection.update_one(
        {"user_id": user_id},
        {"$set": {"saved_jobs": saved_jobs}},
        upsert=True
    )
    return {"status": "success", "action": action}

@candidate_bp.route('/submit_profile', methods=['POST'])
def submit_profile():
    if request.method == 'POST':
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))

        applied_job_id = request.form.get('applied_job_id')
        
        if applied_job_id != 'MASTER':
            if candidates_collection.find_one({"user_id": session['user_id'], "applied_job_id": applied_job_id}):
                flash("Application blocked. You have already applied for this role.")
                return redirect(url_for('candidate.candidate_dashboard'))

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

        cnic_front_file = request.files.get('cnic_front')
        cnic_back_file = request.files.get('cnic_back')
        domicile_file = request.files.get('domicile')

        cnic_front_filename = save_dynamic_file(cnic_front_file) or request.form.get('existing_cnic_front', '')
        cnic_back_filename = save_dynamic_file(cnic_back_file) or request.form.get('existing_cnic_back', '')
        domicile_filename = save_dynamic_file(domicile_file) or request.form.get('existing_domicile', '')

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

        designations = request.form.getlist('job_designation[]')
        companies = request.form.getlist('company_name[]')
        exp_statuses = request.form.getlist('exp_status[]')
        start_dates = request.form.getlist('exp_start_date[]')
        end_dates = request.form.getlist('exp_end_date[]')
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
                        # FIX: Alert the user that their dates couldn't be parsed properly
                        flash(f"Warning: Could not calculate experience duration for '{designations[i]}'. Please ensure dates are in YYYY-MM format.", "error")
                
                total_years_exp += exp_years_calc

                new_file = exp_docs[i] if i < len(exp_docs) else None
                existing_file = existing_exp_docs[i] if i < len(existing_exp_docs) else ""
                doc_name = save_dynamic_file(new_file) or existing_file
                experience_history.append({
                    "job_designation": designations[i],
                    "company_name": companies[i],
                    "location": locations[i] if i < len(locations) else "",
                    "modality": modalities[i] if i < len(modalities) else "",
                    "employment_type": emp_types[i] if i < len(emp_types) else "",
                    "start_date": start_str,
                    "end_date": "" if status == 'Current' else end_str,
                    "status": status,
                    "years": exp_years_calc,
                    "document": doc_name
                })

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

        titles = request.form.getlist('research_title[]')
        links = request.form.getlist('research_link[]')
        research_history = []
        for i in range(len(titles)):
            if titles[i].strip(): 
                research_history.append({"title": titles[i], "link": links[i]})

        master_profile_data = {
            "user_id": session['user_id'],
            "personal_info": {
                "first_name": first_name, 
                "last_name": last_name, 
                "dob": dob,
                "gender": gender, 
                "nationality": nationality, 
                "profile_pic": pic_filename,
                "cnic_front": cnic_front_filename,
                "cnic_back": cnic_back_filename,
                "domicile": domicile_filename
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

        profiles_collection.update_one(
            {"user_id": session['user_id']},
            {"$set": master_profile_data},
            upsert=True
        )

        if applied_job_id == 'MASTER':
            flash("Your Master Profile has been updated successfully! It will automatically fill future job applications.")
            return redirect(url_for('candidate.candidate_dashboard'))

        if target_job:
            education_rank = {"High School": 1, "Intermediate": 2, "Bachelors": 3, "Masters": 4, "PhD": 5}
            job_min_edu = target_job.get("min_education", "")
            job_edu_rank = education_rank.get(job_min_edu, 0)
            
            candidate_max_edu_rank = 0
            for edu in education_history:
                rank = education_rank.get(edu.get("level", ""), 0)
                if rank > candidate_max_edu_rank:
                    candidate_max_edu_rank = rank
                    
            if job_edu_rank > 0 and candidate_max_edu_rank < job_edu_rank:
                flash(f"Application blocked: This position strictly requires a minimum education level of {job_min_edu}.","flash-error")
                return redirect(url_for('candidate.job_board'))
                
            job_min_exp = float(target_job.get("min_experience_years", 0.0))
            if total_years_exp < job_min_exp:
                flash(f"Application blocked: This position requires a minimum of {job_min_exp} years of professional experience.","flash-error")
                return redirect(url_for('candidate.job_board'))

            job_requires_research = str(target_job.get("requires_research_paper", "No")).strip().lower()
            if job_requires_research == "yes" and len(research_history) == 0:
                flash("Application blocked: This position strictly requires at least one published research paper or project link.","flash-error")
                return redirect(url_for('candidate.job_board'))

        final_ai_score = None
        matched_skills = []
        missing_skills = []
        
        if target_job and resume_filename:
            full_resume_path = os.path.join(UPLOAD_FOLDER, resume_filename)
            IS_ON_RENDER = os.environ.get('RENDER') == 'true'
            
            if IS_ON_RENDER:
                print("☁️ App is on Render: Delegating heavy AI math to Hugging Face microservice...")
                candidate_full_text = extract_text_from_file(full_resume_path)
                try:
                    ai_server_url = "https://haiderijaz-hrvision-ai-engine.hf.space/api/score"
                    response = requests.post(ai_server_url, json={
                        "resume_text": candidate_full_text,
                        "job_description": target_job.get("job_description", ""),
                        "mandatory_skills": target_job.get("mandatory_skills", []),
                        "candidate_skills": skills_list
                    }, timeout=30)
                    
                    if response.status_code == 200:
                        ai_results = response.json()
                        final_ai_score = ai_results.get("ai_score")
                        matched_skills = ai_results.get("matched", [])
                        missing_skills = ai_results.get("missing", [])
                    else:
                        print(f"❌ AI Server returned an error: {response.status_code}")
                        final_ai_score = 0.0
                except requests.exceptions.Timeout:
                    print("⏳ Hugging Face AI Server timed out (likely waking up).")
                    final_ai_score = 0.0
                    flash("Note: The AI screening engine is currently waking up. Your profile has been submitted and will be reviewed manually.", "info")
                except Exception as e:
                    print(f"❌ Failed to connect to Hugging Face AI Server: {e}")
                    final_ai_score = 0.0
                    flash("Note: AI screening is currently unavailable. Your application has been saved for manual HR review.", "info")
            else:
                print("💻 App is running Locally: Using local ai_engine.py...")
                try:
                    from ai_engine import calculate_resume_score
                    final_ai_score, matched_skills, missing_skills = calculate_resume_score(
                        resume_path=full_resume_path,
                        job_description=target_job.get("job_description", ""),
                        mandatory_skills=target_job.get("mandatory_skills", []),
                        candidate_skills=skills_list
                    )
                except Exception as e:
                    print(f"❌ Local AI Processing Error: {e}")
                    final_ai_score = 0.0

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
        return redirect(url_for('candidate.candidate_dashboard'))