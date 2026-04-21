# commands.py — Compatibility shim (handlers split into handlers/ package)
"""Re-exports process_command and all handlers for backward compatibility.
The actual implementations live in:
  - router.py — command routing and intent classification
  - handlers/web_handlers.py — browser, search, knowledge
  - handlers/finance_handlers.py — stocks, crypto
  - handlers/news_handlers.py — news
  - handlers/system_handlers.py — volume, screenshot, time, timer, system info, apps
  - handlers/weather_handlers.py — weather
  - handlers/world_handlers.py — world monitor
"""

# Main entry point
from router import process_command  # noqa: F401

# Re-export all handlers for any direct imports
from handlers.web_handlers import (  # noqa: F401
    handle_open, handle_search, handle_browser_action, handle_knowledge,
)
from handlers.finance_handlers import (  # noqa: F401
    handle_stock, handle_crypto,
)
from handlers.news_handlers import handle_news  # noqa: F401
from handlers.system_handlers import (  # noqa: F401
    handle_volume, handle_screenshot, handle_time,
    handle_timer, handle_system_info, handle_app_launch,
)
from handlers.weather_handlers import handle_weather  # noqa: F401
from handlers.world_handlers import handle_world_monitor  # noqa: F401
