import os
from flask import Flask, send_from_directory, flash, redirect, request, url_for
from werkzeug.security import generate_password_hash
from werkzeug.exceptions import RequestEntityTooLarge
from datetime import datetime

# Import variables from our config file
from config import SECRET_KEY, UPLOAD_FOLDER, MAX_CONTENT_LENGTH, users_collection

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

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
# --- GLOBAL FILE SERVING & ERROR HANDLING ---
# ==========================================
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.errorhandler(RequestEntityTooLarge)
def handle_file_size_error(e):
    flash("Upload failed: File size exceeds the 10MB limit. Please compress your document.", "error")
    # FIX: Point to the actual public homepage route
    return redirect(request.referrer or url_for('public.root'))

# ==========================================
# --- REGISTER BLUEPRINTS ---
# ==========================================
from routes.public import public_bp
from routes.auth import auth_bp
from routes.admin import admin_bp
from routes.candidate import candidate_bp

app.register_blueprint(public_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(candidate_bp)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)