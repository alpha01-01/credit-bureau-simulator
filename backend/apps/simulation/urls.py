from django.urls import path

from . import api, ui_api

urlpatterns = [
    path("worlds/", ui_api.worlds, name="worlds"),
    path("games/", ui_api.games, name="games"),
    path("games/<int:game_id>/", ui_api.game_detail, name="game"),
    path("games/<int:game_id>/dashboard/", ui_api.dashboard, name="dashboard"),
    path("games/<int:game_id>/briefing/", ui_api.briefing, name="briefing"),
    path("games/<int:game_id>/submissions/", ui_api.submissions, name="submissions"),
    path(
        "games/<int:game_id>/submissions/<str:reference>/",
        ui_api.submission_detail,
        name="submission",
    ),
    path("games/<int:game_id>/customers/", ui_api.customers, name="customers"),
    path("games/<int:game_id>/customers/<str:reference>/", ui_api.customer_detail, name="customer"),
    path("games/<int:game_id>/ledger/", ui_api.ledger, name="ledger"),
    path("games/<int:game_id>/invoices/", ui_api.invoices, name="invoices"),
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
    path("games/<int:game_id>/enquiries/", api.enquiries, name="enquiries"),
    path("games/<int:game_id>/finance/", api.finance, name="finance"),
    path(
        "games/<int:game_id>/enquiries/<str:reference>/", api.enquiry_report, name="enquiry-report"
    ),
]
