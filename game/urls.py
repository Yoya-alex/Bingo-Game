from django.urls import path
from . import views

urlpatterns = [
    path('lobby/<int:telegram_id>/', views.game_lobby, name='game_lobby'),
    path('play/<int:telegram_id>/<int:game_id>/', views.game_play, name='game_play'),
    path('api/lobby-state/<int:telegram_id>/', views.lobby_state_api, name='lobby_state_api'),
    path('api/play-state/<int:telegram_id>/<int:game_id>/', views.play_state_api, name='play_state_api'),
    path('api/select-card/', views.select_card_api, name='select_card_api'),
    path('api/mark-number/', views.mark_number_api, name='mark_number_api'),
    path('api/game-status/<int:game_id>/', views.game_status_api, name='game_status_api'),
    path('api/claim-bingo/', views.claim_bingo_api, name='claim_bingo_api'),
]
