"""Games: one bureau organisation operating in one world (roadmap S3, extended in S4).

The simulation is the only layer that sees both sides: it delivers what the
world's providers send to the bureau, and remembers which world file became
which bureau file so decisions can later be scored against the truth.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.bureau.submissions.models import Submission, SubmissionFile
from apps.org.models import Organization
from apps.world.models import ProviderFile, ProviderSubmission, World


class GameStatus(models.TextChoices):
    PAUSED = "PAUSED", "Paused"
    RUNNING = "RUNNING", "Running"


SPEEDS = (1, 2, 4, 8)


class Game(models.Model):
    """A bureau playing in a world, and its clock (Document 07, Section 5).

    Time advances in ticks of 15 working minutes. Tick 1 is 08:00-08:15 on the
    first working day of ``clock_start``'s month; nights, weekends and public
    holidays have no ticks. ``current_tick`` is the last tick completed.
    """

    world = models.ForeignKey(World, on_delete=models.CASCADE, related_name="+")
    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name="+")
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="games",
    )
    clock_start = models.DateField(help_text="First calendar day of play")
    current_tick = models.BigIntegerField(default=0)
    status = models.CharField(max_length=10, choices=GameStatus.choices, default=GameStatus.PAUSED)
    speed = models.PositiveSmallIntegerField(default=1, help_text="1x, 2x, 4x or 8x")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Game {self.pk} ({self.organization})"


class TickLog(models.Model):
    """One row per completed tick: what makes ticks idempotent."""

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="ticks")
    tick = models.BigIntegerField()
    sim_time = models.DateTimeField(help_text="Start of the tick, game time")
    events_processed = models.IntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["game", "tick"], name="tick_unique")]

    def __str__(self) -> str:
        return f"{self.game_id}:{self.tick}"


class EventType(models.TextChoices):
    PROVIDER_FILES_ARRIVE = "PROVIDER_FILES_ARRIVE", "Provider files arrive"
    WORLD_ADVANCED = "WORLD_ADVANCED", "The world lived through another month"
    CREDIT_APPLICATION = "CREDIT_APPLICATION", "A borrower applies to a lender"


class EventStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    DONE = "DONE", "Done"


class ScheduledEvent(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=40, choices=EventType.choices)
    due_tick = models.BigIntegerField()
    sequence = models.IntegerField(help_text="Order among events due in the same tick")
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=10, choices=EventStatus.choices, default=EventStatus.PENDING
    )
    processed_tick = models.BigIntegerField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["game", "status", "due_tick"])]

    def __str__(self) -> str:
        return f"{self.event_type} @ {self.due_tick}"


class PlayerAction(models.Model):
    """The action log: replaying it on the same world reproduces the game."""

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="actions")
    sequence = models.IntegerField()
    tick = models.BigIntegerField(help_text="Clock position when the action was taken")
    action_type = models.CharField(max_length=40)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["game", "sequence"], name="action_unique_sequence")
        ]

    def __str__(self) -> str:
        return f"{self.game_id}#{self.sequence} {self.action_type}"


class Delivery(models.Model):
    """A world provider file handed to the bureau."""

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="deliveries")
    world_submission = models.ForeignKey(
        ProviderSubmission, on_delete=models.CASCADE, related_name="+"
    )
    world_file = models.ForeignKey(ProviderFile, on_delete=models.CASCADE, related_name="+")
    bureau_submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="+")
    bureau_file = models.OneToOneField(SubmissionFile, on_delete=models.CASCADE, related_name="+")
    delivered_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["game", "world_file"], name="delivery_unique_file")
        ]

    def __str__(self) -> str:
        return f"{self.world_file_id} -> {self.bureau_file_id}"


class SubscriberView(models.Model):
    """How a subscriber (a world lender) currently values the bureau. Hidden from the bureau."""

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="subscriber_views")
    subscriber_code = models.CharField(max_length=30)
    perceived_value = models.FloatField(default=0.6)
    opportunities = models.IntegerField(default=0, help_text="Applications seen")
    enquiries = models.IntegerField(default=0)
    hits = models.IntegerField(default=0)
    wrong_person = models.IntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["game", "subscriber_code"], name="view_unique_subscriber"
            )
        ]

    def __str__(self) -> str:
        return f"{self.subscriber_code}: {self.perceived_value:.2f}"


class EnquiryJudgement(models.Model):
    """What an enquiry was really worth, judged against the world (S6 measurement)."""

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="enquiry_judgements")
    enquiry = models.OneToOneField(
        "bureau_core.Enquiry", on_delete=models.CASCADE, related_name="+"
    )
    application = models.ForeignKey(
        "world.LoanApplication", on_delete=models.CASCADE, related_name="+"
    )
    should_hit = models.BooleanField(help_text="The applicant has credit with a reporting provider")
    hit = models.BooleanField()
    correct_person = models.BooleanField(null=True, blank=True)
    outcome = models.CharField(max_length=20)

    def __str__(self) -> str:
        return f"{self.enquiry_id}: {self.outcome}"
