"""Self-hosted SMS gateway server.

Forwards messages to an Android phone running the capcom6
android-sms-gateway app in local-server mode, with rate limiting,
a SQLite-backed queue, logging, and basic-auth protected endpoints.
"""

__version__ = "1.0.0"
