import os
import re
import PyPDF2
import docx
from sentence_transformers import SentenceTransformer, util

_ai_model = None

def get_model():
    global _ai_model
    if _ai_model is None:
        print("Loading Deep Learning AI Model (this might take a few seconds)...")
        _ai_model = SentenceTransformer('all-MiniLM-L6-v2')
        print("AI Model successfully loaded and ready!")
    return _ai_model

def clean_text(text):
    if not text: return ""
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

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
            for para in doc.paragraphs: text += para.text + "\n"
    except Exception as e:
        print(f"⚠️ Error reading file {filepath}: {e}")
    return text.strip()

def calculate_resume_score(resume_path, job_description, mandatory_skills=[], candidate_skills=[]):
    resume_raw_text = extract_text_from_file(resume_path)
    
    if not resume_raw_text and not candidate_skills: 
        return 0, [], mandatory_skills 
        
    candidate_full_text = resume_raw_text + " " + " ".join(candidate_skills)
    candidate_clean = clean_text(candidate_full_text)
    jd_clean = clean_text(job_description)

    if not jd_clean: 
        return 0, [], mandatory_skills 

    try:
        model = get_model() 
        candidate_embedding = model.encode(candidate_clean, convert_to_tensor=True)
        jd_embedding = model.encode(jd_clean, convert_to_tensor=True)
        cosine_scores = util.cos_sim(candidate_embedding, jd_embedding)
        base_ai_score = cosine_scores[0][0].item() * 100
    except Exception as e:
        print(f"Error during AI processing: {e}")
        base_ai_score = 0.0

    penalty = 0
    candidate_search_text = candidate_clean.lower()
    matched_skills = []
    missing_skills = []
    
    if mandatory_skills:
        for skill in mandatory_skills:
            cleaned_skill = clean_text(skill)
            
            # NEW: Only grade this skill if it is not totally blank
            if cleaned_skill: 
                if cleaned_skill in candidate_search_text:
                    matched_skills.append(skill)
                else:
                    missing_skills.append(skill)
                    penalty += 15 
                
    final_score = max(0, round(base_ai_score - penalty))
    return final_score, matched_skills, missing_skills