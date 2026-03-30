from django.urls import path
from django.contrib.auth import views as auth_views
from .views import (
    home, login_view, register_view, dashboard, logout_view,
    edit_profile, career_detail,admin_quiz_result_delete,about_us,career_result,admin_student_profiles,refresh_captcha,run_migrations,create_superuser,
    # import_careers_temp,delete_json_careers,delete_all_careers,
# import_courses_temp,delete_all_courses,
    # admin panel views
    admin_dashboard, admin_users, admin_careers,contact_view,career_quiz,admin_quiz_add,admin_quiz_edit, resume_list,skill_based_careers,admin_categories,edit_category,delete_category,admin_quiz_results,
    admin_user_edit, admin_user_delete,admin_users_bulk_delete,admin_skills_bulk_delete,admin_quiz_list,admin_quiz_delete,edit_account,download_career_pdf,
    admin_career_add, admin_career_edit, admin_career_delete,admin_user_add,admin_skills,admin_skill_add,admin_skill_edit,admin_skill_delete)    

urlpatterns = [
    path('', home, name='home'),
    path('login/', login_view, name='login'),
    path('register/', register_view, name='register'),
    path('dashboard/', dashboard, name='dashboard'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('profile/edit/', edit_profile, name='edit_profile'),
    path('career/<int:career_id>/', career_detail, name='career_detail'),
    path('admin-panel/', admin_dashboard, name='admin_dashboard'),
    path('admin-panel/users/', admin_users, name='admin_users'),
    path('admin-panel/careers/', admin_careers, name='admin_careers'),
    path('admin-panel/users/edit/<int:user_id>/', admin_user_edit, name='admin_user_edit'),
    path('admin-panel/users/delete/<int:user_id>/', admin_user_delete, name='admin_user_delete'),
    path('admin-panel/users/add/', admin_user_add, name='admin_user_add'),
    path('admin-panel/careers/add/', admin_career_add, name='admin_career_add'),
    path('admin-panel/careers/edit/<int:career_id>/', admin_career_edit, name='admin_career_edit'),
    path('admin-panel/careers/delete/<int:career_id>/', admin_career_delete, name='admin_career_delete'),
    path('admin-panel/skills/', admin_skills, name='admin_skills'),
    path('admin-panel/skills/add/', admin_skill_add, name='admin_skill_add'),
    path('admin-panel/skills/edit/<int:skill_id>/', admin_skill_edit, name='admin_skill_edit'),
    path('admin-panel/skills/delete/<int:skill_id>/', admin_skill_delete, name='admin_skill_delete'),
    path('admin-panel/users/bulk-delete/', admin_users_bulk_delete, name='admin_users_bulk_delete'),
    path('admin-panel/skills/', admin_skills, name='admin_skills'),
    path('admin-panel/skills/bulk-delete/', admin_skills_bulk_delete, name='admin_skills_bulk_delete'),
    path('contact/', contact_view, name='contact'),
    path("career-quiz/",career_quiz, name="career_quiz"),
     path('admin-panel/manage-quiz/', admin_quiz_list, name='admin_quiz_list'),
    path('admin-panel/manage-quiz/add/',admin_quiz_add, name='admin_quiz_add'),
    path('admin-panel/manage-quiz/edit/<int:id>/',admin_quiz_edit, name='admin_quiz_edit'),
    path('admin-panel/manage-quiz/delete/<int:id>/',admin_quiz_delete, name='admin_quiz_delete'),
    path('skill-based/',skill_based_careers, name='skill_based'),
    path('categories/',admin_categories, name='admin_categories'),
    path('categories/edit/<int:pk>/',edit_category, name='edit_category'),
    path('categories/delete/<int:pk>/',delete_category, name='delete_category'),
    path("edit-account/",edit_account, name="edit_account"),
    path('career/<int:pk>/download/',download_career_pdf, name='download_career_pdf'),
    path('quiz-results/',admin_quiz_results, name='admin_quiz_results'),
    path('quiz-results/delete/<int:id>/', admin_quiz_result_delete, name='admin_quiz_result_delete'),
    path('about_us/',about_us, name='about_us'),
    path("career-result/", career_result, name="career_result"),
    path('admin-panel/students/', admin_student_profiles, name='admin_student_profiles'),
    path('password-reset/',
         auth_views.PasswordResetView.as_view(template_name='accounts/password_reset.html'),
         name='password_reset'),

    path('password-reset/done/',
            auth_views.PasswordResetDoneView.as_view(template_name='accounts/password_reset_done.html'),
            name='password_reset_done'),

    path('reset/<uidb64>/<token>/',
            auth_views.PasswordResetConfirmView.as_view(template_name='accounts/password_reset_confirm.html'),
            name='password_reset_confirm'),

    path('reset/done/',
            auth_views.PasswordResetCompleteView.as_view(template_name='accounts/password_reset_complete.html'),
            name='password_reset_complete'),
    
    path('refresh-captcha/', refresh_captcha, name='refresh_captcha'),
    path('dashboard/resumes/', resume_list, name='admin_resumes'),


    path('run-migrations/', run_migrations),
    path('create-superuser/', create_superuser, name='create_superuser'),
    # path('import-careers-temp/', import_careers_temp, name='import-careers-temp'),
    # path('delete-json-careers/', delete_json_careers, name='delete_json_careers'),
    # path('delete-all-careers/', delete_all_careers, name='delete_all_careers'),
    # path('import-courses-temp/', import_courses_temp),
    # path('delete-all-courses/', delete_all_courses),

]







    



  

