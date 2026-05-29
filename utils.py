import os
import smtplib
import uuid
from email.mime.text import MIMEText
from werkzeug.utils import secure_filename
import PyPDF2
import docx
from flask import url_for

# Import the variables we set up in config.py
from config import MAIL_USERNAME, MAIL_PASSWORD, UPLOAD_FOLDER, ALLOWED_EXTENSIONS

# ==========================================
# --- EMAIL ENGINE FUNCTIONS ---
# ==========================================
def send_application_receipt_email(candidate_email, candidate_name, job_title):
    subject = f"Application Received: {job_title}"
    body = f"Dear {candidate_name},\n\nThank you for applying for the {job_title} position at HRVision.\n\nWe have successfully received your application and resume. Our AI screening engine and recruitment team will review your profile shortly. You can track your application status anytime through your Candidate Dashboard.\n\nBest regards,\nHRVision Talent Acquisition"
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = MAIL_USERNAME
    msg['To'] = candidate_email
    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=10) 
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.sendmail(MAIL_USERNAME, candidate_email, msg.as_string())
        server.quit()
        print(f"✅ Automated Application Receipt Email Sent to {candidate_email}")
    except Exception as e:
        print(f"❌ Failed to send application receipt email: {e}")

def send_reset_email(user_email, token):
    reset_url = url_for('auth.reset_token', token=token, _external=True)
    msg = MIMEText(f"Hello,\n\nTo reset your HRVision password, please click the link below:\n\n{reset_url}\n\nThis link will expire in 1 hour.")
    msg['Subject'] = 'HRVision Password Reset Request'
    msg['From'] = MAIL_USERNAME
    msg['To'] = user_email
    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=10)
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.sendmail(MAIL_USERNAME, user_email, msg.as_string())
        server.quit()
    except Exception as e:
        print(f"❌ Failed to send reset email: {e}")

def send_contact_email(user_name, user_email, user_message):
    receiver_email = MAIL_USERNAME 
    msg = MIMEText(f"New Contact Form Submission from HRVision!\n\nName: {user_name}\nEmail: {user_email}\n\nMessage:\n{user_message}")
    msg['Subject'] = f'HRVision Contact: Message from {user_name}'
    msg['From'] = MAIL_USERNAME
    msg['To'] = receiver_email
    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=10)
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.sendmail(MAIL_USERNAME, receiver_email, msg.as_string())
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
        if interview_details:
            if interview_details.get('inform_later') == 'true':
                body += "Our team is currently finalizing the schedule. We will be reaching out to you very soon with the exact date, time, and venue/meeting link for your interview.\n\n"
            else:
                body += f"Here are your interview details:\n📅 Date: {interview_details.get('date', 'TBD')}\n⏰ Time: {interview_details.get('time', 'TBD')}\n📍 Venue/Link: {interview_details.get('venue', 'TBD')}\n\n"
        body += f"Please reply to this email to confirm your availability.\n\nBest regards,\n{hr_name}\nHRVision Talent Acquisition"
    elif new_status == 'Hired':
        subject = f"Job Offer: {job_title} at HRVision"
        body = f"Dear {candidate_name},\n\nCongratulations! After a thorough review and interview process, we are absolutely thrilled to offer you the position of {job_title} at HRVision.\n\nOur HR team will be reaching out to you shortly with your official offer letter and onboarding details.\n\nWelcome to the team!\n\nBest regards,\n{hr_name}\nHRVision Talent Acquisition"   
    elif new_status == 'Rejected':
        subject = f"Update on your application for {job_title}"
        body = f"Dear {candidate_name},\n\nThank you for applying for the {job_title} position. \n\nWhile your background is impressive, we have decided to move forward with other candidates whose profiles more closely align with the specific needs of this role at this time.\n\nWe wish you the best in your career search.\n\nSincerely,\n{hr_name}\nHRVision Talent Acquisition"
    else:
        return False
        
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = MAIL_USERNAME
    msg['To'] = candidate_email
    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=10)
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.sendmail(MAIL_USERNAME, candidate_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"❌ Failed to send status email: {e}")
        return False

# ==========================================
# --- FILE HANDLING FUNCTIONS ---
# ==========================================
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_dynamic_file(file_obj):
    if file_obj and file_obj.filename and allowed_file(file_obj.filename):
        original_filename = secure_filename(file_obj.filename)
        
        # FIX: Append a unique 8-character ID to the filename to prevent overwrites
        unique_id = uuid.uuid4().hex[:8]
        filename = f"{unique_id}_{original_filename}"
        
        path = os.path.join(UPLOAD_FOLDER, filename)
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
                    extracted = page.extract_text()
                    if extracted: text += extracted + "\n"
        elif ext in ['doc', 'docx']:
            doc = docx.Document(filepath)
            for para in doc.paragraphs:
                text += para.text + "\n"
    except Exception as e:
        print(f"Error extracting JD text: {e}")
    return text.strip()