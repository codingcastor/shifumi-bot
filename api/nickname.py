import json
import logging
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs

from lib.database import (
    init_tables, set_nickname
)
from lib.slack import verify_slack_request

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('shifumi.nickname')


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
            'text': params.get('text', [''])[0],
            'response_url': params.get('response_url', [''])[0],
            'trigger_id': params.get('trigger_id', [''])[0],
            'user_id': params.get('user_id', [''])[0],
            'user_name': params.get('user_name', [''])[0],
            'team_id': params.get('team_id', [''])[0],
            'enterprise_id': params.get('enterprise_id', [''])[0],
            'channel_id': params.get('channel_id', [''])[0],
            'channel_name': params.get('channel_name', [''])[0],
            'api_app_id': params.get('api_app_id', [''])[0]
        }

        # Initialize tables if needed
        init_tables()

        # Handle nickname command
        nickname = slack_params['text']
        logger.info(f"Nickname request from user {slack_params['user_id']}")
        
        if not nickname:
            logger.warning(f"Empty nickname provided by user {slack_params['user_id']}")
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {
                'response_type': 'ephemeral',
                'text': "Tu dois spécifier un pseudo. Utilisation: /shifumi-pseudo <ton-pseudo>"
            }
            self.wfile.write(json.dumps(response).encode('utf-8'))
            return
        else:
            logger.info(f"Setting nickname '{nickname}' for user {slack_params['user_id']}")
            set_nickname(slack_params['user_id'], nickname, slack_params['user_name'])
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {
                'response_type': 'ephemeral',
                'text': f"Ton pseudo est maintenant: {nickname}"
            }
            self.wfile.write(json.dumps(response).encode('utf-8'))
            return
