from random import shuffle
import logging

from django.db import models
from django.contrib.auth.models import User


LOG = logging.getLogger(__name__)


class Game(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    owner = models.ForeignKey('auth.User', related_name='games', on_delete=models.CASCADE, null=True)
    name = models.CharField(max_length=256, blank=True, default="")
    num_players = models.IntegerField()
    num_teams = models.IntegerField()
    score_to_play_to = models.IntegerField()
    passcode_required = models.BooleanField(blank=True, default=False)
    passcode = models.CharField(max_length=256, blank=True, default="")
    single_player = models.BooleanField(blank=False, default=True)
    players = models.ManyToManyField('auth.User')

    class Meta:
        ordering = ('created_at',)

    def get_status(self):
        if self.hands.count() == 0:
            return {
                'state': 'waiting_for_start',
                'metadata': {},
            }
        return self.hands.last().get_status()

    def start(self):
        if self.players.count() != self.num_players:
            raise ValidationError(f"Unable to start game, game requires {self.num_players} players, but {self.players.count()} have joined")

        hand = Hand.objects.create(game=self)
        LOG.info(f"Started hand {hand} on game {self}")

    def add_computer_player(self):
        computers = list(User.objects.filter(username__startswith="mkokotovich+computer").all())
        shuffle(computers)
        for player in computers:
            if not self.players.filter(id=player.id).exists():
                self.players.add(player)
                LOG.info(f"Added computer {player} to {self}")
                return


class Hand(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    game = models.ForeignKey(Game, related_name='hands', on_delete=models.CASCADE, null=True)

    def get_status(self):
        return {
            'state': 'bidding',
            'metadata': {
                'hand': self.id,
            },
        }
