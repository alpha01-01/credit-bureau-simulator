"""Games: one bureau organisation operating in one world (roadmap S3, extended in S4).

The simulation is the only layer that sees both sides: it delivers what the
world's providers send to the bureau, and remembers which world file became
which bureau file so decisions can later be scored against the truth.
"""

from __future__ import annotations

from django.db import models

from apps.bureau.submissions.models import Submission, SubmissionFile
from apps.org.models import Organization
from apps.world.models import ProviderFile, ProviderSubmission, World


class Game(models.Model):
    world = models.ForeignKey(World, on_delete=models.CASCADE, related_name="+")
    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Game {self.pk} ({self.organization})"


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
