"""
iMessage Bridge Server

An HTTP/WebSocket bridge server that connects macOS Messages app to web interfaces.
"""

__version__ = "1.0.0"

from src.config import Config
from src.database import ConversationDatabase
from src.message_sender import MessageSender

__all__ = [
    'Config',
    'ConversationDatabase',
    'MessageSender',
]

