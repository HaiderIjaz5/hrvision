from flask import Blueprint, render_template, request, redirect, url_for, flash
from utils import send_contact_email

public_bp = Blueprint('public', __name__)

@public_bp.route('/')
def root():
   return render_template('index.html')

@public_bp.route('/about')
def about():
    return render_template('about.html')

@public_bp.route('/privacy')
def privacy():
    return render_template('privacy.html')

@public_bp.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        message = request.form.get('message')
        
        success = send_contact_email(name, email, message)
        
        if success:
            flash("Thank you for reaching out! Our team will get back to you shortly.")
        else:
            flash("Oops! Our mail server is currently busy. Please try again later.", "error")
        return redirect(url_for('public.contact'))
        
    return render_template('contact.html')