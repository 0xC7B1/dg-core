"""Game bounded context — game lifecycle, player management, flags."""

from app.domain.game.service import (
    create_game,
    end_game,
    get_flags,
    get_game,
    get_game_players,
    join_game,
    set_flag,
    start_game,
    switch_character,
    update_player_role,
)

__all__ = [
    "create_game",
    "end_game",
    "get_flags",
    "get_game",
    "get_game_players",
    "join_game",
    "set_flag",
    "start_game",
    "switch_character",
    "update_player_role",
]
