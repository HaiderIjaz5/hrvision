import os
import csv
from io import StringIO
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, Response
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash

from config import candidates_collection, jobs_collection, users_collection, profiles_collection, UPLOAD_FOLDER
from utils import send_status_email, save_dynamic_file, extract_text_from_file, allowed_file

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin/dashboard')
def admin_dashboard():
    if session.get('role') != 'admin':
        session['next_url'] = request.url
        return redirect(url_for('auth.admin_login'))

    if session.get('email') == os.getenv("DEFAULT_ADMIN_EMAIL"):
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


@admin_bp.route('/admin/jobs')
def manage_jobs():
    if session.get('role') != 'admin':
        session['next_url'] = request.url
        return redirect(url_for('auth.admin_login'))
    if session.get('email') == os.getenv("DEFAULT_ADMIN_EMAIL"):
        my_jobs = list(jobs_collection.find().sort("created_at", -1))
    else:
        my_jobs = list(jobs_collection.find({"admin_id": session['user_id']}).sort("created_at", -1))
    return render_template('admin_manage_jobs.html', jobs=my_jobs)


@admin_bp.route('/admin/export_csv')
def export_csv():
    if session.get('role') != 'admin':
        session['next_url'] = request.url
        return redirect(url_for('auth.admin_login'))
        
    if session.get('email') == os.getenv("DEFAULT_ADMIN_EMAIL"):
        candidates = list(candidates_collection.find())
    else:
        my_jobs = list(jobs_collection.find({"admin_id": session['user_id']}))
        my_job_ids = [str(job['_id']) for job in my_jobs]
        candidates = list(candidates_collection.find({"applied_job_id": {"$in": my_job_ids}}))
    candidates.sort(key=lambda x: x.get('ai_score') if x.get('ai_score') is not None else 0, reverse=True)

    si = StringIO()
    cw = csv.writer(si)
    
    cw.writerow([
        'Candidate Name', 'Email Address', 'Phone Number', 'Location', 
        'Target Job', 'AI Match Score (%)', 'Current Status', 'Date Applied', 
        'Declared Skills', 'Total Experience (Years)',
        'Education History', 'Experience History', 
        'Resume Link', 'CNIC Front', 'CNIC Back', 'Domicile', 
        'Education Documents', 'Experience Letters', 'Certifications', 'Research Links'
    ])
    
    base_url = request.host_url.rstrip('/')
    
    for c in candidates:
        name = f"{c.get('personal_info', {}).get('first_name', '')} {c.get('personal_info', {}).get('last_name', '')}"
        email = c.get('contact_info', {}).get('email', '')
        phone = c.get('contact_info', {}).get('phone', '')
        
        city = c.get('contact_info', {}).get('address', {}).get('city', '')
        country = c.get('contact_info', {}).get('address', {}).get('country', '')
        location = f"{city}, {country}".strip(', ')
        
        job_title = c.get('applied_job_title', 'N/A')
        score = c.get('ai_score', 'Pending')
        status = c.get('status', 'Applied')
        applied_at = c.get('applied_at', '')
        
        skills = ", ".join(c.get('skills', []))
        total_exp = c.get('total_experience_years', 0)
        
        edu_details_list = []
        for edu in c.get('education', []):
            edu_str = f"• {edu.get('degree_name')} ({edu.get('level')}) at {edu.get('institute_name')} | Score: {edu.get('obtained_marks')}/{edu.get('total_marks')}"
            edu_details_list.append(edu_str)
        edu_details = "\n".join(edu_details_list) if edu_details_list else "No Education Listed"

        exp_details_list = []
        for exp in c.get('experience', []):
            end_date_str = "Present" if exp.get('status') == 'Current' else exp.get('end_date')
            exp_str = f"• {exp.get('job_designation')} at {exp.get('company_name')} ({exp.get('employment_type')}, {exp.get('modality')}) | {exp.get('start_date')} to {end_date_str}"
            exp_details_list.append(exp_str)
        exp_details = "\n".join(exp_details_list) if exp_details_list else "No Experience Listed"

        cnic_front = f"{base_url}/uploads/{c.get('personal_info', {}).get('cnic_front')}" if c.get('personal_info', {}).get('cnic_front') else "Not Provided"
        cnic_back = f"{base_url}/uploads/{c.get('personal_info', {}).get('cnic_back')}" if c.get('personal_info', {}).get('cnic_back') else "Not Provided"
        domicile = f"{base_url}/uploads/{c.get('personal_info', {}).get('domicile')}" if c.get('personal_info', {}).get('domicile') else "Not Provided"

        resume_link = f"{base_url}/uploads/{c.get('resume_filename')}" if c.get('resume_filename') else "Not Provided"
        edu_docs = [f"{edu.get('degree_name')}: {base_url}/uploads/{edu.get('document')}" for edu in c.get('education', []) if edu.get('document')]
        edu_links = "\n".join(edu_docs) if edu_docs else "No Documents"
        exp_docs = [f"{exp.get('company_name')}: {base_url}/uploads/{exp.get('document')}" for exp in c.get('experience', []) if exp.get('document')]
        exp_links = "\n".join(exp_docs) if exp_docs else "No Documents"
        cert_docs = [f"{cert.get('name')}: {base_url}/uploads/{cert.get('document')}" for cert in c.get('certifications', []) if cert.get('document')]
        cert_links = "\n".join(cert_docs) if cert_docs else "No Documents"
        res_docs = [f"{res.get('title')}: {res.get('link')}" for res in c.get('research', []) if res.get('link')]
        res_links = "\n".join(res_docs) if res_docs else "No Links"
        
        cw.writerow([
            name, email, phone, location, 
            job_title, score, status, applied_at, 
            skills, total_exp,
            edu_details, exp_details, 
            resume_link, cnic_front, cnic_back, domicile, 
            edu_links, exp_links, cert_links, res_links
        ])
    
    output = si.getvalue()
    # "\ufeff" (BOM) prevents Excel from breaking newlines and special characters!
    return Response("\ufeff" + output, mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment;filename=HRVision_Candidates_Export.csv"})


@admin_bp.route('/admin/create_hr', methods=['GET', 'POST'])
def create_hr():
    if session.get('role') != 'admin' or session.get('email') != os.getenv("DEFAULT_ADMIN_EMAIL"):
        return redirect(url_for('admin.admin_dashboard'))
        
    if request.method == 'POST':
        action = request.form.get('action', 'create')
        
        if action == 'create':
            name = request.form.get('name')
            email = request.form.get('email')
            password = request.form.get('password')
            
            if users_collection.find_one({"email": email}):
                flash("Error: That email is already in use by another account.", "error")
            else:
                users_collection.insert_one({
                    "name": name, 
                    "email": email, 
                    "password": generate_password_hash(password),
                    "role": "admin", 
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
                flash(f"HR Manager '{name}' created successfully!")
                
        elif action == 'edit':
            hr_id = request.form.get('hr_id')
            name = request.form.get('name')
            email = request.form.get('email')
            password = request.form.get('password')
            
            update_data = {"name": name, "email": email}
            
            if password and password.strip() != "":
                update_data["password"] = generate_password_hash(password)
                
            if users_collection.find_one({"email": email, "_id": {"$ne": ObjectId(hr_id)}}):
                flash("Error: That email is already in use by another account.", "error")
            else:
                users_collection.update_one({"_id": ObjectId(hr_id)}, {"$set": update_data})
                flash(f"HR Manager '{name}' updated successfully!")
                
        elif action == 'delete':
            hr_id = request.form.get('hr_id')
            hr_user = users_collection.find_one({"_id": ObjectId(hr_id)})
            
            if hr_user and hr_user.get('email') == os.getenv("DEFAULT_ADMIN_EMAIL"):
                flash("Error: You cannot delete the Super Admin account.", "error")
            else:
                users_collection.delete_one({"_id": ObjectId(hr_id)})
                flash("HR Manager deleted successfully!")
                
        return redirect(url_for('admin.create_hr'))

    hr_managers = list(users_collection.find({"role": "admin"}))
    return render_template('admin_create_hr.html', hr_managers=hr_managers)


@admin_bp.route('/admin/post_job')
def post_job_form():
    if session.get('role') != 'admin':
        session['next_url'] = request.url
        return redirect(url_for('auth.admin_login'))
    return render_template('admin_job_post.html')


@admin_bp.route('/admin/submit_job', methods=['POST'])
def submit_job():
    if session.get('role') != 'admin':
        return redirect(url_for('auth.admin_login'))

    if request.method == 'POST':
        mand_skills = [s.strip() for s in request.form.get('mandatory_skills', '').split(',') if s.strip()]
        opt_skills = [s.strip() for s in request.form.get('optional_skills', '').split(',') if s.strip()]

        job_description_text = request.form.get('job_description', '')
        jd_file = request.files.get('jd_file')
        jd_filename = save_dynamic_file(jd_file) if jd_file and allowed_file(jd_file.filename) else ""
        if jd_filename:
            extracted_text = extract_text_from_file(os.path.join(UPLOAD_FOLDER, jd_filename))
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
        return redirect(url_for('admin.manage_jobs'))


@admin_bp.route('/admin/edit_job/<job_id>', methods=['GET', 'POST'])
def edit_job(job_id):
    if session.get('role') != 'admin':
        session['next_url'] = request.url
        return redirect(url_for('auth.admin_login'))

    job = jobs_collection.find_one({"_id": ObjectId(job_id)})
    if not job:
        flash("Job not found.")
        return redirect(url_for('admin.manage_jobs'))

    if session.get('email') != os.getenv("DEFAULT_ADMIN_EMAIL") and job.get('admin_id') != session['user_id']:
        flash("Unauthorized: You can only edit your own job postings.")
        return redirect(url_for('admin.manage_jobs'))

    if request.method == 'POST':
        mand_skills = [s.strip() for s in request.form.get('mandatory_skills', '').split(',') if s.strip()]
        opt_skills = [s.strip() for s in request.form.get('optional_skills', '').split(',') if s.strip()]

        job_description_text = request.form.get('job_description', '')
        jd_file = request.files.get('jd_file')
        jd_filename = request.form.get('existing_jd_filename', '')

        if jd_file and allowed_file(jd_file.filename):
            jd_filename = save_dynamic_file(jd_file)
            full_jd_path = os.path.join(UPLOAD_FOLDER, jd_filename)
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
        return redirect(url_for('admin.manage_jobs'))

    return render_template('admin_edit_job.html', job=job)


@admin_bp.route('/admin/update_job_status/<job_id>', methods=['POST'])
def update_job_status(job_id):
    if session.get('role') != 'admin':
        return redirect(url_for('auth.admin_login'))
    
    job = jobs_collection.find_one({"_id": ObjectId(job_id)})
    if session.get('email') != os.getenv("DEFAULT_ADMIN_EMAIL") and job.get('admin_id') != session['user_id']:
        flash("Unauthorized: Cannot update jobs you did not post.")
        return redirect(url_for('admin.manage_jobs'))

    new_status = request.form.get('status')
    if new_status:
        jobs_collection.update_one({"_id": ObjectId(job_id)}, {"$set": {"status": new_status}})
        flash(f"Job status changed to {new_status}.")
    return redirect(url_for('admin.manage_jobs'))


@admin_bp.route('/admin/update_status/<candidate_id>', methods=['POST'])
def update_status(candidate_id):
    if session.get('role') != 'admin':
        return redirect(url_for('auth.admin_login'))
        
    new_status = request.form.get('status')
    if new_status:
        candidate = candidates_collection.find_one({"_id": ObjectId(candidate_id)})
        if candidate:
            candidates_collection.update_one({"_id": ObjectId(candidate_id)}, {"$set": {"status": new_status}})
            
            c_name = candidate.get('personal_info', {}).get('first_name', 'Candidate')
            c_email = candidate.get('contact_info', {}).get('email')
            j_title = candidate.get('applied_job_title', 'a position')
            hr_name = candidate.get('applied_job_admin_name', session.get('user_name', 'HR Team'))
            
            interview_details = None
            if new_status == 'Interviewing':
                interview_details = {
                    "date": request.form.get('interview_date'),
                    "time": request.form.get('interview_time'),
                    "venue": request.form.get('interview_venue'),
                    "inform_later": request.form.get('inform_later')
                }
            
            if c_email and new_status in ['Shortlisted', 'Interviewing', 'Rejected', 'Hired']:
                email_success = send_status_email(c_email, c_name, j_title, new_status, hr_name, interview_details)
                
                if email_success:
                    flash(f"Candidate Status successfully updated to '{new_status}' and email notification sent!")
                else:
                    flash(f"Status updated to '{new_status}', but the email failed to send (Check Environment Variables).", "error")
            else:
                flash(f"Candidate Status successfully updated to '{new_status}'.")
        else:
            flash("Candidate not found.", "error")
            
    return redirect(url_for('admin.admin_dashboard'))


@admin_bp.route('/admin/delete_candidate/<candidate_id>', methods=['POST'])
def delete_candidate(candidate_id):
    if session.get('role') != 'admin':
        return redirect(url_for('auth.admin_login'))

    candidate = candidates_collection.find_one({"_id": ObjectId(candidate_id)})
    if not candidate:
        flash("Candidate not found.")
        return redirect(url_for('admin.admin_dashboard'))

    if session.get('email') == os.getenv("DEFAULT_ADMIN_EMAIL"):
        candidates_collection.delete_one({"_id": ObjectId(candidate_id)})
        flash("Candidate permanently deleted from database.")
    else:
        job = jobs_collection.find_one({"_id": ObjectId(candidate.get("applied_job_id"))})
        if job and job.get("admin_id") == session.get('user_id'):
            candidates_collection.delete_one({"_id": ObjectId(candidate_id)})
            flash("Candidate permanently deleted from your job listing.")
        else:
            flash("Unauthorized: You do not have permission to delete this candidate.", "error")
    return redirect(url_for('admin.admin_dashboard'))
    
@admin_bp.route('/admin/delete_job/<job_id>', methods=['POST'])
def delete_job(job_id):
    if session.get('role') != 'admin':
        return redirect(url_for('auth.admin_login'))
    
    job = jobs_collection.find_one({"_id": ObjectId(job_id)})
    if not job:
        flash("Job not found.", "error")
        return redirect(url_for('admin.manage_jobs'))

    if session.get('email') != os.getenv("DEFAULT_ADMIN_EMAIL") and job.get('admin_id') != session['user_id']:
        flash("Unauthorized: Cannot delete jobs you did not post.", "error")
        return redirect(url_for('admin.manage_jobs'))

    jobs_collection.delete_one({"_id": ObjectId(job_id)})
    flash("Job posting permanently deleted.")
    return redirect(url_for('admin.manage_jobs'))
    