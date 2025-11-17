#!/usr/bin/env python3
"""
HTTP/WebSocket Bridge Server for iMessage Web Interface

This server exposes the existing iMessage functionality via HTTP/WebSocket
without modifying the existing server.py code.
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Set, Dict

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

# Add parent directory to path to import existing modules
# The iMessage backend code should be in the same directory structure
# We'll look for it in common locations
project_root = Path(__file__).parent.parent.parent
imessage_locations = [
    project_root / 'imessage-bridge',  # Current unified location
    project_root / 'imessage',  # Legacy location
    project_root.parent / 'imessage-bridge',
]

imessage_root_path = None
for path in imessage_locations:
    if path.exists() and (path / 'src').exists():
        imessage_root_path = path
        break

if imessage_root_path:
    imessage_src_path = imessage_root_path / 'src'
    # Change to imessage-bridge directory so imports work
    os.chdir(str(imessage_root_path))
    sys.path.insert(0, str(imessage_src_path))
    sys.path.insert(0, str(imessage_root_path))
    logger.info(f"Found iMessage backend at: {imessage_root_path}")
else:
    logger.error("Could not find iMessage backend code. Please ensure it's in one of the expected locations.")
    logger.error(f"Searched in: {[str(p) for p in imessage_locations]}")

from aiohttp import web, WSMsgType
from src.database import ConversationDatabase
from src.message_sender import MessageSender
from src.config import Config

class HTTPBridgeServer:
    def __init__(self):
        # Use absolute path to database - look in common locations
        project_root = Path(__file__).parent.parent.parent
        db_locations = [
            project_root / 'imessage-bridge' / 'conversation_state.db',  # Current unified location
            project_root / 'imessage' / 'conversation_state.db',  # Legacy location
            project_root / 'conversation_state.db',  # Fallback to root
        ]
        
        db_path = None
        for potential_path in db_locations:
            if potential_path.parent.exists():
                db_path = potential_path
                break
        
        if db_path is None:
            # Default location
            db_path = project_root / 'conversation_state.db'
        
        self.db = ConversationDatabase(db_path=str(db_path))
        self.message_sender = MessageSender()
        self.websocket_clients: Set[web.WebSocketResponse] = set()
        self.running = False
        self.last_message_id = 0  # Track last message ID for polling
    
    async def init(self):
        """Initialize database connection"""
        await self.db.init_db()
        logger.info("HTTP Bridge Server initialized")
    
    async def get_all_conversations(self, request):
        """GET /conversations - List all conversations"""
        try:
            # Get unique sender IDs with their last message info
            cursor = await self.db.db.execute('''
                SELECT 
                    sender_id,
                    MAX(timestamp) as last_timestamp,
                    (SELECT message_text FROM messages m2 
                     WHERE m2.sender_id = m1.sender_id 
                     ORDER BY m2.timestamp DESC LIMIT 1) as last_message
                FROM messages m1
                GROUP BY sender_id
                ORDER BY last_timestamp DESC
            ''')
            
            rows = await cursor.fetchall()
            conversations = []
            
            for row in rows:
                sender_id, last_timestamp, last_message = row
                conversations.append({
                    'sender_id': sender_id,
                    'last_message': last_message or '',
                    'last_timestamp': last_timestamp,
                    'unread_count': 0  # TODO: Implement unread tracking
                })
            
            return web.json_response(conversations)
        except Exception as e:
            logger.error(f"Error getting conversations: {e}", exc_info=True)
            return web.json_response({'error': str(e)}, status=500)
    
    async def get_messages(self, request):
        """GET /messages/<sender_id> - Get message history for a conversation"""
        try:
            sender_id = request.match_info.get('sender_id')
            if not sender_id:
                return web.json_response({'error': 'sender_id required'}, status=400)
            
            history = await self.db.get_conversation_history(sender_id, limit=100)
            
            # Format messages for frontend
            messages = []
            for msg in history:
                messages.append({
                    'text': msg['message'],
                    'is_from_user': msg['is_from_user'],
                    'timestamp': msg['timestamp'],
                    'date': datetime.fromtimestamp(msg['timestamp']).isoformat()
                })
            
            return web.json_response({
                'sender_id': sender_id,
                'messages': messages
            })
        except Exception as e:
            logger.error(f"Error getting messages: {e}", exc_info=True)
            return web.json_response({'error': str(e)}, status=500)
    
    async def send_message(self, request):
        """POST /send - Send a message"""
        try:
            data = await request.json()
            recipient = data.get('recipient')
            message_text = data.get('message')
            
            if not recipient or not message_text:
                return web.json_response(
                    {'error': 'recipient and message required'}, 
                    status=400
                )
            
            # Send message using existing MessageSender
            success = await self.message_sender.send_message(recipient, message_text)
            
            if success:
                # Save to database
                await self.db.save_message(recipient, message_text, is_from_user=False)
                
                # Broadcast to WebSocket clients
                await self.broadcast_message({
                    'type': 'message_sent',
                    'sender_id': recipient,
                    'message': message_text,
                    'timestamp': datetime.now().timestamp()
                })
                
                return web.json_response({'success': True})
            else:
                return web.json_response({'error': 'Failed to send message'}, status=500)
                
        except Exception as e:
            logger.error(f"Error sending message: {e}", exc_info=True)
            return web.json_response({'error': str(e)}, status=500)
    
    async def websocket_handler(self, request):
        """WebSocket /ws - Real-time message updates"""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        self.websocket_clients.add(ws)
        logger.info(f"WebSocket client connected. Total clients: {len(self.websocket_clients)}")
        
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    # Handle client messages if needed
                    logger.debug(f"Received WebSocket message: {data}")
                elif msg.type == WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {ws.exception()}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}", exc_info=True)
        finally:
            self.websocket_clients.discard(ws)
            logger.info(f"WebSocket client disconnected. Total clients: {len(self.websocket_clients)}")
        
        return ws
    
    async def broadcast_message(self, data: dict):
        """Broadcast message to all connected WebSocket clients"""
        if not self.websocket_clients:
            return
        
        message = json.dumps(data)
        disconnected = set()
        
        for ws in self.websocket_clients:
            try:
                await ws.send_str(message)
            except Exception as e:
                logger.error(f"Error sending to WebSocket client: {e}")
                disconnected.add(ws)
        
        # Remove disconnected clients
        self.websocket_clients -= disconnected
    
    async def health_check(self, request):
        """GET /health - Health check endpoint"""
        return web.json_response({'status': 'ok', 'clients': len(self.websocket_clients)})
    
    def setup_routes(self, app):
        """Setup HTTP routes"""
        app.router.add_get('/conversations', self.get_all_conversations)
        app.router.add_get('/messages/{sender_id}', self.get_messages)
        app.router.add_post('/send', self.send_message)
        app.router.add_get('/ws', self.websocket_handler)
        app.router.add_get('/health', self.health_check)
    
    async def poll_new_messages(self):
        """Poll database for new messages and broadcast via WebSocket"""
        while self.running:
            try:
                # Get messages newer than last_message_id
                cursor = await self.db.db.execute('''
                    SELECT id, sender_id, message_text, is_from_user, timestamp
                    FROM messages
                    WHERE id > ?
                    ORDER BY id ASC
                ''', (self.last_message_id,))
                
                rows = await cursor.fetchall()
                
                for row in rows:
                    msg_id, sender_id, message_text, is_from_user, timestamp = row
                    self.last_message_id = max(self.last_message_id, msg_id)
                    
                    # Broadcast to WebSocket clients
                    await self.broadcast_message({
                        'type': 'message_received' if is_from_user else 'message_sent',
                        'sender_id': sender_id,
                        'message': message_text,
                        'timestamp': timestamp
                    })
                
                await asyncio.sleep(1)  # Poll every second
            except Exception as e:
                logger.error(f"Error polling messages: {e}", exc_info=True)
                await asyncio.sleep(5)  # Wait longer on error
    
    async def run(self, host='0.0.0.0', port=8765):
        """Run the HTTP server"""
        await self.init()
        
        # Initialize last_message_id
        try:
            cursor = await self.db.db.execute('SELECT MAX(id) FROM messages')
            row = await cursor.fetchone()
            self.last_message_id = row[0] if row and row[0] else 0
        except Exception as e:
            logger.warning(f"Could not get last message ID: {e}")
            self.last_message_id = 0
        
        app = web.Application()
        
        # Enable CORS
        async def cors_middleware(app, handler):
            async def middleware_handler(request):
                if request.method == 'OPTIONS':
                    response = web.Response()
                else:
                    response = await handler(request)
                
                response.headers['Access-Control-Allow-Origin'] = '*'
                response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
                response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
                return response
            return middleware_handler
        
        app.middlewares.append(cors_middleware)
        
        self.setup_routes(app)
        
        logger.info(f"Starting HTTP Bridge Server on http://{host}:{port}")
        logger.info(f"Server accessible at: http://localhost:{port} (local) or http://<your-ip>:{port} (network)")
        logger.info("Endpoints:")
        logger.info("  GET  /conversations - List all conversations")
        logger.info("  GET  /messages/<sender_id> - Get message history")
        logger.info("  POST /send - Send a message")
        logger.info("  WS   /ws - WebSocket for real-time updates")
        logger.info("  GET  /health - Health check")
        
        self.running = True
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()
        
        # Start message polling task
        polling_task = asyncio.create_task(self.poll_new_messages())
        
        try:
            # Keep server running
            while self.running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down HTTP Bridge Server...")
        finally:
            self.running = False
            polling_task.cancel()
            try:
                await polling_task
            except asyncio.CancelledError:
                pass
            await runner.cleanup()
            await self.db.close()

async def main():
    server = HTTPBridgeServer()
    await server.run()

if __name__ == '__main__':
    asyncio.run(main())

