import json
from http.server import BaseHTTPRequestHandler
import os
from urllib.parse import parse_qs
from lib.database import init_tables
from lib.slack import verify_slack_request


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        # Get content length to read the body
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')

        # Verify request is from Slack only in production
        if os.getenv('VERCEL_ENV') == 'production':
            timestamp = self.headers.get('X-Slack-Request-Timestamp')
            signature = self.headers.get('X-Slack-Signature')

            if not timestamp or not signature or not verify_slack_request(timestamp, post_data, signature):
                self.send_response(401)
                self.end_headers()
                return

        # Parse form data
        params = parse_qs(post_data)
        # Extract Slack command parameters
        slack_params = {
            'command': params.get('command', [''])[0],
            'response_url': params.get('response_url', [''])[0],
            'user_id': params.get('user_id', [''])[0],
            'channel_id': params.get('channel_id', [''])[0],
        }

        # Initialize tables if needed
        init_tables()

        # Send temporary response
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        
        response = {
            'response_type': 'in_channel',
            'text': "🏆 Leaderboard coming soon! 🏆"
        }
        
        self.wfile.write(json.dumps(response).encode('utf-8'))
        return
