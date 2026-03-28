from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_customerfeedback'),
    ]

    operations = [
        migrations.AddField(
            model_name='customerprofile',
            name='phone_number',
            field=models.CharField(blank=True, max_length=10),
        ),
        migrations.AddField(
            model_name='sellerprofile',
            name='phone_number',
            field=models.CharField(blank=True, max_length=10),
        ),
    ]
