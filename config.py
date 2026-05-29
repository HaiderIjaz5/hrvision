import os
from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Basic Configuration
SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'default_fallback_key')
UPLOAD_FOLDER = 'uploads'
MAX_CONTENT_LENGTH = 16 * 1024 * 1024 # 16 MB limit for file uploads
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'png', 'jpg', 'jpeg'}

# Email Configuration
MAIL_USERNAME = os.getenv('MAIL_USERNAME')
MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')

# Database Configuration
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
client = MongoClient(MONGO_URI)
db = client['hrvision_db']  
candidates_collection = db['candidates'] 
jobs_collection = db['jobs']  
users_collection = db['users'] 
profiles_collection = db['profiles']