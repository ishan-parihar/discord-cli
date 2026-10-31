"""discord-cli — Discord CLI for fetching chat history."""

try:
    from importlib.metadata import version

    __version__ = version("discord-lyr")
except Exception:
    __version__ = "0.0.0"
