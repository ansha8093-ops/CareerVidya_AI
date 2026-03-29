from django.db import migrations

def map_category_data(apps, schema_editor):
    Skill = apps.get_model('accounts', 'Skill')
    Category = apps.get_model('accounts', 'Category')

    for skill in Skill.objects.all():
        # Agar category NULL hai ya wrong hai
        if not skill.category_id:
            # try matching by skill name logic (customize if needed)
            name = skill.name.strip().lower()

            # example mapping logic
            if "python" in name or "ai" in name:
                cat_name = "tech"
            elif "design" in name:
                cat_name = "design"
            else:
                cat_name = "other"

            category, _ = Category.objects.get_or_create(name=cat_name)
            skill.category = category
            skill.save()

class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0011_alter_skill_category'),
    ]

    operations = [
        migrations.RunPython(map_category_data),
    ]