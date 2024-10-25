import logging

from django.db import transaction
from django.db.models import prefetch_related_objects
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from unique_names_generator import get_random_name
from unique_names_generator.data import ADJECTIVES, ANIMALS, COLORS

from apps.smear.models import Bid, Game, Hand, Play, Player, Team, Trick
from apps.smear.pagination import SmearPagination
from apps.smear.permissions import (
    IsBidOwnerPermission,
    IsGameOwnerPermission,
    IsPlayerInGame,
    IsPlayerOnTeam,
    IsPlayOwnerPermission,
)
from apps.smear.serializers import (
    BidSerializer,
    GameDetailSerializer,
    GameJoinSerializer,
    GameSerializer,
    PlayerIDSerializer,
    PlayerSummarySerializer,
    PlaySerializer,
    StatusBiddingSerializer,
    StatusPlayingTrickSerializer,
    StatusStartingSerializer,
    TeamSerializer,
    TeamSummarySerializer,
)

LOG = logging.getLogger(__name__)


class GameViewSet(viewsets.ModelViewSet):
    filter_backends = (
        filters.SearchFilter,
        DjangoFilterBackend,
    )
    pagination_class = SmearPagination
    search_fields = ("name",)
    filterset_fields = ("owner", "passcode_required", "single_player", "players")

    def get_serializer_class(self):
        if self.action == "retrieve":
            return GameDetailSerializer
        else:
            return GameSerializer

    def get_permissions(self):
        if self.action in ["create", "list", "retrieve"]:
            self.permission_classes = [IsAuthenticated]
        elif self.action in ["update", "partial_update", "destroy"]:
            self.permission_classes = [IsGameOwnerPermission]

        return super().get_permissions()

    def get_queryset(self):
        base_queryset = (
            Game.objects.filter(single_player=False).exclude(players=self.request.user)
            if self.request.query_params.get("public", "false") == "true"
            else Game.objects.all()
        )

        return base_queryset.order_by("-id").prefetch_related("players", "teams", "hands__tricks__plays")

    @transaction.atomic
    def perform_create(self, serializer):
        passcode = serializer.validated_data.get("passcode", None)
        instance = serializer.save(owner=self.request.user, passcode_required=bool(passcode))
        instance.name = get_random_name(combo=[ADJECTIVES, COLORS, ANIMALS])
        Player.objects.create(game=instance, user=self.request.user, is_computer=False)
        LOG.info(f"Created game {instance} and added {self.request.user} as player and creator")

        instance.create_initial_teams()

        if instance.single_player:
            num_computers = instance.num_players - instance.player_set.count()
            instance.add_computer_players(num_computers)

        if instance.single_player and instance.num_teams == 0:
            # Start single player games without teams immediately
            instance.start_game()
        else:
            instance.state = Game.STARTING
            instance.save()

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated],
    )
    def join(self, request, pk=None):
        game = self.get_object()
        serializer = GameJoinSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        if game.player_set.count() >= game.num_players:
            raise ValidationError(f"Unable to join game, already contains {game.num_players} players")
        if game.passcode_required and game.passcode != serializer.data.get("passcode", None):
            raise ValidationError("Unable to join game, passcode is required and was incorrect")

        Player.objects.create(game=game, user=self.request.user)
        LOG.info(f"Added {self.request.user} to game {game}")
        return Response({"status": "success"})

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated],
    )
    def spectate(self, request, pk=None):
        game = self.get_object()
        serializer = GameJoinSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        if game.passcode_required and game.passcode != serializer.data.get("passcode", None):
            raise ValidationError("Unable to spectate game, passcode is required and was incorrect")

        # TODO Don't add player to game, need something new for spectator
        # Player.objects.create(game=game, user=self.request.user)
        LOG.info(f"Added {self.request.user} as spectator to game {game}")
        return Response({"status": "success"})

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsGameOwnerPermission],
    )
    def start(self, request, pk=None):
        game = self.get_object()
        game.start_game()
        LOG.info(f"Started game {game}")
        return Response({"status": "success"})

    @action(
        detail=True,
        methods=["post", "delete"],
        permission_classes=[IsGameOwnerPermission],
    )
    def player(self, request, pk=None):
        game = self.get_object()
        if request.method == "POST":
            computer_player = game.add_computer_player()
            LOG.info(f"Added computer {computer_player} to game {game}")
            return Response(PlayerSummarySerializer(computer_player).data)
        else:
            serializer = PlayerIDSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            player_id = serializer.validated_data["id"]
            try:
                player = Player.objects.get(id=player_id)
            except Player.DoesNotExist:
                LOG.info(f"Player with ID {player_id} did not exist")
                pass
            else:
                player.delete()
                LOG.info(f"Removed {player} from game {pk}")
            return Response(
                {
                    "status": "success",
                }
            )

    @action(
        detail=True,
        methods=["get"],
        permission_classes=[IsPlayerInGame],
    )
    def status(self, request, pk=None):
        game = self.get_object()
        status_serializer = {
            Game.STARTING: StatusStartingSerializer,
            Game.BIDDING: StatusBiddingSerializer,
            Game.DECLARING_TRUMP: StatusBiddingSerializer,
            Game.PLAYING_TRICK: StatusPlayingTrickSerializer,
            Game.GAME_OVER: GameDetailSerializer,
        }.get(game.state, None)
        if not status_serializer:
            raise APIException(f"Unable to find status of game {game}, state ({game.state}) is not supported")

        context = {
            **self.get_serializer_context(),
            "trick_num": request.query_params.get("trick_num"),
            "hand_num": request.query_params.get("hand_num"),
        }

        if context.get("trick_num"):
            # Not the best way to do this...
            status_serializer = StatusPlayingTrickSerializer

        serializer = status_serializer(game, context=context)

        return Response(serializer.data)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsPlayerInGame],
    )
    def auto_pilot(self, request, pk=None):
        game = self.get_object()
        player = Player.objects.get(game=game, user=self.request.user)
        # Default to forever
        auto_pilot_mode = Player.AUTO_PILOT_FOREVER
        if request.query_params.get("until_new_hand", "false").lower() == "true":
            auto_pilot_mode = Player.AUTO_PILOT_UNTIL_NEW_HAND

        LOG.info(
            f"Setting player {player} to auto-pilot " "disabled"
            if player.is_computer
            else "enabled" " with mode " "UNTIL_NEW_HAND"
            if auto_pilot_mode == Player.AUTO_PILOT_UNTIL_NEW_HAND
            else "FOREVER"
        )
        player.is_computer = not player.is_computer
        player.auto_pilot_mode = auto_pilot_mode
        player.save()
        return Response({"status": "success"})

    @action(
        detail=True,
        methods=["get"],
        permission_classes=[IsPlayerInGame],
    )
    def scores(self, request, pk=None):
        game = self.get_object()
        score_data = game.get_score_data()
        return Response(score_data)


class TeamViewSet(viewsets.ModelViewSet):
    filter_backends = (
        filters.SearchFilter,
        DjangoFilterBackend,
    )
    pagination_class = SmearPagination
    serializer_class = TeamSummarySerializer

    def get_permissions(self):
        if self.action in ["create", "destroy", "update"]:
            self.permission_classes = [IsGameOwnerPermission]
        elif self.action in ["partial_update"]:
            self.permission_classes = [IsPlayerOnTeam]
        elif self.action in ["list", "retrieve"]:
            self.permission_classes = [IsPlayerInGame]

        return super().get_permissions()

    def get_queryset(self):
        game_id = self.kwargs.get("game_id")
        return Team.objects.filter(game_id=game_id).select_related("game").order_by("-id")

    @action(
        detail=True,
        methods=["post", "delete"],
        permission_classes=[IsGameOwnerPermission],
    )
    def member(self, request, pk=None, game_id=None):
        team = self.get_object()
        serializer = PlayerIDSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        player_id = serializer.validated_data["id"]
        player = get_object_or_404(Player, pk=player_id)

        adding = request.method == "POST"

        player.team = team if adding else None
        player.save()
        LOG.info(f"{'Added' if adding else 'Removed'} player {player} {'to' if adding else 'from'} team {team}")

        return Response(TeamSerializer(team).data)

    @action(
        detail=False,
        methods=["post", "delete"],
        permission_classes=[IsGameOwnerPermission],
    )
    def all(self, request, game_id=None):
        game = get_object_or_404(Game, pk=game_id)
        prefetch_related_objects([game], "players", "teams")

        if request.method == "POST":
            LOG.info(f"Autofilling teams for game {game}")
            game.autofill_teams()

        elif request.method == "DELETE":
            LOG.info(f"Resetting teams for game {game}")
            game.reset_teams()

        game.save()

        return Response(GameSerializer(game).data)


class BidViewSet(viewsets.ModelViewSet):
    filter_backends = (
        filters.SearchFilter,
        DjangoFilterBackend,
    )
    pagination_class = SmearPagination
    serializer_class = BidSerializer

    def get_permissions(self):
        if self.action in ["create", "list", "retrieve"]:
            self.permission_classes = [IsPlayerInGame]
        if self.action in ["update", "partial_update"]:
            self.permission_classes = [IsBidOwnerPermission]

        return super().get_permissions()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        player = Player.objects.get(game=self.kwargs["game_id"], user=self.request.user)
        hand = Hand.objects.get(pk=self.kwargs["hand_id"])
        context["extra_kwargs"] = {
            "hand": hand,
            "player": player,
        }
        return context

    def get_queryset(self):
        game_id = self.kwargs.get("game_id")
        hand_id = self.kwargs.get("hand_id")
        qs = Bid.objects.filter(hand__game_id=game_id, hand_id=hand_id).order_by("-id")
        return qs.select_related("player").prefetch_related("hand__game__players")

    @transaction.atomic
    def perform_create(self, serializer):
        bid = serializer.save(**serializer.context["extra_kwargs"])
        bid.hand.submit_bid(bid)
        return bid

    def perform_update(self, serializer):
        hand = serializer.context["extra_kwargs"].get("hand")
        player = serializer.context["extra_kwargs"].get("player")

        if hand.game.state == Game.BIDDING:
            if not hand.player_can_change_bid(player):
                raise ValidationError("No longer able to change bid")
        elif hand.game.state == Game.DECLARING_TRUMP:
            if player != hand.high_bid.player:
                raise ValidationError("Not able to change bid after bidder is chosen")
            bid = serializer.validated_data.get("bid", None)
            if bid and bid != self.get_object().bid:
                raise ValidationError("Changing the bid is not allowed while declaring trump")
        else:
            raise ValidationError("No longer able to change bid")

        bid = serializer.save(**serializer.context["extra_kwargs"])

        if hand.game.state == Game.DECLARING_TRUMP and bid.trump:
            hand.finalize_trump_declaration(bid.trump)


class PlayViewSet(viewsets.ModelViewSet):
    filter_backends = (
        filters.SearchFilter,
        DjangoFilterBackend,
    )
    pagination_class = SmearPagination
    serializer_class = PlaySerializer

    def get_permissions(self):
        if self.action in ["create", "list", "retrieve"]:
            self.permission_classes = [IsPlayerInGame]
        if self.action in ["update", "partial_update"]:
            self.permission_classes = [IsPlayOwnerPermission]

        return super().get_permissions()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        player = Player.objects.get(game=self.kwargs["game_id"], user=self.request.user)
        trick = Trick.objects.get(pk=self.kwargs["trick_id"])
        context["extra_kwargs"] = {
            "player": player,
            "trick": trick,
        }
        return context

    def get_queryset(self):
        trick_id = self.kwargs.get("trick_id")
        qs = Play.objects.filter(trick_id=trick_id).order_by("-id")
        return qs.select_related("player", "trick__hand__game", "trick__active_player").prefetch_related("trick__plays")

    @transaction.atomic
    def perform_create(self, serializer):
        play = serializer.save(**serializer.context["extra_kwargs"])
        trick = serializer.context["extra_kwargs"].get("trick")
        trick.submit_play(play)
        return play

    def perform_update(self, serializer):
        trick = serializer.context["extra_kwargs"].get("trick")
        player = serializer.context["extra_kwargs"].get("player")

        if not trick.player_can_change_play(player):
            raise ValidationError("No longer able to change card to play")

        play = serializer.save(**serializer.context["extra_kwargs"])
        return play
