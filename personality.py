# personality.py — F.R.I.D.A.Y. response templates (MCU-accurate)
import random
from datetime import datetime


def get_confirmation(action, entity=None):
    """Spoken echo confirming what Friday heard — brief and natural.
    Examples: 'Checking Bitcoin', 'Pulling up the weather', 'Searching for that'."""
    if entity:
        templates = [
            f"Got it — {action} {entity}.",
            f"{action.capitalize()} {entity}, boss.",
            f"Copy that. {action.capitalize()} {entity}.",
        ]
    else:
        templates = [
            f"{action.capitalize()}, boss.",
            f"Copy that. {action.capitalize()}.",
            f"Got it — {action}.",
        ]
    return random.choice(templates)


def get_greeting():
    """Startup greeting — simple, warm."""
    now = datetime.now()
    time_str = now.strftime("%I:%M %p").lstrip("0")
    return f"Greetings boss, it's {time_str}, what are you up to?"


def get_acknowledgment():
    """Quick natural acknowledgments."""
    return random.choice([
        "On it.",
        "Copy that.",
        "Got it, boss.",
        "One sec.",
        "Working on it.",
        "Yep.",
    ])


def get_error_response():
    """Composed error responses — calm, not dramatic."""
    return random.choice([
        "Hit a snag. Rerouting.",
        "That didn't go through. Want me to try something else?",
        "Something's off. Working around it.",
        "Ran into an issue, boss. Diagnosing.",
    ])


def get_browser_opening():
    """Said right before opening the browser — casual."""
    return random.choice([
        "Okay boss, just a second.",
        "On it boss, one sec.",
        "Okay boss, pulling that up.",
    ])


def get_data_ready():
    """Said when data is ready to present."""
    return random.choice([
        "According to the data.",
        "According to what I'm seeing.",
        "According to the latest info.",
    ])


def get_farewell():
    """Shutdown messages — brief, warm."""
    return random.choice([
        "Going offline, boss.",
        "Signing off. I'll be here.",
        "Shutting down. Night, boss.",
    ])


def get_unknown_command(text):
    """Unknown command responses — honest, not apologetic."""
    return random.choice([
        "Don't have a module for that one.",
        "That's not in my systems yet, boss.",
        "Nothing matches that. Want me to search for it?",
    ])


def get_summary_done():
    """Closing line after delivering a summary or data report — Iron Man / Friday style."""
    return random.choice([
        "That's all I've got.",
        "That's the rundown.",
        "That's everything on my end.",
        "That's the latest.",
        "You're all caught up.",
        "That's what I have for you.",
        "End of report.",
    ])


def get_thinking_pause():
    """Short hesitation filler before delivering data — makes Friday feel more alive."""
    return random.choice([
        "Hmm.",
        "Alright.",
        "Okay.",
        "Let me see.",
        "Right.",
    ])
