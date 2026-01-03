from aiogram import Router

router = Router()

# Import handlers to register them with the router
# Order matters: more specific handlers must be imported before catch-all handlers
from src.handlers import admin  # noqa: E402, F401
from src.handlers import broadcast  # noqa: E402, F401
from src.handlers import history  # noqa: E402, F401
from src.handlers import visualization  # noqa: E402, F401
from src.handlers import registration  # noqa: E402, F401 - must be last (has catch-all)

# Re-export public symbols for backwards compatibility
from src.handlers.helpers import (  # noqa: E402
    admin_check,
    format_broadcast_progress,
    format_failure_reasons,
    generate_event_csv,
    get_event_message,
    get_event_stats,
    get_or_create_user,
    is_valid_event_code,
    send_broadcast_messages,
    suggest_event_code,
)
from src.handlers.states import (  # noqa: E402
    BroadcastStates,
    EndBroadcastStates,
    HistoryBroadcastStates,
    NewEventStates,
    RegistrationStates,
)

__all__ = [
    "router",
    # States
    "NewEventStates",
    "BroadcastStates",
    "RegistrationStates",
    "HistoryBroadcastStates",
    "EndBroadcastStates",
    # Helpers
    "is_valid_event_code",
    "suggest_event_code",
    "get_or_create_user",
    "get_event_message",
    "generate_event_csv",
    "send_broadcast_messages",
    "format_failure_reasons",
    "format_broadcast_progress",
    "get_event_stats",
    "admin_check",
]
