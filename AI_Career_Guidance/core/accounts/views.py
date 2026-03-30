import profile

from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from .models import StudentProfile
from .models import Skill, StudentProfile,StudentSkill
from django.shortcuts import get_object_or_404
from .models import Career
from django.views.decorators.cache import never_cache
from django.contrib.admin.views.decorators import staff_member_required
from .forms import UserUpdateForm, CareerForm ,ContactForm
from django.conf import settings
from .forms import SkillForm
from django.contrib import messages
from django.db.models import Q
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST
from .models import CareerQuizQuestion, CareerQuizOption, CareerQuizResult ,Category,CombinedCareerResult
from django.http import HttpResponse
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Content
from .models import Category
from .forms import CategoryForm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer,ListFlowable, ListItem
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
import io
from xml.sax.saxutils import escape
import os 
import json
import re
from courses.models import Course
from captcha.fields import CaptchaField
from captcha.helpers import captcha_image_url
from captcha.models import CaptchaStore
from django.core.mail import send_mail
from django.http import JsonResponse
import random
from analyzer.models import ResumeAnalysis
from django.views.decorators.cache import never_cache
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

@never_cache
@login_required
def dashboard(request):
    profile, created = StudentProfile.objects.get_or_create(user=request.user)

    # ================= INTEREST NAME =================
    interest_name = None

    if profile.interest:
        val = str(profile.interest).strip()

        if val.isdigit():
            category = Category.objects.filter(id=int(val)).first()
            if category:
                interest_name = category.name
        else:
            interest_name = val.title()

    # ================= QUIZ RESULT =================
    result = CombinedCareerResult.latest_for_student(profile)

    top_career = None
    top_careers_with_gap = []
    match_percentage = 0

    if result and result.suggested_career:
        top_career = result.suggested_career
        match_percentage = result.match_percentage or 0

        # 🔥 Similar careers (SAFE)
        careers = Career.objects.filter(
            category=top_career.category
        ).exclude(id=top_career.id)[:2]

        all_careers = [(top_career, match_percentage)]
        for c in careers:
            all_careers.append((c, 50))  # dummy score

        # 🔥 USER SKILLS
        user_skills = {
            ss.skill.name.strip().lower(): ss.level
            for ss in profile.student_skills.select_related("skill")
        }

        # 🔥 GAP ANALYSIS
        for career, score in all_careers:
            career_skills = {
                s.name.strip().lower()
                for s in career.required_skills.all()
            }

            gap = list(career_skills - set(user_skills.keys()))

            top_careers_with_gap.append({
                "career": career,
                "score": score,
                "gap": gap
            })

    # ================= PROFILE COMPLETION =================
    completion = 0

    if profile.profile_picture:
        completion += 15
    if request.user.first_name:
        completion += 15
    if request.user.last_name:
        completion += 15
    if profile.student_skills.exists():
        completion += 20
    if profile.education_level:
        completion += 15
    if profile.interest:
        completion += 10

    # 🔥 IMPORTANT: quiz add kar
    if result:
        completion += 10

    completion = min(completion, 100)

    # ================= PROFILE COMPLETE CHECK =================
    profile_completed = (
        request.user.first_name and
        request.user.last_name and
        profile.profile_picture and
        profile.student_skills.exists()
    )

    # ================= QUIZ STATUS =================
    has_taken_quiz = result is not None

    # ================= CHART DATA =================
    chart_labels = []
    chart_required = []
    chart_user = []

    if top_career:
        for skill in top_career.required_skills.all():
            chart_labels.append(skill.name.strip())
            chart_required.append(80)  # market demand

            if profile.student_skills.filter(skill=skill).exists():
                chart_user.append(80)  # green
            else:
                chart_user.append(0)   # red

    # ================= FINAL RENDER =================
    return render(request, "accounts/dashboard.html", {
        "profile": profile,
        "interest_name": interest_name,

        "career": top_career,
        "top_careers_with_gap": top_careers_with_gap,

        "has_taken_quiz": has_taken_quiz,
        "profile_completed": profile_completed,

        "match_percentage": match_percentage,
        "completion": completion,

        "chart_labels": chart_labels,
        "chart_required": chart_required,
        "chart_user": chart_user,
    })
def about_us(request):
    """
    Render the About Us page for AI Career Guidance.
    """
    return render(request, "accounts/about_us.html")

@login_required
def edit_account(request):
    user = request.user
    profile, created = StudentProfile.objects.get_or_create(user=user)

    if request.method == "POST":

        user.first_name = request.POST.get("first_name", "").strip()
        user.last_name = request.POST.get("last_name", "").strip()
        email = request.POST.get("email", "").strip()

        if User.objects.filter(email=email).exclude(id=user.id).exists():
            messages.error(request, "Email already in use.")
            return redirect("edit_account")

        user.email = email

        # ---------------- Basic Info ----------------
        profile.education_level = request.POST.get("education_level")
        profile.stream = request.POST.get("stream")
        profile.graduation_field = request.POST.get("graduation_field")
        profile.post_graduation_field = request.POST.get("post_graduation_field")
        profile.location_preference = request.POST.get("location_preference")

        # ❌ INTEREST REMOVED

        # ---------------- Profile Picture ----------------
        if request.POST.get("remove_photo"):
            if profile.profile_picture:
                profile.profile_picture.delete(save=True)
            profile.profile_picture = None

        if request.FILES.get("profile_picture"):
            profile.profile_picture = request.FILES["profile_picture"]

        user.save()
        profile.save()

        messages.success(request, "Account updated successfully!")
        return redirect("dashboard")

    return render(request, "accounts/edit_account.html", {"profile": profile})


def home(request):
    quiz_done = False
    can_take_quiz = False  # 🔥 NEW

    if request.user.is_authenticated:
        try:
            profile = StudentProfile.objects.get(user=request.user)

            quiz_done = profile.personality_quiz_completed

            # 🔥 MAIN LOGIC (skills + interests check)
            can_take_quiz = (
                profile.student_skills.exists() and
                bool(profile.skills)
            )

        except StudentProfile.DoesNotExist:
            quiz_done = False
            can_take_quiz = False

    courses = Course.objects.filter(is_featured=True)[:3] 

    context = {
        "quiz_done": quiz_done,
        "can_take_quiz": can_take_quiz,
        "courses": courses  
    }

    return render(request, "accounts/home.html", context)
def login_view(request):
    if request.method == "POST":
        email = request.POST.get('email')
        password = request.POST.get('password')
        captcha_input = request.POST.get('captcha')
        captcha_key = request.POST.get('captcha_key')

        # ✅ CAPTCHA validation
        try:
            captcha_obj = CaptchaStore.objects.get(hashkey=captcha_key)
            if captcha_obj.response.lower() != captcha_input.lower():
                raise Exception("Invalid Captcha")
        except:
            captcha = CaptchaStore.generate_key()
            captcha_image = captcha_image_url(captcha)

            return render(request, 'accounts/login.html', {
                'error': 'Invalid Captcha',
                'captcha_key': captcha,
                'captcha_image': captcha_image
            })

        # ✅ AUTHENTICATION
        user = authenticate(request, username=email, password=password)

        if user:
            login(request, user)
            return redirect('dashboard')
        else:
            captcha = CaptchaStore.generate_key()
            captcha_image = captcha_image_url(captcha)

            return render(request, 'accounts/login.html', {
                'error': 'Invalid credentials',
                'captcha_key': captcha,
                'captcha_image': captcha_image
            })

    # ✅ First load captcha
    captcha = CaptchaStore.generate_key()
    captcha_image = captcha_image_url(captcha)

    return render(request, 'accounts/login.html', {
        'captcha_key': captcha,
        'captcha_image': captcha_image
    })

def refresh_captcha(request):
    new_key = CaptchaStore.generate_key()
    return JsonResponse({
        'captcha_key': new_key,
        'captcha_image': captcha_image_url(new_key)
    })


def send_email(to_email, subject, html_content):
    message = Mail(
        from_email=settings.DEFAULT_FROM_EMAIL,
        to_emails=to_email,
        subject=subject,
        html_content=html_content
    )

    # Add plain text version
    message.add_content(Content("text/plain", "Your registration is successful."))

    # Optional: Reply-To header
    message.reply_to = settings.DEFAULT_FROM_EMAIL

    try:
        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sg.send(message)
        print("Email sent, status:", response.status_code)
    except Exception as e:
        print("Error sending email:", e)

def register_view(request):
    if request.method == "POST":
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        email = request.POST.get('email')
        password = request.POST.get('password')
        captcha_input = request.POST.get('captcha')

        if not all([first_name, last_name, email, password, captcha_input]):
            return render(request, 'accounts/register.html', {'error': 'All fields are required'})

        if not re.match("^[A-Za-z]+$", first_name):
            return render(request, 'accounts/register.html', {'error': 'First name should contain only letters'})

        if not re.match("^[A-Za-z]+$", last_name):
            return render(request, 'accounts/register.html', {'error': 'Last name should contain only letters'})

        if User.objects.filter(username=email).exists():
            return render(request, 'accounts/register.html', {'error': 'Email already registered'})

        captcha_key = request.POST.get('captcha_key')
        try:
            captcha_obj = CaptchaStore.objects.get(hashkey=captcha_key)
            if captcha_obj.response.lower() != captcha_input.lower():
                raise Exception()
        except:
            return render(request, 'accounts/register.html', {'error': 'Invalid Captcha'})

        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name
        )

        user = authenticate(request, username=email, password=password)
        if user:
            login(request, user)

        send_email(
            email,
            "Welcome to CareerVidya AI",
            f"""
            <h2>Hello {first_name}</h2>
            <p>Your registration is successful.</p>
            <p>Platform: CareerVidya AI</p>
            <p>Start exploring now</p>
            <p>Thanks<br>CareerVidya Team</p>
            """
        )

        send_email(
            "patyaldeepanshu05@gmail.com",
            "New User Registered",
            f"""
            <h3>New User Registered</h3>
            <p>Name: {first_name} {last_name}</p>
            <p>Email: {email}</p>
            """
        )

        return redirect('dashboard')

    captcha = CaptchaStore.generate_key()
    captcha_image = captcha_image_url(captcha)

    return render(request, 'accounts/register.html', {
        'captcha_key': captcha,
        'captcha_image': captcha_image
    })

# locally eamil setup code
# from django.core.mail import EmailMultiAlternatives

# def send_email(to_email, subject, html_content):
#     # Django EmailMultiAlternatives for HTML + plain text
#     plain_text = "Your registration is successful."
#     msg = EmailMultiAlternatives(
#         subject,
#         plain_text,
#         settings.DEFAULT_FROM_EMAIL,
#         [to_email]
#     )
#     msg.attach_alternative(html_content, "text/html")
#     try:
#         msg.send()
#         print(f"Email sent to {to_email}")
#     except Exception as e:
#         print(f"Error sending email: {e}")

# def register_view(request):
#     if request.method == "POST":
#         first_name = request.POST.get('first_name')
#         last_name = request.POST.get('last_name')
#         email = request.POST.get('email')
#         password = request.POST.get('password')
#         captcha_input = request.POST.get('captcha')

#         # Basic validation
#         if not all([first_name, last_name, email, password, captcha_input]):
#             return render(request, 'accounts/register.html', {'error': 'All fields are required'})

#         if not first_name.isalpha() or not last_name.isalpha():
#             return render(request, 'accounts/register.html', {'error': 'Names should contain only letters'})

#         if User.objects.filter(username=email).exists():
#             return render(request, 'accounts/register.html', {'error': 'Email already registered'})

#         # Captcha validation
#         captcha_key = request.POST.get('captcha_key')
#         try:
#             captcha_obj = CaptchaStore.objects.get(hashkey=captcha_key)
#             if captcha_obj.response.lower() != captcha_input.lower():
#                 raise Exception()
#         except:
#             return render(request, 'accounts/register.html', {'error': 'Invalid Captcha'})

#         # Create user
#         user = User.objects.create_user(
#             username=email,
#             email=email,
#             password=password,
#             first_name=first_name,
#             last_name=last_name
#         )

#         user = authenticate(request, username=email, password=password)
#         if user:
#             login(request, user)

#         # Send user email
#         send_email(
#             email,
#             "Welcome to CareerVidya AI",
#             f"""
#             <h2>Hello {first_name}</h2>
#             <p>Your registration is successful.</p>
#             <p>Platform: CareerVidya AI</p>
#             <p>Start exploring now</p>
#             <p>Thanks<br>CareerVidya Team</p>
#             """
#         )

#         # Send admin email
#         send_email(
#             "patyaldeepanshu05@gmail.com",
#             "New User Registered",
#             f"""
#             <h3>New User Registered</h3>
#             <p>Name: {first_name} {last_name}</p>
#             <p>Email: {email}</p>
#             """
#         )

#         return redirect('dashboard')

#     # Generate captcha
#     captcha = CaptchaStore.generate_key()
#     captcha_image = captcha_image_url(captcha)

#     return render(request, 'accounts/register.html', {
#         'captcha_key': captcha,
#         'captcha_image': captcha_image
#     })
@login_required
def edit_profile(request):
    profile = StudentProfile.objects.get(user=request.user)
    skills = Skill.objects.all()
    categories = Category.objects.all()

    if request.method == "POST":
        profile.interest = request.POST.get("interest", "")

        # -------- Update Skills --------
        selected_skill_ids = request.POST.getlist("skills")

        # delete old skills
        profile.student_skills.all().delete()

        # add new skills
        for skill_id in selected_skill_ids:
            StudentSkill.objects.create(
                student=profile,
                skill_id=skill_id,
                level=5
            )

        # profile picture
        if request.FILES.get("profile_picture"):
            profile.profile_picture = request.FILES["profile_picture"]

        profile.save()

        # 🔥🔥 CAREER RECALCULATION (MAIN FIX)
        last_result = CombinedCareerResult.objects.filter(student=profile).last()

        if last_result:
            career_obj, _, _ = calculate_combined_career(profile)

            # calculate new skill score
            user_skills = {
                ss.skill.name.lower(): ss.level
                for ss in profile.student_skills.select_related("skill")
            }

            skill_score = 0
            if career_obj:
                career_skills = {
                    s.name.lower()
                    for s in career_obj.required_skills.all()
                }
                matched = set(user_skills.keys()) & career_skills
                skill_score = sum(user_skills[s] for s in matched)

            # update result
            last_result.suggested_career = career_obj
            last_result.skill_score = skill_score
            last_result.total_score = last_result.quiz_score + skill_score
            last_result.save()

        messages.success(request, "Profile updated & career recalculated ✅")
        return redirect("dashboard")

    # -------- GET --------
    student_skill_ids = profile.student_skills.values_list("skill_id", flat=True)

    return render(request, "accounts/edit_profile.html", {
        "profile": profile,
        "skills": skills,
        "categories" : categories,
        "student_skill_ids": student_skill_ids,
    })

def calculate_combined_career(profile):

    user_skills = {
        ss.skill.name.strip().lower(): ss.level
        for ss in profile.student_skills.select_related("skill")
    }

    career_scores = []

    for career in Career.objects.prefetch_related("required_skills").all():

        career_skills = [
            skill.name.strip().lower()
            for skill in career.required_skills.all()
        ]

        if not career_skills:
            continue

        total_score = 0

        for skill in career_skills:
            user_level = user_skills.get(skill, 0)

            if user_level > 0:
                # normalize level (0–1)
                total_score += user_level / 10
            else:
                total_score += 0

        # final percentage
        skill_percentage = (total_score / len(career_skills)) * 100

        career_scores.append((career, round(skill_percentage)))

    # sort best → worst
    career_scores.sort(key=lambda x: x[1], reverse=True)

    top_career = career_scores[0][0] if career_scores else None

    return top_career, career_scores, {}
   
@login_required
def career_detail(request, career_id):
    career = get_object_or_404(Career, id=career_id)

    # Split comma-separated fields into lists
    courses = career.recommended_courses.split(',') if career.recommended_courses else []
    roadmap_steps = career.roadmap.split(',') if career.roadmap else []

    return render(request, 'accounts/career_detail.html', {
        'career': career,
        'courses': courses,
        'roadmap_steps': roadmap_steps,
    })

def logout_view(request):
    logout(request)
    return redirect('login')

def is_admin(user):
    return user.is_authenticated and user.is_staff

# 🧠 Admin Dashboard
@staff_member_required
def admin_dashboard(request):
    total_users = User.objects.count()
    total_careers = Career.objects.count()
    total_skills = Skill.objects.count()
    total_categories = Category.objects.count()
    total_quiz_questions = CareerQuizQuestion.objects.count()
    total_quiz_results = CombinedCareerResult.objects.count() 
    total_resumes = ResumeAnalysis.objects.count() 

    recent_students = StudentProfile.objects.select_related('user').order_by('-id')[:10]
    resumes = ResumeAnalysis.objects.select_related('user').order_by('-created_at')[:10]


    context = {
        'total_users': total_users,
        'total_careers': total_careers,
        'total_skills': total_skills,
        'total_categories': total_categories,
        "total_quiz_questions": total_quiz_questions,
        "total_quiz_results": total_quiz_results,
        'recent_students': recent_students,
        'resumes': resumes,
        'total_resumes': total_resumes,
    }

    return render(request, 'accounts/admin/dashboard.html', context)

@staff_member_required
def resume_list(request):
    resumes = ResumeAnalysis.objects.select_related('user').order_by('-created_at')

    return render(request, 'accounts/admin/resume_list.html', {
        'resumes': resumes
    })

@staff_member_required
def admin_users(request):
    search = request.GET.get('search', '')
    status = request.GET.get('status', '')

    users = User.objects.all().order_by('-id')  # 👈 latest first

    # 🔍 Search (username + email)
    if search:
        users = users.filter(
            Q(username__icontains=search) |
            Q(email__icontains=search)
        )

    # 🎯 Status filter
    if status == 'active':
        users = users.filter(is_active=True)
    elif status == 'inactive':
        users = users.filter(is_active=False)

    # 📄 Pagination
    paginator = Paginator(users, 5)  # 👈 5 users per page
    page_number = request.GET.get('page')
    users = paginator.get_page(page_number)

    context = {
        'users': users,
        'search': search,
        'status': status
    }

    return render(request, 'accounts/admin/users.html', context)


@staff_member_required
def admin_user_edit(request, user_id):
    user = get_object_or_404(User, id=user_id)
    form = UserUpdateForm(request.POST or None, instance=user)

    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('admin_users')

    return render(request, 'accounts/admin/user_edit.html', {'form': form})


@staff_member_required
@require_POST  # ensures only POST method is allowed
def admin_user_delete(request, user_id):
    user = get_object_or_404(User, id=user_id)
    user.delete()
    messages.success(request, "User deleted successfully 🗑️")
    return redirect('admin_users')

@staff_member_required
def admin_user_add(request):
    form = UserUpdateForm(request.POST or None)  # ya UserCreationForm agar new user
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('admin_users')

    return render(request, 'accounts/admin/user_edit.html', {'form': form})


@staff_member_required
@require_POST
def admin_users_bulk_delete(request):
    user_ids = request.POST.getlist('user_ids')  # checkbox ids
    if user_ids:
        User.objects.filter(id__in=user_ids).delete()
    messages.success(request, "Selected users deleted successfully 🗑️")
    return redirect('admin_users')
# ================= CAREERS =================
@staff_member_required
def admin_careers(request):
    search = request.GET.get('search', '')
    careers = Career.objects.all().order_by('-id')  # latest first

    # 🔍 Search by name / description
    if search:
        careers = careers.filter(
            Q(name__icontains=search) |
            Q(description__icontains=search)
        )

    # 📄 Pagination
    paginator = Paginator(careers, 5)  # 5 careers per page
    page_number = request.GET.get('page')
    careers = paginator.get_page(page_number)

    return render(request, 'accounts/admin/careers.html', {
        'careers': careers,
        'search': search
    })

@staff_member_required
def admin_career_add(request):
    form = CareerForm(request.POST or None, request.FILES or None)

    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Career added successfully ✅")
        return redirect('admin_careers')

    return render(request, 'accounts/admin/career_form.html', {
        'form': form
    })


@staff_member_required
def admin_career_edit(request, career_id):
    career = get_object_or_404(Career, id=career_id)
    form = CareerForm(request.POST or None, request.FILES or None, instance=career)

    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Career updated successfully ✨")
        return redirect('admin_careers')

    return render(request, 'accounts/admin/career_form.html', {
        'form': form
    })
   

@staff_member_required
def admin_career_delete(request, career_id):
    career = get_object_or_404(Career, id=career_id)
    career.delete()
    return redirect('admin_careers')


@staff_member_required
def admin_skills(request):
    search = request.GET.get('search', '')
    skills = Skill.objects.all().order_by('-id')  # latest first

    # 🔍 Search by name
    if search:
        skills = skills.filter(name__icontains=search)

    # Pagination
    paginator = Paginator(skills, 5)  # 5 skills per page
    page_number = request.GET.get('page')
    skills = paginator.get_page(page_number)

    return render(request, 'accounts/admin/skills.html', {
        'skills': skills,
        'search': search
    })


@staff_member_required
@require_POST
def admin_skills_bulk_delete(request):
    skill_ids = request.POST.getlist('skill_ids')
    if skill_ids:
        Skill.objects.filter(id__in=skill_ids).delete()
        messages.success(request, "Selected skills deleted successfully 🧠")
    return redirect('admin_skills')


@staff_member_required
def admin_skill_add(request):
    form = SkillForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Skill added successfully 🧠")

        return redirect('admin_skills')
    return render(request, 'accounts/admin/skill_form.html', {'form': form})

@staff_member_required
def admin_skill_edit(request, skill_id):
    skill = get_object_or_404(Skill, id=skill_id)
    form = SkillForm(request.POST or None, instance=skill)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('admin_skills')
    return render(request, 'accounts/admin/skill_form.html', {'form': form})

@staff_member_required
def admin_skill_delete(request, skill_id):
    skill = get_object_or_404(Skill, id=skill_id)
    skill.delete()
    return redirect('admin_skills')


def contact_view(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data['name']
            user_email = form.cleaned_data['email']
            subject = form.cleaned_data['subject']
            message = form.cleaned_data['message']

            full_message = f"Message from {name} ({user_email}):\n\n{message}"

            email_message = Mail(
                from_email='patyaldeepanshu05@gmail.com',  # Verified sender in SendGrid
                to_emails='patyaldeepanshu05@gmail.com',   # Jahan message receive karna hai
                subject=subject,
                plain_text_content=full_message,
            )

            try:
                sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
                sg.send(email_message)
                messages.success(request, "Your message has been sent! ✅")
            except Exception as e:
                print(str(e))
                messages.error(request, "Something went wrong. Please try again.")

            return redirect('contact')
    else:
        form = ContactForm()

    return render(request, 'accounts/contact.html', {'form': form})


@login_required
def career_quiz(request):

    # ---------- Get Profile Safely ----------
    try:
        profile = StudentProfile.objects.get(user=request.user)
    except StudentProfile.DoesNotExist:
        messages.error(request, "Student profile not found.")
        return redirect("dashboard")

    if not profile.student_skills.exists() or not profile.skills:
        messages.error(request, "Please select your skills and interests first!")
        return redirect("dashboard")

    # ---------- Check Previous Result ----------
    last_result = CombinedCareerResult.objects.filter(
        student=profile
    ).last()

    if last_result and not request.GET.get("retake") and request.method != "POST":
        messages.info(request, "You have already attempted the quiz.")
        return redirect("dashboard")

    # ---------- Load Questions ----------
    questions = CareerQuizQuestion.objects.prefetch_related("options").all()

    # ================= POST SUBMIT =================
    if request.method == "POST":

        scores = {}
        unanswered = False

        # -------- Collect Answers --------
        for question in questions:
            selected_option_id = request.POST.get(f"question_{question.id}")

            if not selected_option_id:
                unanswered = True
                continue

            try:
                option = CareerQuizOption.objects.get(id=selected_option_id)

                if option.category:
                    # ✅ FIX: use category.id (safe key)
                    scores[option.category.id] = (
                        scores.get(option.category.id, 0) + option.weight
                    )

            except CareerQuizOption.DoesNotExist:
                continue

        # -------- Validation --------
        if unanswered:
            messages.error(request, "Please answer all questions.")
            return redirect("career_quiz")

        if not scores:
            messages.error(request, "Something went wrong. Try again.")
            return redirect("career_quiz")

        # -------- Top 2 Personality Categories --------
        sorted_categories = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_categories_ids = [cat[0] for cat in sorted_categories[:2]]

        # -------- Get Careers from Top Categories --------
        careers = Career.objects.filter(
            category__id__in=top_categories_ids
        ).prefetch_related("required_skills")

        if not careers.exists():
            messages.error(request, "No careers found for your profile.")
            return redirect("career_quiz")

        # -------- Prepare User Skills --------
        user_skills = {
            ss.skill.name.strip().lower(): ss.level
            for ss in profile.student_skills.select_related("skill")
        }

        best_career = None
        best_total_score = 0
        best_quiz_score = 0
        best_skill_score = 0
        skill_gap = []

        # -------- Normalize personality max --------
        max_personality = max(scores.values()) if scores else 1

        # -------- Evaluate Each Career --------
        for career in careers:

            # Personality score
            personality_score = scores.get(career.category.id, 0)

            # ✅ Normalize personality (0–100)
            personality_score_normalized = (personality_score / max_personality) * 100

            # Career required skills
            career_skills = {
                skill.name.strip().lower()
                for skill in career.required_skills.all()
            }

            if not career_skills:
                continue

            # -------- Skill Score (FIXED LOGIC) --------
            total_skill_score = 0

            for skill in career_skills:
                level = user_skills.get(skill, 0)
                total_skill_score += level / 10   # normalize (0–1)

            skill_score = (total_skill_score / len(career_skills)) * 100

            # -------- Skill Gap --------
            career_skill_gap = career_skills - set(user_skills.keys())

            # -------- FINAL SCORE (BALANCED AI) --------
            total_score = (0.5 * personality_score_normalized) + (0.5 * skill_score)

            if total_score > best_total_score:
                best_total_score = total_score
                best_career = career
                best_quiz_score = round(personality_score_normalized)
                best_skill_score = round(skill_score)
                skill_gap = list(career_skill_gap)

        if not best_career:
            messages.error(request, "No suitable career found.")
            return redirect("career_quiz")

        # -------- Match Percentage (FINAL FIX) --------
        match_percentage = round(best_total_score)

        # -------- Save / Update Result --------
        CombinedCareerResult.objects.update_or_create(
            student=profile,
            defaults={
                "suggested_career": best_career,
                "quiz_score": best_quiz_score,
                "skill_score": best_skill_score,
                "total_score": best_total_score,
                "match_percentage": match_percentage,
                "skill_gap": skill_gap,
            }
        )

        profile.personality_quiz_completed = True
        profile.save()

        messages.success(request, "Quiz submitted successfully!")
        return redirect("career_result")

    # ================= GET REQUEST =================
    context = {
        "questions": questions,
        "retake_mode": bool(request.GET.get("retake")),
    }

    return render(request, "accounts/quiz.html", context)
@login_required
def admin_quiz_list(request):
    questions = CareerQuizQuestion.objects.all()
    return render(request, "accounts/admin/quiz_list.html", {"questions": questions})

@login_required
def admin_quiz_add(request):
    categories = Category.objects.all()

    if request.method == "POST":
        question_text = request.POST.get("question")
        if not question_text:
            return render(request, "accounts/admin/quiz_add.html", {
                "categories": categories,
                "error": "Question is required."
            })

        question = CareerQuizQuestion.objects.create(question=question_text)

        for i in range(1, 4):  # assuming 3 options per question
            opt_text = request.POST.get(f"option{i}_text")
            category_id = request.POST.get(f"option{i}_category")
            weight = request.POST.get(f"option{i}_weight")

            if opt_text and category_id:
                CareerQuizOption.objects.create(
                    question=question,
                    option_text=opt_text,
                    category_id=category_id,
                    weight=int(weight or 1)
                )

        return redirect('admin_quiz_list')

    return render(request, "accounts/admin/quiz_add.html", {"categories": categories})

@login_required
def admin_quiz_edit(request, id):
    question = get_object_or_404(CareerQuizQuestion, id=id)
    options = question.options.all()
    categories = Category.objects.all()

    if request.method == "POST":
        question.question = request.POST.get("question")
        question.save()

        for i, opt in enumerate(options, start=1):
            opt.option_text = request.POST.get(f"option{i}_text")
            opt.category_id = request.POST.get(f"option{i}_category")
            opt.weight = int(request.POST.get(f"option{i}_weight") or 1)
            opt.save()

        return redirect('admin_quiz_list')

    return render(request, "accounts/admin/quiz_edit.html", {
        "question": question,
        "options": options,
        "categories": categories
    })

@login_required
def admin_quiz_delete(request, id):
    question = get_object_or_404(CareerQuizQuestion, id=id)
    question.delete()
    return redirect('admin_quiz_list')
@staff_member_required
def admin_quiz_results(request):

    # ✅ Correct model use karo
    results = CombinedCareerResult.objects.select_related(
        "student__user",
        "suggested_career"
    ).order_by("-created_at")

    careers = Career.objects.all()

    if request.method == "POST":
        result_id = request.POST.get("result_id")
        career_id = request.POST.get("career")

        result = get_object_or_404(CombinedCareerResult, id=result_id)

        if career_id:
            result.suggested_career_id = career_id
        else:
            result.suggested_career = None

        result.save()
        return redirect("admin_quiz_results")

    return render(request, "accounts/admin/quiz_results.html", {
        "results": results,
        "careers": careers,
    })

from django.db.models import Q

@login_required
def skill_based_careers(request):
    profile = StudentProfile.objects.get(user=request.user)

    # Correct fetch of skills
    user_skills = Skill.objects.filter(studentskill__student=profile)

    careers = Career.objects.none()

    # 1️⃣ Skill match
    if user_skills.exists():
        careers = Career.objects.filter(required_skills__in=user_skills)

    # 2️⃣ Interest match
    if profile.interest:
        interest_based = Career.objects.filter(category__name__icontains=profile.interest)
        careers = careers | interest_based

    careers = careers.distinct()

    return render(request, 'accounts/skill_based.html', {
        'careers': careers
    })

import subprocess
@staff_member_required
def run_migrations(request):
    core_path = "/opt/render/project/src/AI_Career_Guidance/core"

    # Run all migrations safely
    result = subprocess.run(
        ["python", "manage.py", "migrate", "--noinput"],
        cwd=core_path,
        capture_output=True,
        text=True
    )

    return HttpResponse(f"<pre>{result.stdout}\n{result.stderr}</pre>")
def create_superuser(request):
    # Ye secret key ya simple check laga do taki koi aur access na kare
    if request.GET.get("key") != "mysecret123":
        return HttpResponse("Not authorized", status=403)

    if not User.objects.filter(username="admin").exists():
        User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="Admin@123"
        )
        return HttpResponse("Superuser created successfully!")
    return HttpResponse("Superuser already exists.")

@login_required
def admin_categories(request):
    categories = Category.objects.all().order_by('id')
    form = CategoryForm()

    if request.method == "POST":
        form = CategoryForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('admin_categories')  # redirect to same page

    context = {'categories': categories, 'form': form}
    return render(request, 'accounts/admin/admin_categories.html', context)


@login_required
def edit_category(request, pk):
    category = get_object_or_404(Category, pk=pk)
    form = CategoryForm(instance=category)

    if request.method == "POST":
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            return redirect('admin_categories')

    return render(request, 'accounts/admin/edit_category.html', {'form': form, 'category': category})


@login_required
def delete_category(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if request.method == "POST":
        category.delete()
        return redirect('admin_categories')
    return render(request, 'accounts/admin/delete_category.html', {'category': category})


def download_career_pdf(request, pk):
    career = get_object_or_404(Career, pk=pk)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []

    styles = getSampleStyleSheet()
    title_style = styles["Heading1"]
    normal_style = styles["BodyText"]

    # Custom style for links (blue + underline)
    link_style = ParagraphStyle(
        'link_style',
        parent=normal_style,
        textColor=colors.blue,
        underline=True,
    )

    # Helper function to convert <a href> tags to ReportLab <link href="...">Text</link>
    def parse_links(text):
        def replace_link(match):
            url = match.group(1)
            link_text = match.group(2)
            return f'<font color="blue"><u><a href="{url}">{link_text}</a></u></font>'

        # Replace links
        result = re.sub(r"<a href=['\"](.*?)['\"]>(.*?)</a>", replace_link, text)

        # Fix <br> tag issue
        result = result.replace("<br>", "<br/>")

        return Paragraph(result, normal_style)
    

    # Title
    elements.append(Paragraph(f"{career.name} Career Guide", title_style))
    elements.append(Spacer(1, 0.4 * inch))

    # Description
    description = career.description or "Coming soon"
    elements.append(Paragraph("<b>Description:</b>", normal_style))
    elements.append(Spacer(1, 0.1 * inch))
    for line in description.splitlines():
        if line.strip():
            elements.append(Paragraph(line.strip(), normal_style))
    elements.append(Spacer(1, 0.3 * inch))

    # Average Salary
    elements.append(Paragraph(f"<b>Average Salary:</b> {career.average_salary or 'Not specified'}", normal_style))
    elements.append(Spacer(1, 0.3 * inch))

    elements.append(Paragraph("<b>Required Skills:</b>", normal_style))
    skills = career.required_skills.all()

    if skills:
        skill_list = ListFlowable(
            [ListItem(Paragraph(skill.name, normal_style)) for skill in skills],
            bulletType='bullet',
            leftIndent=20,
        )
        elements.append(skill_list)

    elements.append(Spacer(1, 0.3 * inch))

    # Future Scope with bullets
    elements.append(Paragraph("<b>Future Scope:</b>", normal_style))
    future_scope = career.future_scope or ""
    bullets = [line.strip() for line in future_scope.splitlines() if line.strip()]
    if bullets:
        bullet_list = ListFlowable(
            [ListItem(Paragraph(b, normal_style)) for b in bullets],
            bulletType='bullet',
            leftIndent=20,
        )
        elements.append(bullet_list)
    elements.append(Spacer(1, 0.3 * inch))

    # Recommended Courses with bullets and clickable links
    elements.append(Paragraph("<b>Recommended Courses:</b>", normal_style))
    courses = career.recommended_courses.split(',') if career.recommended_courses else []
    if courses:
        course_list = ListFlowable(
            [ListItem(parse_links(c.strip())) for c in courses],
            bulletType='bullet',
            leftIndent=20,
        )
        elements.append(course_list)
    elements.append(Spacer(1, 0.3 * inch))

    # Career Roadmap with bullets and clickable links
    elements.append(Paragraph("<b>Career Roadmap:</b>", normal_style))
    roadmap = career.roadmap.split('<br>') if career.roadmap else []
    if roadmap:
        roadmap_list = ListFlowable(
            [ListItem(parse_links(r.strip())) for r in roadmap],
            bulletType='bullet',
            leftIndent=20,
        )
        elements.append(roadmap_list)
    elements.append(Spacer(1, 0.3 * inch))

    # Build PDF
    doc.build(elements)
    buffer.seek(0)

    return HttpResponse(
        buffer,
        content_type='application/pdf',
        headers={'Content-Disposition': f'attachment; filename="{career.name}_guide.pdf"'},
    )

def calculate_dynamic_career(result, profile):
    """
    Returns dynamic career suggestion based on quiz result and student profile.

    :param result: CareerQuizResult instance
    :param profile: StudentProfile instance
    :return: (career_object, description, final_category, final_score, category_scores)
    """

    category_scores = {}
    final_score = result.total_score
    final_category = None

    # Adjust this according to your actual model
    if hasattr(result, 'answers'):
        for answer in result.answers.all():
            cat = getattr(answer, 'category', None)
            score = getattr(answer, 'score', 0)
            if cat:
                category_scores[cat] = category_scores.get(cat, 0) + score

    # Determine highest scoring category
    if category_scores:
        final_category = max(category_scores, key=category_scores.get)

    # Map final category or total score to a Career
    career = None
    description = "No description available."

    if final_category:
        career = Career.objects.filter(category=final_category).first()
    else:
        # fallback based on total score
        if final_score >= 12:
            career = Career.objects.filter(name="Data Scientist").first()
        elif final_score >= 8:
            career = Career.objects.filter(name="Web Developer").first()
        else:
            career = Career.objects.filter(name="Designer").first()

    if career:
        description = career.description or "No description available."

    return career, description, final_category, final_score, category_scores



def edit_quiz_question(request, id):
    question = CareerQuizQuestion.objects.get(id=id)
    options = CareerQuizOption.objects.filter(question=question)
    categories = Category.objects.all()   # 👈 ADD THIS

    return render(request, "accounts/admin/quiz_edit.html", {
        "question": question,
        "options": options,
        "categories": categories,   # 👈 PASS THIS
    })

@login_required
def admin_quiz_result_delete(request, id):
    result = get_object_or_404(CareerQuizResult, id=id)
    result.delete()
    return redirect('admin_quiz_results')


@login_required
def career_result(request):
    profile = StudentProfile.objects.get(user=request.user)

    result = CombinedCareerResult.objects.filter(
        student=profile
    ).select_related("suggested_career").last()

    if not result:
        messages.error(request, "No quiz result found.")
        return redirect("career_quiz")

    career = result.suggested_career

    # ---------- Prepare skill gap & match percentage ----------
    user_skills = {ss.skill.name.lower(): ss.level for ss in profile.student_skills.all()}

    career_skills = {s.name.lower() for s in career.required_skills.all()} if career else set()

    matched_skills = set(user_skills.keys()) & career_skills
    skill_score = sum(user_skills[s] for s in matched_skills)

    skill_gap = list(career_skills - set(user_skills.keys()))

    personality_score = result.quiz_score
    total_score = result.total_score

    # Match Percentage
    max_personality_score = personality_score or 1
    max_skill_score = sum(user_skills.values()) if user_skills else 1
    max_total = (0.6 * max_personality_score) + (0.4 * max_skill_score)
    match_percentage = round((total_score / max_total) * 100) if max_total else 0

    # Optional: breakdown scores
    scores = {
        "Personality": personality_score,
        "Skills": skill_score,
    }

    context = {
        "career": career.name if career else "No Career",
        "career_obj": career,   # clickable link in template
        "description": career.description if career else "",
        "final_score": total_score,
        "scores": scores,
        "match_percentage": match_percentage,
        "skill_gap": skill_gap,
    }

    return render(request, "accounts/result.html", context)


def admin_student_profiles(request):
    students = StudentProfile.objects.select_related('user').all()
    return render(request, 'accounts/admin/student_profiles.html', {'students': students})



# def import_careers_temp(request):
#     if not request.user.is_superuser:
#         return HttpResponse("❌ Not authorized", status=403)

#     # 🔥 PATH AUTO DETECT
#     possible_paths = [
#         os.path.join(settings.BASE_DIR, "core", "data.json"),
#         os.path.join(settings.BASE_DIR, "AI_Career_Guidance", "core", "data.json"),
#         os.path.join(os.getcwd(), "core", "data.json"),
#         os.path.join(os.getcwd(), "AI_Career_Guidance", "core", "data.json"),
#     ]

#     file_path = None
#     for path in possible_paths:
#         if os.path.exists(path):
#             file_path = path
#             break

#     if not file_path:
#         return HttpResponse("❌ data.json file not found!", status=404)

#     # 🔥 LOAD JSON
#     try:
#         with open(file_path, 'r', encoding='utf-8-sig') as f:
#             data = json.load(f)
#     except UnicodeDecodeError:
#         with open(file_path, 'r', encoding='utf-16') as f:
#             data = json.load(f)
#     except json.JSONDecodeError:
#         return HttpResponse("❌ JSON format invalid!", status=400)

#     careers = data if isinstance(data, list) else [data]

#     # 🔥 IMPORT LOOP
#     for c in careers:
#         if not isinstance(c, dict):
#             continue

#         fields = c.get('fields', {})

#         # ✅ CATEGORY
#         category_name = fields.get('category')
#         category_obj = None

#         if category_name:
#             category_obj, _ = Category.objects.get_or_create(name=category_name)

#         # ✅ CAREER
#         career_obj, created = Career.objects.get_or_create(
#             name=fields.get('name', 'Unnamed Career'),
#             defaults={
#                 'description': fields.get('description', ''),
#                 'category': category_obj,
#                 'average_salary': fields.get('average_salary', ''),
#                 'future_scope': fields.get('future_scope', ''),
#                 'recommended_courses': fields.get('recommended_courses', ''),
#                 'roadmap': fields.get('roadmap', ''),
#                 'imported_from_json': True,
#             }
#         )

#         # 🔥 SKILLS (MAIN FIX)
#         skills = fields.get('required_skills', [])

#         for skill_name in skills:

#             skill_obj, created = Skill.objects.get_or_create(name=skill_name)

#             # 🔥 DIRECT CATEGORY ASSIGN (BEST LOGIC)
#             if category_obj:
#                 skill_obj.category = category_obj
#                 skill_obj.save()

#             career_obj.required_skills.add(skill_obj)

#     return HttpResponse("✅ Careers + Skills + Categories imported successfully 🚀")

# def delete_json_careers(request):
#     if not request.user.is_superuser:
#         return HttpResponse("❌ Not authorized", status=403)

#     # Delete only careers imported from JSON
#     deleted_count, _ = Career.objects.filter(imported_from_json=True).delete()
    
#     return HttpResponse(f"✅ {deleted_count} careers deleted successfully!")


# def delete_all_careers(request):
#     if not request.user.is_superuser:
#         return HttpResponse("❌ Not authorized", status=403)

#     deleted_count, _ = Career.objects.all().delete()
#     return HttpResponse(f"✅ {deleted_count} careers deleted successfully!")



# def import_courses_temp(request):
#     if not request.user.is_superuser:
#         return HttpResponse("❌ Not authorized", status=403)

#     # 🔥 AUTO-DETECT PATH
#     possible_paths = [
#         os.path.join(settings.BASE_DIR, "courses.json"),
#         os.path.join(settings.BASE_DIR, "core", "courses.json"),
#         os.path.join(os.getcwd(), "courses.json"),
#         os.path.join(os.getcwd(), "core", "courses.json"),
#     ]

#     file_path = None
#     for path in possible_paths:
#         if os.path.exists(path):
#             file_path = path
#             break

#     if not file_path:
#         return HttpResponse("❌ courses.json file not found!", status=404)

#     # Load JSON safely
#     try:
#         with open(file_path, 'r', encoding='utf-8-sig') as f:
#             data = json.load(f)
#     except UnicodeDecodeError:
#         with open(file_path, 'r', encoding='utf-16') as f:
#             data = json.load(f)
#     except json.JSONDecodeError:
#         return HttpResponse("❌ JSON format is invalid!", status=400)

#     # Ensure list
#     if isinstance(data, dict):
#         courses_list = [data]
#     elif isinstance(data, list):
#         courses_list = data
#     else:
#         return HttpResponse("❌ Invalid JSON structure!", status=400)

#     # Import courses
#     for c in courses_list:
#         if not isinstance(c, dict):
#             continue

#         # Category
#         category_name = c.get('category')
#         category_obj = None
#         if category_name:
#             try:
#                 category_obj = Category.objects.get(name=category_name)
#             except Category.DoesNotExist:
#                 print(f"Category '{category_name}' not found. Skipping '{c.get('title')}'")
#                 continue

#         # Course
#         Course.objects.get_or_create(
#             title=c.get('title', 'Unnamed Course'),
#             defaults={
#                 'description': c.get('description', ''),
#                 'content_type': c.get('content_type', 'image'),
#                 'image': c.get('image', ''),
#                 'video_url': c.get('video_url', ''),
#                 'price': c.get('price', ''),
#                 'category': category_obj,
#                 'level': c.get('level', ''),
#                 'rating': c.get('rating', 0),
#                 'duration': c.get('duration', ''),
#                 'link': c.get('link', ''),
#                 'is_featured': c.get('is_featured', False),
#                 'imported_from_json': True,
#             }
#         )

#     return HttpResponse("✅ Courses imported successfully!")


# def delete_all_courses(request):
#     if not request.user.is_superuser:
#         return HttpResponse("❌ Not authorized", status=403)

#     deleted_count, _ = Course.objects.all().delete()
#     return HttpResponse(f"✅ {deleted_count} courses deleted successfully!")