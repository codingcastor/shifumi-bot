import json
import logging
from http.server import BaseHTTPRequestHandler
import os
from urllib.parse import parse_qs
import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('shifumi.stats')

from lib.database import init_tables, get_move_stats
from lib.slack import verify_slack_request
from lib.types import Gesture


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
        }

        logger.info(f"Received stats request from user {slack_params['user_id']}")

        # Initialize tables if needed
        init_tables()

        try:
            # Get move statistics
            stats = get_move_stats()
            
            if not stats:
                text = "Aucune partie jouée cette année ! 😢"
                blocks = None
            else:
                # Create blocks for better formatting
                blocks = [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": "📊 Statistiques des coups joués 📊",
                            "emoji": True
                        }
                    }
                ]
                
                # Add stats for each move
                for move_stat in stats:
                    move = Gesture(move_stat['move'])
                    blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"*{move.emoji} {move.value} ({move_stat['play_rate']}%)*\n"
                                f"• Victoires: `{move_stat['wins']}` ({move_stat['win_rate']}%)\n"
                                f"• Défaites: `{move_stat['losses']}`\n"
                                f"• Egalités: `{move_stat['draws']}`\n"
                                f"• Total: `{move_stat['total_games']}` parties"
                            )
                        }
                    })
                
                text = None  # Fallback text not needed with blocks

            response_message = {
                'response_type': 'in_channel',
                'blocks': blocks if not text else None,
                'text': text if text else None
            }

            # Send response
            logger.info(f'Sending response to Slack')
            requests.post(slack_params['response_url'], json=response_message)

            # Send immediate empty 200 response
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'')
            logger.info('Request completed successfully')

        except Exception as e:
            logger.error(f'Error processing request: {str(e)}', exc_info=True)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            error_response = {
                'response_type': 'ephemeral',
                'text': f"Une erreur s'est produite: {str(e)}"
            }
            self.wfile.write(json.dumps(error_response).encode('utf-8'))

        return 