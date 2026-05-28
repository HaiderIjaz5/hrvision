from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer
from datetime import datetime
from bson.objectid import ObjectId

from config import users_collection, SECRET_KEY
from utils import send_reset_email

auth_bp = Blueprint('auth', __name__)
serializer = URLSafeTimedSerializer(SECRET_KEY)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')

        if users_collection.find_one({"email": email}):
            flash("Email already registered. Please login.", "error")
            return redirect(url_for('auth.login'))

        hashed_password = generate_password_hash(password)
        users_collection.insert_one({
            "name": name, "email": email, "password": hashed_password,
            "role": "candidate", "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        flash("Account created successfully! Please log in.")
        return redirect(url_for('auth.login'))
    return render_template('register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('role') == 'candidate':
        return redirect(url_for('candidate.candidate_dashboard'))
    elif session.get('role') == 'admin':
        return redirect(url_for('admin.admin_dashboard'))

    if request.method == 'GET':
        next_url = request.args.get('next')
        if next_url:
            session['next_url'] = next_url

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = users_collection.find_one({"email": email, "role": "candidate"})
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = str(user['_id'])
            session['user_name'] = user['name']
            session['email'] = user['email']
            session['role'] = user['role']
            flash(f"Welcome back, {user['name']}! You have successfully logged in.")
            return redirect(session.pop('next_url', url_for('candidate.candidate_dashboard')))
        else:
            flash("Incorrect email or password.", "error")
            return redirect(url_for('auth.login'))
            
    return render_template('login.html')

@auth_bp.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('role') == 'admin':
        return redirect(url_for('admin.admin_dashboard'))

    if request.method == 'GET':
        next_url = request.args.get('next')
        if next_url:
            session['next_url'] = next_url

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = users_collection.find_one({"email": email, "role": "admin"})
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = str(user['_id'])
            session['user_name'] = user['name']
            session['email'] = user['email']
            session['role'] = user['role']
            return redirect(session.pop('next_url', url_for('admin.admin_dashboard')))
        else:
            flash("Invalid Admin Credentials or Unauthorized Access.", "error")
            return redirect(url_for('auth.admin_login'))
            
    return render_template('admin_login.html')

@auth_bp.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = users_collection.find_one({"email": email})
        if user:
            token = serializer.dumps(email, salt='password-reset-salt')
            send_reset_email(email, token)
        flash("If an account with that email exists, a password reset link has been sent.")
        return redirect(url_for('auth.login'))
    return render_template('forgot_password.html')

@auth_bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_token(token):
    try:
        email = serializer.loads(token, salt='password-reset-salt', max_age=3600)
    except Exception:
        flash("The password reset link is invalid or has expired.", "error")
        return redirect(url_for('auth.forgot_password'))
        
    if request.method == 'POST':
        hashed_password = generate_password_hash(request.form.get('new_password'))
        users_collection.update_one({"email": email}, {"$set": {"password": hashed_password}})
        flash("Your password has been successfully updated! Please log in.")
        return redirect(url_for('auth.login'))
        
    return render_template('reset_with_token.html')

@auth_bp.route('/logout')
def logout():
    user_role = session.get('role')
    session.clear()
    
    if user_role == 'admin':
        flash("You have securely logged out of the Admin Portal.")
    elif user_role == 'candidate':
        flash("You have successfully logged out of your account.")
        
    return redirect(request.referrer or url_for('public.root'))