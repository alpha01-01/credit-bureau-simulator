from django.urls import path

from . import api

urlpatterns = [
    path("games/<int:game_id>/clock/", api.clock_state, name="clock-state"),
    path("games/<int:game_id>/clock/pause/", api.clock_pause, name="clock-pause"),
    path("games/<int:game_id>/clock/resume/", api.clock_resume, name="clock-resume"),
    path("games/<int:game_id>/clock/speed/", api.clock_speed, name="clock-speed"),
    path("games/<int:game_id>/clock/advance/", api.clock_advance, name="clock-advance"),
]
