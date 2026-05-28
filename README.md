# 🚀 HRVision: AI-Powered Recruitment Ecosystem

**HRVision** is a next-generation Applicant Tracking System (ATS) developed as a Final Year Project. By leveraging Deep Learning and Natural Language Processing (NLP), HRVision eliminates the "black box" of AI hiring. It provides transparent, explainable semantic scoring to identify the best talent while offering candidates a frictionless, "apply-once" experience. :contentReference[oaicite:0]{index=0}

---

## ✨ Key Features

- **Semantic AI Matching:** Uses `all-MiniLM-L6-v2` (BERT-based) to compute precise similarity scores between candidate resumes and job requirements.
- **Explainable AI (XAI):** Provides a transparent dashboard showing exactly which skills were matched and which are missing, reducing recruitment bias.
- **Master Profile System:** Candidates build one comprehensive profile (Experience, Education, Certifications) and can apply to multiple job postings with a single click.
- **Secure HR ATS:** A centralized dashboard for HR managers to review candidates, track pipeline status, manage interview schedules, and export hiring data to CSV.
- **Automated Communication:** Integrated secure email engine provides instant status updates (Shortlisted, Interviewing, Hired/Rejected) to candidates.

---

## 🛠️ Technology Stack

| Layer | Technology |
| :--- | :--- |
| **Backend** | Python 3.x, Flask (Blueprint Architecture) |
| **Database** | MongoDB Atlas (NoSQL) |
| **AI/NLP Engine** | `sentence-transformers`, PyTorch, Hugging Face Hub |
| **File Processing** | `PyPDF2`, `python-docx`, `Mammoth.js` |
| **Frontend** | HTML5, CSS3, JavaScript (Vanilla), Chart.js, DataTables |

---

## ⚙️ Core Architecture & Cloud Integration

HRVision utilizes a **Distributed Microservices Architecture** to ensure high performance and scalability.

- **Web Server (Render):** Hosts the Flask application. It manages user authentication, routing, and file parsing.
- **AI Microservice (Hugging Face Spaces):** The heavy NLP workload is offloaded to a dedicated API hosted on Hugging Face. Render sends a lightweight JSON payload to this API, which performs tensor calculations and returns the results.
- **Database (MongoDB Atlas):** A managed cloud database cluster handles persistent storage for candidates, jobs, and profiles via secure TLS/SSL TCP connections.

---

## 📂 Enterprise Project Structure

The backend is completely decoupled using **Flask Blueprints** for maximum scalability and maintainability:

```text
hrvision/
│
├── .env                   # Environment variables (Hidden)
├── config.py              # Database & global application settings
├── utils.py               # Background tasks (Email Engine & File Parsing)
├── ai_engine.py           # Offline/Local AI Fallback Logic
├── app.py                 # Core Application Entry Point
│
├── routes/                # Modular Blueprint Routing
│   ├── public.py          # Landing, About, Contact
│   ├── auth.py            # Secure Login, Registration, Password Resets
│   ├── admin.py           # HR ATS Dashboard & Job Management
│   └── candidate.py       # Candidate Profiles, Job Board, AI Evaluation
│
├── templates/             # Jinja2 HTML Templates
└── static/                # CSS, JavaScript, and Images
```

---

## 📦 Setup & Installation

### 1. Environment Requirements

- Python 3.x
- MongoDB Atlas Cluster (or local MongoDB instance)

### 2. Configuration (`.env`)

Create a `.env` file in your root directory and add your secure credentials:

```env
FLASK_SECRET_KEY=your_secure_random_key
MONGO_URI=mongodb+srv://<username>:<password>@cluster.mongodb.net/hrvision_db
MAIL_USERNAME=your_email@gmail.com
MAIL_PASSWORD=your_16_digit_app_password
RENDER=false
```

### 3. Local Installation

Follow these steps to run the environment locally:

```bash
# 1. Clone the repository
git clone https://github.com/HaiderIjaz5/hrvision.git
cd hrvision

# 2. Create a Virtual Environment
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate

# 3. Install Dependencies
pip install -r requirements.txt

# 4. Launch the Server
python app.py
```

The application will be accessible at:

```text
http://127.0.0.1:5000
```

---

## 📊 Deployment Notes (For FYP Defense)

### Why Render over Vercel?

We opted for Render because Vercel's serverless architecture has a strict **250MB deployment limit** and read-only file systems, which are fundamentally incompatible with our heavy AI-model dependencies and dynamic file-upload requirements.

### Explainable AI Advantage

Unlike legacy ATS systems that rely on blind keyword matching, HRVision utilizes deep semantic understanding. By exposing the "matched" and "missing" parameters to the HR Manager, we remove the "black box" of AI, promoting fairer and more transparent hiring practices.

### Security Standards

- All application secrets are injected via runtime environment variables.
- Passwords are cryptographically hashed using `werkzeug.security`.
- Route access is protected via strict session-based Role-Based Access Control (RBAC).

---

## 👨‍💻 Developed By

**Muhammad Haider Ijaz**  
Software Engineering Capstone 2026  
University of Agriculture, Faisalabad