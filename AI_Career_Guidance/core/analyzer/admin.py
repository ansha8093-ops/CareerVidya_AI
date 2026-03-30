from django.contrib import admin
from .models import ResumeAnalysis
from django.utils.html import format_html


@admin.register(ResumeAnalysis)
class ResumeAnalysisAdmin(admin.ModelAdmin):
    list_display = ('user', 'job_role', 'created_at')

def view_resume(self, obj):
    return format_html(f'<a href="{obj.resume.url}" target="_blank">View</a>')

view_resume.short_description = "Resume"