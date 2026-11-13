from django.urls import path

from . import api

urlpatterns = [
    path("games/<int:game_id>/clock/", api.clock_state, name="clock-state"),
    path("games/<int:game_id>/clock/pause/", api.clock_pause, name="clock-pause"),
    path("games/<int:game_id>/clock/resume/", api.clock_resume, name="clock-resume"),
    path("games/<int:game_id>/clock/speed/", api.clock_speed, name="clock-speed"),
    path("games/<int:game_id>/clock/advance/", api.clock_advance, name="clock-advance"),
    path("games/<int:game_id>/work-items/", api.work_items, name="work-items"),
    path("games/<int:game_id>/work-items/<int:number>/", api.work_item, name="work-item"),
    path(
        "games/<int:game_id>/work-items/<int:number>/resolve/",
        api.resolve_work_item,
        name="work-item-resolve",
    ),
    path("games/<int:game_id>/employees/", api.employees, name="employees"),
]
