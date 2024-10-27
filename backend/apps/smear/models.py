import logging
from random import shuffle

from django.contrib.auth.models import User
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import F
from django.utils.functional import cached_property
from rest_framework.exceptions import ValidationError

from apps.smear.cards import SUIT_CHOICES, Card, Deck

LOG = logging.getLogger(__name__)


class Game(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    owner = models.ForeignKey("auth.User", related_name="games", on_delete=models.SET_NULL, null=True)
    name = models.CharField(max_length=256, blank=True, default="")
    num_players = models.IntegerField()
    # num_spectators = models.IntegerField()
    num_teams = models.IntegerField()
    score_to_play_to = models.IntegerField()
    passcode_required = models.BooleanField(blank=True, default=False)
    passcode = models.CharField(max_length=256, blank=True, default="")
    single_player = models.BooleanField(blank=False, default=True)
    players = models.ManyToManyField("auth.User", through="Player")
    state = models.CharField(max_length=1024, blank=True, default="")
    next_dealer = models.ForeignKey(
        "Player", related_name="games_next_dealer", on_delete=models.SET_NULL, null=True, blank=True
    )
    # {
    #     "id1": [0, 3, 3, 5],
    #     "id2": [2, 2, 4, 7],
    # }
    scores_by_contestant = models.JSONField(default=dict)
    must_bid_to_win = models.BooleanField(blank=True, default=False)

    # Available states
    STARTING = "starting"
    NEW_HAND = "new_hand"
    BIDDING = "bidding"
    DECLARING_TRUMP = "declaring_trump"
    PLAYING_TRICK = "playing_trick"
    GAME_OVER = "game_over"

    def set_state(self, new_state, save=True):
        # For now just set state. At some point we might invalidate cache
        self.state = new_state
        if save:
            self.save()

    class Meta:
        ordering = ("created_at",)

    def __str__(self):
        return f"{self.name} ({self.id})"

    @property
    def current_hand(self):
        return self.hands.last()

    @property
    def current_trick(self):
        hand = self.hands.last()
        return hand.tricks.last() if hand else None

    def start_new_hand_in_contestants_scores(self):
        if not self.scores_by_contestant:
            # Initialize the dict
            contestants_qs = self.teams.all() if self.num_teams else self.player_set.all()
            self.scores_by_contestant = {str(contestant.id): [0] for contestant in contestants_qs}
        else:
            # Otherwise, just add one more entry
            for contestant_id, scores in self.scores_by_contestant.items():
                # Add the last score as the starting value for the next score
                scores.append(scores[-1])

    def add_to_contestants_current_hand_score(self, contestant_id, score_delta):
        scores = self.scores_by_contestant[contestant_id]
        scores[-1] = scores[-1] + score_delta

    def next_player(self, player):
        # TODO determine if this is really more performant
        # next_seat = (player.seat + 1) % self.num_players
        # return self.player_set.get(seat=next_seat)
        return player.plays_before

    def create_initial_teams(self):
        teams = []
        for i in range(0, self.num_teams):
            color = Team.COLORS[i]
            teams.append(Team(game=self, name=f"Team {color}", color=color))
        teams.append(Team(game=self, name="Spectators", color="spectator"))

        Team.objects.bulk_create(teams)

    def add_computer_players(self, count):
        if self.player_set.count() + count > self.num_players:
            raise ValidationError(f"Unable to add {count} computers, game already contains {self.num_players} players")

        computers_to_add = []
        computers_already_in_game = self.players.values_list("id", flat=True)
        computers = list(
            User.objects.filter(username__startswith="mkokotovich+computer",).exclude(
                id__in=computers_already_in_game,
            )
        )
        shuffle(computers)
        for computer in computers[:count]:
            computer_player = Player(game=self, user=computer, is_computer=True)
            computers_to_add.append(computer_player)
        computers_added = Player.objects.bulk_create(computers_to_add)
        computer_strs = [str(comp) for comp in computers_added]
        LOG.info(f"Added computers {', '.join(computer_strs)} to {self}")

    def add_computer_player(self):
        num_spectators = 0
        for player in self.player_set.all():
            if player.is_spectator:
                num_spectators += 1
        if self.players.count() - num_spectators >= self.num_players:
            raise ValidationError(f"Unable to add computer, game already contains {self.num_players} players")

        computers = list(User.objects.filter(username__startswith="mkokotovich+computer").all())
        shuffle(computers)
        for computer in computers:
            if not self.players.filter(id=computer.id).exists():
                computer_player = Player.objects.create(game=self, user=computer, is_computer=True)
                LOG.info(f"Added computer {computer} to {self}")
                return computer_player

    def autofill_teams(self):
        if self.num_teams == 0:
            return
        teams = list(self.teams.all())[0:-1]
        spec_team = list(self.teams.all())[-1]
        # players = list(self.player_set.all())
        players = []
        spectators = []
        for player in self.player_set.all():
            if not player.is_spectator:
                players.append(player)
            else:
                spectators.append(player)


        shuffle(players)

        for player_num, player in enumerate(players):
            team_num = player_num % self.num_teams
            player.team = teams[team_num]
            LOG.info(f"Autofilling teams for game {self}. Added {player} to team {teams[team_num]}")

        for player_num, player in enumerate(spectators):
            player.team = spec_team
            LOG.info(f"Autofilling teams for game {self}. Added {player} to team {spec_team}")
        Player.objects.bulk_update(players, ["team"])
        print(f"ADDED {spectators} to spectator team")
        Player.objects.bulk_update(spectators, ["team"])

    def reset_teams(self):
        for team in list(self.teams.all()):
            team.members.clear()

    def start_game(self):
        num_spectators = 0
        print(f"TYPE OF PLAYER SET: {type(self.player_set)}")
        
        for player in self.player_set.all():
            if player.is_spectator:
                num_spectators += 1
        if self.players.count() - num_spectators != self.num_players:
            raise ValidationError(
                f"Unable to start game, game requires {self.num_players} players, but {self.players.count()} have joined"
            )

        self.set_seats()
        self.next_dealer = self.set_plays_after()
        LOG.info(f"Starting game {self} with players {', '.join([str(p) for p in self.player_set.all()])}")

        self.start_new_hand_in_contestants_scores()
        self.set_state(Game.NEW_HAND, save=False)
        self.advance_game()

    def set_seats(self):
        
        # Assign players to their seats
        total_players = 0
        players_to_save = []
        for team_num, team in enumerate(self.teams.all()):
            for player_num, player in enumerate(team.members.all()):
                if player.is_spectator:
                    continue
                player.seat = team_num + (self.num_teams * player_num)
                LOG.info(f"Added {player.name} from game {self.name} and team {team.name} to seat {player.seat}")
                players_to_save.append(player)
                total_players += 1

        if not self.teams.exists():
            for player_num, player in enumerate(self.player_set.all()):
                if player.is_spectator:
                    continue
                player.seat = player_num
                LOG.info(f"Added {player.name} from game {self.name} to seat {player.seat}")
                players_to_save.append(player)
                total_players += 1
        
        if total_players != self.num_players:
            raise ValidationError(
                f"Unable to start game, only {total_players} were assigned to teams, but {self.num_players} are playing"
            )
        Player.objects.bulk_update(players_to_save, ["seat"])

    def set_plays_after(self):
        players_all = list(self.player_set.all().order_by("seat"))
        num_spectators = 0
        players = []
        for player in players_all:
            if player.is_spectator:
                print(f"{player} is a SPECTATOR")
                num_spectators += 1
            else:
                players.append(player)

        prev_player = players[-1]
        print(f"NUM SPECTATORS: {num_spectators}")
        print(f"PREV_PLAYER: {prev_player}")
        for player in players:
            if player.is_spectator:
                continue
            player.plays_after = prev_player
            prev_player = player
        Player.objects.bulk_update(players, ["plays_after"])
        return players[0]

    def advance_game(self):
        if self.state == Game.NEW_HAND:
            hand = Hand.objects.create(game=self, num=self.hands.count() + 1)
            hand.start_hand(dealer=self.next_dealer)
            self.next_dealer = self.next_player(self.next_dealer)
            self.set_state(Game.BIDDING, save=False)
            self.save()
            self.current_hand.advance_bidding()
        elif self.state == Game.BIDDING:
            self.current_hand.advance_bidding()

    def get_score_data(self):
        contestants_qs = self.teams.all() if self.num_teams else self.player_set.all()
        contestants_names = []
        contestants_data = {}
        min_score = 0
        max_score = 0
        for index, contestant in enumerate(contestants_qs):
            # Use team color or pick one
            color = getattr(contestant, "color", Team.COLORS[index])
            scores = self.scores_by_contestant.get(str(contestant.id), [0])
            contestants_names.append(contestant.name)
            contestants_data[contestant.name] = {"color": color, "scores": scores}
            # Check for new min/max
            min_score = min(min_score, *scores)
            max_score = max(max_score, *scores)

        return {
            "contestants": contestants_names,
            "contestantData": contestants_data,
            "maxScore": max_score,
            "minScore": min_score,
        }


class Team(models.Model):
    COLORS = ["blue", "orange", "plum", "sienna", "khaki", "linen", "cyan", "green"]
    game = models.ForeignKey(Game, related_name="teams", on_delete=models.CASCADE)
    name = models.CharField(max_length=1024)
    score = models.IntegerField(blank=True, default=0)
    winner = models.BooleanField(blank=True, default=False)
    color = models.CharField(max_length=1024, blank=True, null=True)

    def __str__(self):
        return f"{self.name} ({self.id})"


class Player(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    game = models.ForeignKey(Game, on_delete=models.CASCADE)
    user = models.ForeignKey("auth.User", on_delete=models.CASCADE)
    is_spectator = models.BooleanField(blank=True, default=False)
    spectate_only = models.BooleanField(blank=True, default=False)

    score = models.IntegerField(blank=True, default=0)
    winner = models.BooleanField(blank=True, default=False)

    is_computer = models.BooleanField(blank=True, default=False)
    name = models.CharField(max_length=1024)
    team = models.ForeignKey(Team, related_name="members", on_delete=models.CASCADE, null=True, blank=True)
    seat = models.IntegerField(blank=True, null=True)
    plays_after = models.OneToOneField(
        "smear.Player", related_name="plays_before", on_delete=models.SET_NULL, null=True, blank=True
    )

    cards_in_hand = ArrayField(models.CharField(max_length=2), default=list)

    AUTO_PILOT_DISABLED = 0
    AUTO_PILOT_UNTIL_NEW_HAND = 1
    AUTO_PILOT_FOREVER = 2
    auto_pilot_mode = models.IntegerField(blank=True, null=True)

    def __str__(self):
        return f"{self.name} ({self.id})"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.name:
            self.name = self._get_name_from_user(kwargs.get("user", None))

    @property
    def contestant_id(self):
        return str(self.team_id if self.team else self.id)

    def _get_name_from_user(self, user):
        if not user:
            return "Unknown"
        name = user.first_name + f"{' ' + user.last_name[:1] if user.last_name else ''}"
        if not name:
            name = user.username.split("@")[0]
        return name

    def reset_for_new_hand(self):
        self.cards_in_hand = []
        # Reset players who only enabled auto pilot until the end of the hand
        if self.auto_pilot_mode == self.AUTO_PILOT_UNTIL_NEW_HAND:
            self.auto_pilot_mode = self.AUTO_PILOT_DISABLED
            self.is_computer = False

    # def can_only_spectate(self):
    #     self.only_spectate = True
    #     self.spectator = True

    # def get_spectate_status(self):
    #     return self.spectator

    # def set_spectator(self, val):
    #     if (self.only_spectate):
    #         return
    #     self.spectator = val

    def accept_dealt_cards(self, cards):
        representations = [card.to_representation() for card in cards]
        self.cards_in_hand.extend(representations)

    def get_cards(self):
        return [Card(representation=rep) for rep in self.cards_in_hand]

    def get_trump(self, trump, smallest_to_largest=False):
        all_cards = [Card(representation=rep) for rep in self.cards_in_hand]
        trump_cards = [card for card in all_cards if card.is_trump(trump)]
        reverse = not smallest_to_largest
        ordered_cards = sorted(trump_cards, key=lambda c: c.trump_rank(trump), reverse=reverse)
        return ordered_cards

    def create_bid(self, hand):
        # avoid circular imports
        from apps.smear.computer_logic import computer_bid

        bid_value, trump_value = computer_bid(self, hand)

        LOG.info(f"{self} has {self.cards_in_hand}, bidding {bid_value}{' in ' + trump_value if bid_value else ''}")
        return Bid.create_bid_for_player(bid_value, trump_value, self, self.game.current_hand)

    def play_card(self, trick):
        # avoid circular imports
        from apps.smear.computer_logic import computer_play_card

        card = computer_play_card(self, trick)

        LOG.info(f"{self} has {self.cards_in_hand}, playing {card}")
        return card

    def card_played(self, card):
        self.cards_in_hand.remove(card.to_representation())
        self.save()

    def increment_score(self):
        if self.team:
            self.team.score = F("score") + 1
            self.team.save()
        else:
            self.score = F("score") + 1
            self.save()

    def decrement_score(self, amount):
        if self.team:
            self.team.score = F("score") - amount
            self.team.save()
        else:
            self.score = F("score") - amount
            self.save()


class Hand(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # num is the number hand in the game, starting at 1
    num = models.IntegerField()

    game = models.ForeignKey(Game, related_name="hands", on_delete=models.CASCADE, null=True)
    dealer = models.ForeignKey(Player, on_delete=models.SET_NULL, null=True, blank=True)
    bidder = models.ForeignKey(
        Player, related_name="hands_was_bidder", on_delete=models.SET_NULL, null=True, blank=True
    )
    high_bid = models.OneToOneField(
        "smear.Bid", related_name="hand_with_high_bid", on_delete=models.SET_NULL, null=True, blank=True
    )
    trump = models.CharField(max_length=16, blank=True, default="", choices=SUIT_CHOICES)

    # Used by card-counting logic. jicks are included in the trump suit
    # The values in the list are the string of the player.id
    # {
    #   "spades": ["123", "533", "1"],
    #   "clubs": ["123"],
    #   "diamonds": [],
    #   "hearts": ["32"],
    # }
    players_out_of_suits = models.JSONField(default=dict)

    # These values are updated as players win the cards, but game is
    # awarded at the end of the game
    winner_high = models.ForeignKey(
        Player, related_name="games_winner_high", on_delete=models.SET_NULL, null=True, blank=True
    )
    winner_low = models.ForeignKey(
        Player, related_name="games_winner_low", on_delete=models.SET_NULL, null=True, blank=True
    )
    winner_jack = models.ForeignKey(
        Player, related_name="games_winner_jack", on_delete=models.SET_NULL, null=True, blank=True
    )
    winner_jick = models.ForeignKey(
        Player, related_name="games_winner_jick", on_delete=models.SET_NULL, null=True, blank=True
    )
    winner_game = models.ForeignKey(
        Player, related_name="games_winner_game", on_delete=models.SET_NULL, null=True, blank=True
    )

    # Used to store game points by player
    # The keys are the string of the player.id
    # The values are an integer number of points the player has
    # {
    #   "123": 10,
    #   "456": 0,
    #   "789": 4,
    #   "555": 12,
    # }
    game_points_by_player = models.JSONField(default=dict)

    finished = models.BooleanField(blank=True, default=False)

    class Meta:
        ordering = ["num"]
        unique_together = (("game", "num"),)

    def __str__(self):
        return f"Hand {self.id} (dealer: {self.dealer}) (bidder: {self.bidder}) (high_bid: {self.high_bid}) (trump: {self.trump})"

    @property
    def current_trick(self):
        return self.tricks.last()

    def start_hand(self, dealer):
        LOG.info(f"Starting hand {self.num} with dealer: {dealer}")
        # Set the dealer
        self.dealer = dealer
        self.bidder = self.game.next_player(dealer)

        # Deal out six cards
        deck = Deck()
        players = self.game.player_set.all()

        for player in players:
            if player.is_spectator:
                player.accept_dealt_cards([Card(value="ace", suit="spades"), Card(value="ace", suit="spades"), Card(value="ace", suit="spades")])
                continue
            player.reset_for_new_hand()
            player.accept_dealt_cards(deck.deal(3))
        for player in players:
            if player.is_spectator:
                player.accept_dealt_cards([Card(value="ace", suit="spades"), Card(value="ace", suit="spades"), Card(value="ace", suit="spades")])
                continue
            player.accept_dealt_cards(deck.deal(3))
        for player in players:
            if player.is_spectator:
                continue
            LOG.info(f"{player} starts hand {self.num} with {player.cards_in_hand}")
        Player.objects.bulk_update(players, ["cards_in_hand", "is_computer", "auto_pilot_mode"])

        self.save()

    def add_bid_to_hand(self, new_bid):
        if self.high_bid and new_bid.bid <= self.high_bid.bid and new_bid.bid != 0:
            # User bid the same as the current bid, invalid
            raise ValueError(f"Unable to bid {new_bid.bid} when the current high bid is {self.high_bid.bid}")
        self.high_bid = self.high_bid if (self.high_bid and self.high_bid.bid >= new_bid.bid) else new_bid
        finished_bidding = self.bidder == self.dealer
        self.bidder = self.game.next_player(self.bidder)
        LOG.info(
            f"Submitted bid {new_bid}, high bid is now {self.high_bid}, bidder is now {self.bidder}, finished_bidding is {finished_bidding}"
        )
        self.save()
        return finished_bidding

    def submit_bid(self, new_bid):
        if new_bid.player.id != self.bidder.id:
            raise ValidationError(f"It is not {new_bid.player}'s turn to bid")
        finished_bidding = self.add_bid_to_hand(new_bid)
        self.advance_bidding(finished_bidding)

    def advance_bidding(self, finished_bidding_arg=False):
        finished_bidding = finished_bidding_arg
        while not finished_bidding:
            bid_filter = self.bidder.bids.filter(hand=self)
            if bid_filter.exists():
                # A human's bid exists, submit it
                finished_bidding = self.add_bid_to_hand(bid_filter[0])
            elif self.bidder.is_computer:
                # Generate computer bid and submit it
                bid = self.bidder.create_bid(self)
                finished_bidding = self.add_bid_to_hand(bid)
            else:
                # Waiting for a human to bid, just return
                return

        self._finalize_bidding()

    def _finalize_bidding(self):
        if not self.high_bid or self.high_bid.bid < 2:
            # No one bid, set the dealer
            self.bidder = self.dealer
            self._finalize_hand(no_bid=True)
            self.game.set_state(Game.NEW_HAND)
            self.save()
            self.game.advance_game()
            return

        self.bidder = self.high_bid.player
        self.save()
        self.game.set_state(Game.DECLARING_TRUMP)

        LOG.info(f"{self.bidder} has the high bid of {self.high_bid}")

        if self.high_bid.trump:
            self.finalize_trump_declaration(self.high_bid.trump)

    def award_low_trump(self):
        current_low = None
        current_low_winner = None
        for player in self.game.player_set.all():
            trump_cards = player.get_trump(self.trump)
            lowest_trump = min(trump_cards, key=lambda x: x.trump_rank(self.trump)) if trump_cards else None
            new_low = (
                current_low
                if (
                    lowest_trump is None
                    or (current_low and current_low.trump_rank(self.trump) < lowest_trump.trump_rank(self.trump))
                )
                else lowest_trump
            )
            if new_low != current_low and new_low is not None:
                current_low = new_low
                current_low_winner = player
        self.winner_low = current_low_winner
        LOG.info(f"Awarding low to {self.winner_low} - low is {current_low}")

    def award_high_trump(self):
        current_high = None
        current_high_winner = None
        for player in self.game.player_set.all():
            trump_cards = player.get_trump(self.trump)
            highest_trump = max(trump_cards, key=lambda x: x.trump_rank(self.trump)) if trump_cards else None
            new_high = (
                current_high
                if (
                    highest_trump is None
                    or (current_high and current_high.trump_rank(self.trump) > highest_trump.trump_rank(self.trump))
                )
                else highest_trump
            )
            if new_high != current_high and new_high is not None:
                current_high = new_high
                current_high_winner = player
        self.winner_high = current_high_winner
        LOG.info(f"Awarding high to {self.winner_high} - high is {current_high}")

    def finalize_trump_declaration(self, trump):
        """Now that we know trump, we will figure out what the high
        and low are and "award" them in advance
        """
        LOG.info(f"Trump is {trump}")
        self.trump = trump
        self.award_low_trump()
        self.award_high_trump()
        self.save()
        self.advance_hand()

    def advance_hand(self):
        if self.game.state == Game.BIDDING:
            self.advance_bidding()
        elif self.game.state == Game.DECLARING_TRUMP:
            trick = Trick.objects.create(hand=self, num=self.tricks.count() + 1)
            trick.start_trick(self.bidder)
            self.game.set_state(Game.PLAYING_TRICK)
            trick.advance_trick()
        elif self.game.state == Game.PLAYING_TRICK:
            # game.advance_hand() is only called when trick is finished
            # Check to see if hand is finished, otherwise start next trick
            if self.tricks.count() == 6:
                game_is_over = self._finalize_hand()
                new_state = Game.GAME_OVER if game_is_over else Game.NEW_HAND
                self.game.set_state(new_state)
                self.game.advance_game()
            else:
                last_taker = self.tricks.last().taker
                trick = Trick.objects.create(hand=self, num=self.tricks.count() + 1)
                trick.start_trick(last_taker)
                trick.advance_trick()

    def player_can_change_bid(self, player):
        next_bidder = self.bidder
        if player == next_bidder:
            return True
        while next_bidder != self.dealer:
            next_bidder = next_bidder.plays_before
            if player == next_bidder:
                return True
        return False

    def award_game(self):
        """Awards game

        When teams are playing, game points are summed for the whole team together
        However, self.winner_game must be a Player, so we just give it to the player
        on the team with the most points. The entire team gets the game point, though
        """
        teams = self.game.num_teams != 0
        high_game_score = 0
        high_game_player = []

        if teams:
            for team in self.game.teams.all():
                team_score = 0
                highest_member_score = 0
                high_member = None
                for member in team.members.all():
                    member_id = str(member.id)
                    member_score = self.game_points_by_player.get(member_id, 0)
                    team_score += member_score
                    if member_score > highest_member_score:
                        high_member = member
                        highest_member_score = member_score
                if team_score > high_game_score:
                    high_game_player = [high_member]
                    high_game_score = team_score
                elif team_score == high_game_score:
                    # It's a tie!
                    high_game_player.append(high_member)
        else:
            for player in self.game.player_set.all():
                player_id = str(player.id)
                player_score = self.game_points_by_player.get(player_id, 0)
                if player_score > high_game_score:
                    high_game_player = [player]
                    high_game_score = player_score
                elif player_score == high_game_score:
                    # It's a tie!
                    high_game_player.append(player)

        if len(high_game_player) > 1:
            LOG.info(f"Unable to award game, {high_game_player} all tied with {high_game_score} game points")
            self.winner_game = None
        else:
            self.winner_game = high_game_player[0]
        LOG.info(f"Awarding game to {self.winner_game} with {high_game_score} game points")

    def _check_for_must_bid_to_win(self, bid_won, bidding_contestant, contestants_over):
        # If we aren't playing with must_bid_to_win, this function always returns True
        if not self.game.must_bid_to_win:
            return True

        # If we are playing with must_bid_to_win, then only return True if the
        # bidder went out
        return bid_won and bidding_contestant in contestants_over

    def _declare_winner_if_game_is_over(self, bid_won):
        # This function deals with players or teams. We will use the generic
        # noun contestants to describe either
        teams = self.game.teams.exists()
        winners = None
        bidding_contestant = self.bidder.team if teams else self.bidder
        contestants = self.game.teams.all() if teams else self.game.player_set.all()
        contestants_at_or_over = list(contestants.filter(score__gte=self.game.score_to_play_to))
        bidder_went_out = self._check_for_must_bid_to_win(bid_won, bidding_contestant, contestants_at_or_over)
        game_is_over = bool(contestants_at_or_over) and bidder_went_out

        if game_is_over:
            if bidding_contestant in contestants_at_or_over:
                # Bidder always goes out
                bidding_contestant.refresh_from_db()
                high_score = bidding_contestant.score
                winners = [bidding_contestant]
            else:
                high_scorer = max(contestants_at_or_over, key=lambda c: c.score)
                high_scorer.refresh_from_db()
                high_score = high_scorer.score
                # Accounting for the unlikely scenario of a tie
                winners = [contestant for contestant in contestants_at_or_over if contestant.score == high_score]
                LOG.info(f"high_score: {high_score} c_a_o_o: {contestants_at_or_over} winners: {winners}")

            for winner in winners:
                winner.winner = True
            contestant_class = Team if teams else Player
            contestant_class.objects.bulk_update(winners, ["winner"])

            LOG.info(f"Game Over! Winners are {winners} with a score of {high_score}")

        return game_is_over

    def _calculate_if_bid_was_won(self):
        teammate_ids = (
            [self.bidder.id] if self.bidder.team is None else self.bidder.team.members.values_list("id", flat=True)
        )

        bidders_points = 0
        if self.winner_high and self.winner_high.id in teammate_ids:
            bidders_points += 1
        if self.winner_low and self.winner_low.id in teammate_ids:
            bidders_points += 1
        if self.winner_jick and self.winner_jick.id in teammate_ids:
            bidders_points += 1
        if self.winner_jack and self.winner_jack.id in teammate_ids:
            bidders_points += 1
        if self.winner_game and self.winner_game.id in teammate_ids:
            bidders_points += 1

        bid_won = bidders_points >= self.high_bid.bid
        LOG.info(
            f"{self.bidder} bid {self.high_bid.bid} and got {bidders_points}: {'was not' if bid_won else 'was'} set"
        )
        return bid_won, teammate_ids

    def _refresh_all_scores(self):
        contestants = self.game.teams.all() if self.game.teams.exists() else self.game.player_set.all()
        for contestant in contestants:
            contestant.refresh_from_db(fields=["score"])

    def _finalize_hand(self, no_bid=False):
        if no_bid:
            LOG.info("No bids, dealer is set 2")
            self.dealer.decrement_score(2)
            self.game.add_to_contestants_current_hand_score(self.bidder.contestant_id, -2)
            self.finished = True
            self._refresh_all_scores()
            return False

        self.award_game()
        self.finished = True
        self.save()
        LOG.info(
            f"Hand is finished. High: {self.winner_high} "
            f"Low: {self.winner_low} Jack: {self.winner_jack} "
            f"Jick: {self.winner_jick} Game: {self.winner_game}"
        )

        self.game.start_new_hand_in_contestants_scores()
        bid_won, teammate_ids = self._calculate_if_bid_was_won()
        if not bid_won:
            self.bidder.decrement_score(self.high_bid.bid)
            self.game.add_to_contestants_current_hand_score(self.bidder.contestant_id, -self.high_bid.bid)

        # Award the points, but not to the bidder if the bidder was set
        if self.winner_high and (bid_won or self.winner_high.id not in teammate_ids):
            self.winner_high.increment_score()
            self.game.add_to_contestants_current_hand_score(self.winner_high.contestant_id, 1)
        if self.winner_low and (bid_won or self.winner_low.id not in teammate_ids):
            self.winner_low.increment_score()
            self.game.add_to_contestants_current_hand_score(self.winner_low.contestant_id, 1)
        if self.winner_jick and (bid_won or self.winner_jick.id not in teammate_ids):
            self.winner_jick.increment_score()
            self.game.add_to_contestants_current_hand_score(self.winner_jick.contestant_id, 1)
        if self.winner_jack and (bid_won or self.winner_jack.id not in teammate_ids):
            self.winner_jack.increment_score()
            self.game.add_to_contestants_current_hand_score(self.winner_jack.contestant_id, 1)
        if self.winner_game and (bid_won or self.winner_game.id not in teammate_ids):
            self.winner_game.increment_score()
            self.game.add_to_contestants_current_hand_score(self.winner_game.contestant_id, 1)

        self.game.save()

        # Refresh the scores of all contestants to get the latest loaded from DB
        self._refresh_all_scores()

        return self._declare_winner_if_game_is_over(bid_won)

    def update_if_out_of_cards(self, player, card_played):
        all_plays = Play.objects.filter(trick__hand=self)
        all_cards_played = [Card(representation=play.card) for play in all_plays]

        suit_played = self.trump if card_played.is_trump(self.trump) else card_played.suit
        if card_played.is_trump(self.trump):
            if len([card for card in all_cards_played if card.is_trump(self.trump)]) == 14:
                # If all trump have been played, everyone is out
                self.players_out_of_suits[suit_played] = [str(p.id) for p in self.game.players.all()]
        else:
            # Only 12 cards exist in the jick suit (jick counts as trump)
            expected_cards = 12 if suit_played == Card.jick_suit(self.trump) else 13
            if (
                len([card for card in all_cards_played if not card.is_trump(self.trump) and card.suit == suit_played])
                == expected_cards
            ):
                # If all cards of this suit have been played, everyone is out
                self.players_out_of_suits[suit_played] = [str(p.id) for p in self.game.players.all()]

        # Update if the player is out of the suit
        lead_card = Card(representation=self.current_trick.get_lead_play().card)
        player_is_out = None
        if lead_card.is_trump(self.trump):
            if not card_played.is_trump(self.trump):
                player_is_out = self.trump
        else:
            if not card_played.is_trump(self.trump) and card_played.suit != lead_card.suit:
                # If player is trumping in, can't tell if he/she is out of lead_suit
                # So if it isn't trump, and isn't the lead_suit, must be out of lead_suit
                player_is_out = lead_card.suit
        existing_outs = self.players_out_of_suits.get(suit_played, [])
        new_outs = existing_outs if str(player.id) in existing_outs else [*existing_outs, str(player.id)]
        self.players_out_of_suits[player_is_out] = new_outs


class Bid(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    hand = models.ForeignKey(Hand, related_name="bids", on_delete=models.CASCADE, null=True)
    player = models.ForeignKey(Player, related_name="bids", on_delete=models.SET_NULL, null=True)
    bid = models.IntegerField()
    trump = models.CharField(max_length=16, blank=True, default="", choices=SUIT_CHOICES)

    def __str__(self):
        return f"{self.bid} (by {self.player})"

    @staticmethod
    def create_bid_for_player(bid, trump, player, hand):
        return Bid.objects.create(bid=bid, trump=trump, player=player, hand=hand)


class Play(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    trick = models.ForeignKey("Trick", related_name="plays", on_delete=models.CASCADE, null=True)
    player = models.ForeignKey(Player, related_name="plays", on_delete=models.SET_NULL, null=True)
    card = models.CharField(max_length=2)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.card} (by {self.player})"

    @cached_property
    def card_obj(self):
        return Card(representation=self.card)


class Trick(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # num is the number trick of the hand (e.g. 1, 2, 3, 4, 5, and then 6)
    num = models.IntegerField()

    hand = models.ForeignKey(Hand, related_name="tricks", on_delete=models.CASCADE, null=True)
    active_player = models.ForeignKey(Player, related_name="tricks_playing", on_delete=models.SET_NULL, null=True)
    taker = models.ForeignKey(Player, related_name="tricks_taken", on_delete=models.SET_NULL, null=True)

    class Meta:
        unique_together = (("hand", "num"),)
        ordering = ["num"]

    def __str__(self):
        return f"{', '.join(self.plays.all())} ({self.id})"

    def is_card_invalid_to_play(self, card, player):
        cards = player.get_cards()

        # First check to make sure the player didn't pull a card out of their sleave
        if card not in cards:
            return f"{card.pretty if card else 'None'} is not one of the player's cards"

        lead_card = self.get_lead_play().card_obj if self.get_lead_play() else None
        # If this is the first card, it's valid
        if lead_card is None:
            return

        # If trump was lead, did they follow suit if able?
        has_trump = any(c.is_trump(self.hand.trump) for c in cards)
        if lead_card.is_trump(self.hand.trump) and not card.is_trump(self.hand.trump) and has_trump:
            return "must follow suit"

        # For other lead suits, ensure either:
        # - card is following suit (if able, and ignoring jick suit)
        # - player is trumping
        has_lead_suit = any(c.same_suit(lead_card, self.hand.trump) for c in cards)
        if (lead_card.suit != card.suit) and has_lead_suit and not card.is_trump(self.hand.trump):
            return "must follow suit"

        return None

    def submit_card_to_play(self, card, player):
        """Handles validation of the card's legality

        Returns:
            trick_finished (bool): whether or not the trick is finished

        """
        if player != self.active_player:
            raise ValidationError(f"It is not {player}'s turn to play")

        error_msg = self.is_card_invalid_to_play(card, player)
        if error_msg:
            LOG.error(f"{player} tried to play {card}")
            raise ValidationError(
                f"Unable to play {card.pretty if card else 'None'} ({error_msg}), please choose another card"
            )

        LOG.info(f"{player} played {card}")
        self.active_player = self.hand.game.next_player(self.active_player)
        self.save()

        # Officially "play" the card, if the play hasn't already been created in the view
        play, created = Play.objects.get_or_create(
            card=card.to_representation(),
            player=player,
            trick=self,
        )

        # Let the player know to remove card from hand
        player.card_played(card)

        # Update card counting logic
        self.hand.update_if_out_of_cards(player, card)
        self.hand.save()

        return self.plays.count() == self.hand.game.num_players

    def submit_play(self, play):
        card = Card(representation=play.card)
        trick_finished = self.submit_card_to_play(card, play.player)
        self.advance_trick(trick_finished)

    def get_cards(self, as_rep=False):
        cards = [play.card for play in self.plays.all()]
        return [Card(representation=rep) for rep in cards] if not as_rep else cards

    def get_lead_play(self):
        return self.plays.first() if self.plays.exists() else None

    def start_trick(self, player_who_leads):
        LOG.info(f"Starting trick with {player_who_leads} leading")
        self.active_player = player_who_leads
        self.save()

    def advance_trick(self, trick_finished_arg=False):
        """Advances any computers playing"""
        trick_finished = trick_finished_arg
        while not trick_finished:
            if self.active_player.is_computer:
                # Have computer choose a card to play, then play it
                card_to_play = self.active_player.play_card(self)
                trick_finished = self.submit_card_to_play(card_to_play, self.active_player)
            else:
                # Waiting for a human to play, just return
                return

        self._finalize_trick()

    def find_winning_play(self):
        plays = list(self.plays.all())
        current_high = plays[0]
        for play in plays[1:]:
            if current_high.card_obj.is_less_than(play.card_obj, self.hand.trump):
                current_high = play
        return current_high

    def _award_cards_to_taker(self):
        winning_play = self.find_winning_play()
        LOG.info(f"Winning play was {winning_play}")
        self.taker = winning_play.player
        taker_id = str(self.taker.id)
        cards = self.get_cards()

        # Give games points to taker
        game_points = sum(card.game_points for card in cards)
        prev_points = self.hand.game_points_by_player.get(taker_id, 0)
        self.hand.game_points_by_player[taker_id] = prev_points + game_points

        # Award Jack or Jick, if taken
        jack = next((card for card in cards if card.is_jack(self.hand.trump)), None)
        jick = next((card for card in cards if card.is_jick(self.hand.trump)), None)
        if jack:
            self.hand.winner_jack = self.taker
            LOG.info(f"{self.taker} won Jack ({jack})")
        if jick:
            self.hand.winner_jick = self.taker
            LOG.info(f"{self.taker} won Jick ({jick})")

        # Save hand
        self.hand.save()

    def _finalize_trick(self):
        self.active_player = None
        self._award_cards_to_taker()
        LOG.info(f"Trick is finished. {self.taker} took the following cards: {self.get_cards()}")
        self.save()
        self.hand.advance_hand()

    def player_can_change_play(self, player):
        # TODO - do we want to allow async play submission?
        return False
