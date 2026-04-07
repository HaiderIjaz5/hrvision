# 🚀 HRVision: AI-Powered Resume Screening System

**HRVision** is a comprehensive Final Year Project (FYP) designed to streamline the recruitment process. By leveraging Deep Learning and Natural Language Processing (NLP), HRVision eliminates the "black box" of AI hiring by automatically scoring candidate resumes against job descriptions while providing transparent, Explainable AI insights.

## ✨ Key Features
- **Intelligent Candidate Matching:** Utilizes `all-MiniLM-L6-v2` (a BERT-based model) to compute semantic similarity between candidate profiles and job requirements.
- **Explainable AI (XAI):** Doesn't just give a score; explicitly shows HR Managers which mandatory skills were matched and which were missing.
- **Master Profile System:** Candidates create a single, comprehensive profile (Education, Experience, Certifications) to easily apply to multiple jobs.
- **Automated Communication:** Built-in email engine to automatically notify candidates when their application status changes (e.g., Shortlisted, Rejected).
- **Secure Admin Portal:** Role-based access control with secure password hashing, allowing HR managers to post jobs, review AI scores, and export candidate data to CSV.

## 🛠️ Technology Stack
- **Backend:** Python, Flask
- **Database:** MongoDB
- **AI/ML Engine:** `sentence-transformers`, PyTorch
- **File Parsing:** `PyPDF2`, `python-docx`
- **Frontend:** HTML5, CSS3, vanilla JavaScript, DataTables, Chart.js

## ⚙️ Local Setup Instructions

Follow these steps to run HRVision on your local machine:

**1. Clone the repository**
```bash
git clone [https://github.com/HaiderIjaz5/hrvision.git](https://github.com/HaiderIjaz5/hrvision.git)
cd hrvision