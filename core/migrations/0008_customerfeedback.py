from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_genre_productreview_and_genres'),
    ]

    operations = [
        migrations.CreateModel(
            name='CustomerFeedback',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('feedback_type', models.CharField(choices=[('FEEDBACK', 'Feedback'), ('COMPLAINT', 'Complaint')], default='FEEDBACK', max_length=12)),
                ('subject', models.CharField(max_length=180)),
                ('message', models.TextField()),
                ('status', models.CharField(choices=[('OPEN', 'Open'), ('IN_REVIEW', 'In Review'), ('RESOLVED', 'Resolved')], default='OPEN', max_length=12)),
                ('admin_note', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='feedback_entries', to='core.customerprofile')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
