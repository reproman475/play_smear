# Generated by Django 4.1.2 on 2024-02-01 05:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('smear', '0040_remove_player_current_hand_game_points_won_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='game',
            name='scores_by_contestant',
            field=models.JSONField(default=dict),
        ),
    ]
