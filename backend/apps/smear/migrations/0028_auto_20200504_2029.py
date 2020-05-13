# Generated by Django 3.0.5 on 2020-05-04 20:29

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('smear', '0027_auto_20200430_1852'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='trick',
            name='cards_played',
        ),
        migrations.CreateModel(
            name='Play',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('card', models.CharField(max_length=2)),
                ('player', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='plays', to='smear.Player')),
                ('trick', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='plays', to='smear.Trick')),
            ],
        ),
    ]