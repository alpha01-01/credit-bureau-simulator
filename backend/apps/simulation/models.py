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


class Severity(models.TextChoices):
    INFO = "INFO", "Information"
    WARNING = "WARNING", "Warning"
    CRITICAL = "CRITICAL", "Critical"


def default_pause_severities() -> list[str]:
    return [Severity.CRITICAL.value]


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
    setup_status = models.CharField(
        max_length=10, default="READY", help_text="PREPARING while history is pre-loaded"
    )
    setup_message = models.CharField(max_length=200, blank=True)
    # Auto-pause rules (Document 07, Section 5.2), set by the player.
    pause_severities = models.JSONField(
        default=default_pause_severities, help_text="Notice severities that pause the clock"
    )
    pause_on_deadlines = models.BooleanField(
        default=True, help_text="Pause when work is due today and no one has taken it"
    )
    last_step_at = models.DateTimeField(
        null=True, blank=True, help_text="Wall-clock time of the last real-time tick"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Game {self.pk} ({self.organization})"


class HistoryTemplate(models.Model):
    """A world's established bureau, built once and copied into each new game (P2.1).

    Pre-loading history is deterministic: the same world and number of months
    always give the same bureau. So it is built once, in a hidden game with no
    owner, and every new game with that history gets a copy (``copy_bureau``),
    in seconds instead of minutes. ``code_version`` names the code that built
    it; a template built by other code is rebuilt rather than copied.
    """

    world = models.ForeignKey(World, on_delete=models.CASCADE, related_name="+")
    months = models.PositiveSmallIntegerField()
    game = models.OneToOneField(Game, on_delete=models.CASCADE, related_name="+")
    code_version = models.CharField(max_length=60)
    build_seconds = models.FloatField(default=0)
    built_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["world", "months"], name="history_template_unique")
        ]

    def __str__(self) -> str:
        return f"World {self.world_id}, {self.months} months"


class Notice(models.Model):
    """One entry in the game's event feed: what just happened (P2.2).

    Notices are written by the simulation while ticks run, so a replay writes
    the same ones. ``paused`` marks a notice that stopped the clock under the
    player's auto-pause rules.
    """

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="notices")
    tick = models.BigIntegerField()
    sim_time = models.DateTimeField(help_text="Game time")
    kind = models.CharField(max_length=40)
    severity = models.CharField(max_length=10, choices=Severity.choices)
    title = models.CharField(max_length=200)
    detail = models.CharField(max_length=500, blank=True)
    drill = models.JSONField(default=dict, help_text="Where the Why? link leads")
    is_deadline = models.BooleanField(default=False)
    paused = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=["game", "tick"])]

    def __str__(self) -> str:
        return f"{self.game_id}@{self.tick} {self.severity} {self.title}"


class Consequence(models.Model):
    """One link in a consequence chain (P2.3; Document 07, Section 8.5).

    A report delivered to a subscriber held another person's accounts (a false
    merge) or missed some of the applicant's own (a false split). ``cause`` says
    how the wrong link was made: a reviewer's decision (``work_item``) or the
    automatic matching rules. The debrief replays these for the player.
    """

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="consequences")
    tick = models.BigIntegerField()
    sim_time = models.DateTimeField()
    effect = models.CharField(max_length=30, help_text="MIXED_REPORT or INCOMPLETE_REPORT")
    enquiry = models.ForeignKey("bureau_core.Enquiry", on_delete=models.CASCADE, related_name="+")
    subscriber_code = models.CharField(max_length=30)
    accounts = models.IntegerField(help_text="Accounts shown wrongly, or missing")
    cause = models.CharField(max_length=20, help_text="DECISION or AUTOMATIC")
    work_item = models.ForeignKey(
        "workitems.WorkItem", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    provider = models.CharField(max_length=30, help_text="Institution code of the wrong link")
    provider_customer = models.CharField(max_length=50, help_text="Its customer number")
    detail = models.CharField(max_length=300)

    class Meta:
        indexes = [models.Index(fields=["game", "tick"])]

    def __str__(self) -> str:
        return f"{self.game_id}@{self.tick} {self.effect} <- {self.cause}"


class DataQualityReview(models.Model):
    """The monthly Data Quality Review: the hidden truth, revealed (P2.3; Section 11.2).

    Built at the end of each month and kept as it was then. ``figures`` holds the
    numbers; ``refs`` the natural keys of the records behind each figure, for the
    drill-down (natural keys, so a review survives copying a game).
    """

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="reviews")
    period = models.DateField(help_text="Last day of the month reviewed")
    tick = models.BigIntegerField()
    figures = models.JSONField(default=dict)
    refs = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["game", "period"], name="review_unique_period")
        ]

    def __str__(self) -> str:
        return f"{self.game_id} review {self.period:%Y-%m}"


class CheckpointKind(models.TextChoices):
    MONTH_END = "MONTH_END", "Month-end"
    ON_DEMAND = "ON_DEMAND", "On demand"


class Checkpoint(models.Model):
    """A named point in a game, with a summary of the bureau's state there (P2.1).

    Document 07, Section 12.3: taken at each month-end and on demand. The game is
    deterministic, so the checkpoint does not store the state itself: replaying the
    first ``action_count`` actions on a fresh game up to ``tick`` reproduces it, and
    ``summary`` (row counts and money totals, cheap to take) shows that it did. For
    testing and bug reports, not player-facing time travel.
    """

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="checkpoints")
    tick = models.BigIntegerField(help_text="The last tick completed")
    sim_time = models.DateTimeField(help_text="End of that tick, game time")
    kind = models.CharField(max_length=10, choices=CheckpointKind.choices)
    label = models.CharField(max_length=100, blank=True)
    action_count = models.IntegerField(help_text="Actions in the log when it was taken")
    code_version = models.CharField(max_length=60)
    summary = models.JSONField(default=dict)
    digest = models.CharField(max_length=64, help_text="SHA-256 of the summary")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["game", "tick"])]

    def __str__(self) -> str:
        return f"{self.game_id}@{self.tick} {self.kind} {self.label}".rstrip()


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
    SUBSCRIBER_PAYMENT = "SUBSCRIBER_PAYMENT", "A subscriber pays an invoice"
    PAYROLL_TAX_REMITTANCE = "PAYROLL_TAX_REMITTANCE", "PAYE and SSNIT are paid over"
    VAT_RETURN = "VAT_RETURN", "VAT and levies are paid to the GRA"


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
    at_risk = models.BooleanField(
        default=False, help_text="Has complained and is reconsidering; cleared when it recovers"
    )

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
