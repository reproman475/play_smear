# Generated by Django 2.1.2 on 2019-01-08 15:03

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('smear', '0010_game_players'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='game',
            name='num_joined',
        ),
    ]
