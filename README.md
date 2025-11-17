# iMessage Bridge Server

HTTP/WebSocket bridge server that connects your macOS Messages app to a web interface.

## Features

- Send iMessages via HTTP API
- Receive real-time message updates via WebSocket
- Store conversation history in SQLite database
- Expose iMessage functionality over the network

## Requirements

- macOS (for iMessage integration)
- Python 3.9+
- ngrok (for remote access)

## Quick Start

1. **Install dependencies:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Start the server:**
   ```bash
   ./start_server.sh
   ```

3. **Expose via ngrok (in another terminal):**
   ```bash
   ngrok http 8765
   ```

## Configuration

The server binds to `0.0.0.0:8765` by default, making it accessible on your local network.

For remote access, use ngrok or similar tunneling service.

## API Endpoints

- `GET /health` - Health check
- `GET /conversations` - List all conversations
- `GET /messages/<sender_id>` - Get message history
- `POST /send` - Send a message
- `WS /ws` - WebSocket for real-time updates

## Environment Variables

Create a `.env` file (optional):

```env
GEMINI_API_KEY=your_key_here
POLL_INTERVAL=0.5
MESSAGE_HISTORY_LIMIT=20
```

## License

MIT

