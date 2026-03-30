import os
import uuid
import json
import re
import pdfplumber
from docx import Document
from django.shortcuts import render
from django.conf import settings
from groq import Groq

client = Groq(api_key=settings.GROQ_API)


# ==============================
# Extract Text
# ==============================
def extract_text(file_path):
    text = ""

    try:
        if file_path.endswith(".pdf"):
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"

        elif file_path.endswith(".docx"):
            doc = Document(file_path)
            for para in doc.paragraphs:
                text += para.text + "\n"

    except Exception as e:
        print("TEXT EXTRACTION ERROR:", str(e))
        return ""

    return text.strip()


# ==============================
# 🔥 Deterministic Keyword Matching
# ==============================
def extract_role_keywords(role):
    """
    Simple keyword extraction from role string
    Example: 'AI Full Stack Developer'
    → ['ai', 'full', 'stack', 'developer']
    """
    role = role.lower()
    words = re.findall(r'\b[a-zA-Z]+\b', role)
    return list(set(words))


def count_matching_words(resume_text, role_keywords):
    resume_text = resume_text.lower()
    count = 0

    for word in role_keywords:
        if word in resume_text:
            count += 1

    return count


# ==============================
# Analyze Resume with Groq
# ==============================
def analyze_resume(resume_text, role):

    if len(resume_text) < 50:
        return {"error": "Resume text too short or could not be extracted."}

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior HR consultant and ATS optimization expert. "
                        "Return ONLY valid raw JSON. "
                        "Do NOT include markdown or extra explanation."
                    )
                },
                {
                    "role": "user",
                    "content": f"""
                Analyze this resume for a {role} role.

                Give realistic scores for:
                - experience_score (0-30)
                - skills_score (0-20)
                - structure_score (0-20)

                DO NOT calculate keyword_score.
                Return ONLY valid JSON in this format:

                {{
                    "experience_score": number,
                    "skills_score": number,
                    "structure_score": number,
                    "executive_summary": "summary",
                    "role_match_analysis": "analysis",
                    "strengths": ["s1","s2","s3"],
                    "weaknesses": ["w1","w2"],
                    "missing_skills": ["m1","m2","m3"],
                    "improvements": ["i1","i2","i3"],
                    "verdict": "final recommendation"
                }}

                Resume:
                {resume_text}
                """
                }
            ],
            temperature=0,
            max_tokens=1200
        )

        content = response.choices[0].message.content.strip()

        # Remove markdown
        if "```" in content:
            parts = content.split("```")
            if len(parts) > 1:
                content = parts[1].strip()
                if content.lower().startswith("json"):
                    content = content[4:].strip()

        # Extract JSON
        start = content.find("{")
        end = content.rfind("}") + 1

        if start == -1 or end == -1:
            print("INVALID JSON RESPONSE:", content)
            return {"error": "AI returned invalid JSON format."}

        json_string = content[start:end]

        try:
            data = json.loads(json_string)
        except Exception:
            print("JSON PARSE ERROR:", content)
            return {"error": "AI returned malformed JSON."}

        # ==============================
        # 🔥 Deterministic Keyword Score
        # ==============================

        role_keywords = extract_role_keywords(role)
        matched_keywords = count_matching_words(resume_text, role_keywords)

        keyword_score = min(matched_keywords * 3, 30)

        # Clamp other scores safely
        experience = min(max(int(data.get("experience_score", 0)), 0), 30)
        skills = min(max(int(data.get("skills_score", 0)), 0), 20)
        structure = min(max(int(data.get("structure_score", 0)), 0), 20)

        final_score = keyword_score + experience + skills + structure

        data["keyword_score"] = keyword_score
        data["ats_score"] = min(final_score, 100)

        print("MATCHED KEYWORDS:", matched_keywords)
        print("FINAL CALCULATED SCORE:", data["ats_score"])

        return data

    except Exception as e:
        print("GROQ ERROR:", str(e))
        return {"error": f"Error analyzing resume: {str(e)}"}


# ==============================
# Upload Resume View
# ==============================
from .models import ResumeAnalysis

def upload_resume(request):

    if request.method == "POST":

        resume_file = request.FILES.get("resume")
        role = request.POST.get("role")

        if not resume_file:
            return render(request, "upload.html", {"error": "No file uploaded."})

        if not role:
            return render(request, "upload.html", {"error": "Please enter job role."})

        if not resume_file.name.endswith((".pdf", ".docx")):
            return render(request, "upload.html", {
                "error": "Only PDF and DOCX files allowed."
            })

        if resume_file.size > 5 * 1024 * 1024:
            return render(request, "upload.html", {
                "error": "File must be under 5MB."
            })

        # 🔥 DATABASE ME SAVE KAR (AUTO FILE SAVE HO JAYEGI)
        analysis_obj = ResumeAnalysis.objects.create(
            user=request.user,
            resume=resume_file,
            job_role=role
        )

        # 🔥 FILE PATH YAHAN SE LE
        file_path = analysis_obj.resume.path

        # TEXT EXTRACT
        resume_text = extract_text(file_path)

        if not resume_text:
            return render(request, "upload.html", {
                "error": "Could not extract text from resume."
            })

        # ANALYSIS
        result = analyze_resume(resume_text, role)

        return render(request, "result.html", {
            "role": role,
            "ats_score": result.get("ats_score", 0),
            "keyword_score": result.get("keyword_score", 0),
            "executive_summary": result.get("executive_summary", result.get("error", "")),
            "role_match_analysis": result.get("role_match_analysis", ""),
            "strengths": result.get("strengths", []),
            "weaknesses": result.get("weaknesses", []),
            "missing_skills": result.get("missing_skills", []),
            "improvements": result.get("improvements", []),
            "verdict": result.get("verdict", "")
        })

    return render(request, "upload.html")