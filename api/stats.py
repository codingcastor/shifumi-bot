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

from lib.database import get_player_stats, init_tables, get_move_stats, get_nickname
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
            'text': params.get('text', [''])[0],
            'response_url': params.get('response_url', [''])[0],
            'user_id': params.get('user_id', [''])[0],
        }

        logger.info(f"Received stats request from user {slack_params['user_id']}")

        # Initialize tables if needed
        init_tables()

        try:
            # Check if a user was specified
            text = slack_params.get('text', '').strip()
            target_user_id = None
            user_name = None
            
            logger.info(f"Command text received: '{text}'")
            
            if text and text.startswith('<@'):
                # Extract user ID from mention
                target_user_id = text[2:-1].split('|')[0]
                logger.info(f"Computing stats for specific user: {target_user_id}")
                user_name = get_nickname(target_user_id) or f"<@{target_user_id}>"
                logger.info(f"User nickname resolved to: {user_name}")
            else:
                logger.info("Computing global stats for all users")
            
            # Get move statistics
            stats = get_player_stats(target_user_id) if target_user_id else get_move_stats()
            
            if not stats:
                text = f"{'Ce joueur' if target_user_id else 'Personne'} n'a pas encore joué cette année ! 😢"
                logger.info(f"No stats found: {text}")
            else:
                logger.info(f"Stats breakdown: {', '.join([f'{stat['move']}: {stat['total_games']} games' for stat in stats])}")
                
                # Create text output
                lines = [f"📊 *Statistiques des coups joués{' par ' + user_name if user_name else ''}* 📊\n"]
                
                # Add stats for each move
                for move_stat in stats:
                    move = Gesture(move_stat['move'])
                    logger.info(f"Processing stats for {move.value}: "
                              f"W/L/D: {move_stat['wins']}/{move_stat['losses']}/{move_stat['draws']} "
                              f"(Win rate: {move_stat['win_rate']}%, Play rate: {move_stat['play_rate']}%)")
                    
                    lines.extend([
                        f"{move.emoji} *{move.value}* ({move_stat['play_rate']}% des coups) - "
                        f"`{move_stat['wins']}W/{move_stat['losses']}L/{move_stat['draws']}D` "
                        f"(WR: {move_stat['win_rate']}%)"
                    ])
                
                text = "\n".join(lines)

            response_message = {
                'response_type': 'in_channel',
                'text': text
            }

            # Send response
            logger.info(f"Sending response to Slack")
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