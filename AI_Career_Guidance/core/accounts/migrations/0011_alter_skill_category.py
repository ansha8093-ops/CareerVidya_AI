# accounts/migrations/0011_alter_skill_category.py
from django.db import migrations, models
import django.db.models.deletion

def fix_empty_category(apps, schema_editor):
    # Direct SQL to convert empty strings to NULL
    schema_editor.execute("""
        UPDATE accounts_skill
        SET category = NULL
        WHERE category = '';
    """)

class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0010_skill_category'),
    ]

    operations = [
        migrations.RunPython(fix_empty_category),
        migrations.AlterField(
            model_name='skill',
            name='category',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='accounts.category'),
        ),
    ]