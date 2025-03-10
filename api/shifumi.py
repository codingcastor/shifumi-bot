import json
import logging
from http.server import BaseHTTPRequestHandler
import requests
from urllib.parse import parse_qs
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('shifumi.game')
from lib.database import (
    init_tables, create_game,
    get_pending_challenge, get_nickname
)
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

        # Parse the command text
        text_parts = slack_params['text'].split()
        logger.info(f"Game request from user {slack_params['user_id']}")

        user_nickname = get_nickname(slack_params['user_id']) or f'<@{slack_params['user_id']}>'
        logger.info(f"User nickname resolved to: {user_nickname}")

        # Check if it's a direct challenge
        if len(text_parts) == 2 and text_parts[0].startswith('<@'):
            target_user = text_parts[0][2:-1].split('|')[0]  # Remove <@ and >
            try:
                move = Gesture.from_input(text_parts[1].upper())
            except ValueError:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response = {
                    'response_type': 'ephemeral',
                    'text': f"Geste invalide ! Valeurs possibles : :rock:, :leaves:, :scissors: (ou PIERRE, FEUILLE, CISEAUX)"
                }
                self.wfile.write(json.dumps(response).encode('utf-8'))
                return

            # Prevent self-challenge
            if target_user == slack_params['user_id']:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response = {
                    'response_type': 'ephemeral',
                    'text': "Tu ne peux pas te défier toi-même !"
                }
                self.wfile.write(json.dumps(response).encode('utf-8'))
                return

            logger.info(f"Challenge request from {slack_params['user_id']} to {target_user}")
            # Check if there's already a challenge
            pending_challenge = get_pending_challenge(
                target_user,  # The challenger
                slack_params['user_id']  # The current player
            )
            logger.info(f"Pending challenge check result: {pending_challenge is not None}")

            if pending_challenge and pending_challenge[0] == target_user:
                # There's already a pending challenge from this user
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response = {
                    'response_type': 'ephemeral',
                    'text': f"Tu as déjà un défi en cours avec cette personne !"
                }
                self.wfile.write(json.dumps(response).encode('utf-8'))
                return
            else:
                # This is a new challenge
                logger.info(f"Creating new challenge game with move {move.value}")
                game_id = create_game(
                    slack_params['channel_id'],
                    slack_params['channel_name'],
                    slack_params['user_id'],
                    slack_params['user_name'],
                    move.value,
                    target_user,
                    None  # We don't have the opponent's name yet
                )
                delayed_response = {
                    'response_type': 'in_channel',
                    'text': f"{user_nickname} défie <@{target_user}> !",
                    'blocks': [
                        {
                            'type': 'section',
                            'text': {
                                'type': 'mrkdwn',
                                'text': f"{user_nickname} défie <@{target_user}> !"
                            }
                        },
                        {
                            'type': 'actions',
                            'elements': [
                                {
                                    'type': 'button',
                                    'text': {
                                        'type': 'plain_text',
                                        'text': '🪨 Pierre',
                                        'emoji': True
                                    },
                                    'value': f'{game_id}',
                                    'action_id': 'play_rock'
                                },
                                {
                                    'type': 'button',
                                    'text': {
                                        'type': 'plain_text',
                                        'text': '🍃 Feuille',
                                        'emoji': True
                                    },
                                    'value': f'{game_id}',
                                    'action_id': 'play_paper'
                                },
                                {
                                    'type': 'button',
                                    'text': {
                                        'type': 'plain_text',
                                        'text': '✂️ Ciseaux',
                                        'emoji': True
                                    },
                                    'value': f'{game_id}',
                                    'action_id': 'play_scissors'
                                }
                            ]
                        }
                    ]
                }

            requests.post(slack_params['response_url'], json=delayed_response)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'')
            return

        # Start new game
        try:
            move = Gesture.from_input(text_parts[0])
        except ValueError:
            response = {
                'response_type': 'ephemeral',
                'text': f"Geste invalide ! Valeurs possibles : :rock:, :leaves:, :scissors: (ou PIERRE, FEUILLE, CISEAUX)"
            }
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(bytes(str(response), 'utf-8'))
            return
            # Start new game
        game_id = create_game(
            slack_params['channel_id'],
            slack_params['channel_name'],
            slack_params['user_id'],
            slack_params['user_name'],
            move.value
        )
        delayed_response = {
            'response_type': 'in_channel',
            'text': f"{user_nickname} a joué. En attente d'un adversaire...",
            'blocks': [
                {
                    'type': 'section',
                    'text': {
                        'type': 'mrkdwn',
                        'text': f"{user_nickname} a joué. En attente d'un adversaire..."
                    }
                },
                {
                    'type': 'actions',
                    'elements': [
                        {
                            'type': 'button',
                            'text': {
                                'type': 'plain_text',
                                'text': '🪨 Pierre',
                                'emoji': True
                            },
                            'value': f'{game_id}',
                            'action_id': 'play_rock'
                        },
                        {
                            'type': 'button',
                            'text': {
                                'type': 'plain_text',
                                'text': '🍃 Feuille',
                                'emoji': True
                            },
                            'value': f'{game_id}',
                            'action_id': 'play_paper'
                        },
                        {
                            'type': 'button',
                            'text': {
                                'type': 'plain_text',
                                'text': '✂️ Ciseaux',
                                'emoji': True
                            },
                            'value': f'{game_id}',
                            'action_id': 'play_scissors'
                        }
                    ]
                }
            ]
        }
        requests.post(
            slack_params['response_url'],
            json=delayed_response
        )

        # Send immediate empty 200 response
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(b'')

        return