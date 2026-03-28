from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_chapter_chapter_file'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='payment_method',
            field=models.CharField(
                choices=[('CARD', 'Prepaid (Card)'), ('UPI', 'Prepaid (UPI)'), ('COD', 'Cash on Delivery')],
                default='COD',
                max_length=10,
            ),
        ),
    ]
