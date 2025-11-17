import aiosqlite
import logging
import os
from pathlib import Path
from typing import List, Dict, Optional
from src.config import Config

logger = logging.getLogger(__name__)

class MessagesReader:
    """Read messages from macOS Messages database"""
    
    def __init__(self, chat_db_path: str = None):
        self.chat_db_path = chat_db_path or Config.CHAT_DB_PATH
        self.db = None
    
    async def connect(self):
        """Connect to macOS Messages database"""
        if not os.path.exists(self.chat_db_path):
            logger.warning(f"Messages database not found at {self.chat_db_path}")
            return False
        
        try:
            # Open read-only connection
            self.db = await aiosqlite.connect(f"file:{self.chat_db_path}?mode=ro", uri=True)
            logger.info(f"Connected to Messages database at {self.chat_db_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Messages database: {e}")
            return False
    
    async def get_all_conversations(self) -> List[Dict]:
        """Get all conversations from Messages database"""
        if not self.db:
            if not await self.connect():
                return []
        
        try:
            # Query to get unique phone numbers/contacts with their last message
            cursor = await self.db.execute('''
                SELECT 
                    handle.id as sender_id,
                    MAX(message.date/1000000000 + 978307200) as last_timestamp,
                    (SELECT text FROM message 
                     WHERE message.handle_id = handle.id 
                     ORDER BY message.date DESC LIMIT 1) as last_message
                FROM handle
                INNER JOIN message ON message.handle_id = handle.id
                WHERE handle.service = 'iMessage'
                GROUP BY handle.id
                ORDER BY last_timestamp DESC
            ''')
            
            rows = await cursor.fetchall()
            conversations = []
            
            for row in rows:
                sender_id, last_timestamp, last_message = row
                # Format phone number if it's a phone number
                if sender_id and sender_id.startswith('+'):
                    conversations.append({
                        'sender_id': sender_id,
                        'last_message': last_message or '',
                        'last_timestamp': last_timestamp or 0,
                        'unread_count': 0
                    })
            
            logger.info(f"Found {len(conversations)} conversations in Messages database")
            return conversations
        except Exception as e:
            logger.error(f"Error reading conversations from Messages database: {e}", exc_info=True)
            return []
    
    async def get_messages_for_contact(self, sender_id: str, limit: int = 100) -> List[Dict]:
        """Get messages for a specific contact"""
        if not self.db:
            if not await self.connect():
                return []
        
        try:
            cursor = await self.db.execute('''
                SELECT 
                    message.text,
                    message.is_from_me,
                    message.date/1000000000 + 978307200 as timestamp
                FROM message
                INNER JOIN handle ON message.handle_id = handle.id
                WHERE handle.id = ? AND handle.service = 'iMessage'
                ORDER BY message.date ASC
                LIMIT ?
            ''', (sender_id, limit))
            
            rows = await cursor.fetchall()
            messages = []
            
            for row in rows:
                text, is_from_me, timestamp = row
                messages.append({
                    'message': text or '',
                    'is_from_user': bool(is_from_me),
                    'timestamp': timestamp
                })
            
            return messages
        except Exception as e:
            logger.error(f"Error reading messages for {sender_id}: {e}", exc_info=True)
            return []
    
    async def close(self):
        """Close database connection"""
        if self.db:
            await self.db.close()
            logger.info("Messages database connection closed")

