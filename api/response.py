import json
import logging
from http.server import BaseHTTPRequestHandler
import os
from urllib.parse import parse_qs
import requests
from typing import Dict, Optional

# In-memory cache for nicknames
_nickname_cache: Dict[str, Optional[str]] = {}

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('shifumi.response')

from lib.database import (
    init_tables, get_pending_game, update_game,
    get_pending_challenge, get_nickname, get_game_by_id
)
from lib.slack import verify_slack_request
from lib.types import Gesture


def get_nickname_with_cache(user_id: str) -> Optional[str]:
    # Check cache first
    if user_id in _nickname_cache:
        return _nickname_cache[user_id]
    nickname = get_nickname(user_id)
    _nickname_cache[user_id] = nickname
    return nickname


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
        payload = json.loads(params.get('payload', ['{}'])[0])

        logger.info('Received interaction payload')

        # Extract action data
        action = payload.get('actions', [{}])[0]
        action_id = action.get('action_id', '')
        action_value = action.get('value', '')
        logger.info(f'Action received: {action_id} with value: {action_value}')

        # Extract user data
        user = payload.get('user', {})
        user_id = user.get('id')
        user_name = user.get('username')
        logger.info(f'User interaction from: {user_id} ({user_name})')

        # Extract other context
        channel = payload.get('channel', {})
        channel_id = channel.get('id')
        response_url = payload.get('response_url')
        logger.info(f'Channel context: {channel_id}')

        # Initialize tables if needed
        init_tables()

        user_nickname = get_nickname_with_cache(user_id) or f'<@{user_id}>'

        try:
            # Parse the move from action
            if action_id == 'play_rock':
                move = Gesture.ROCK
            elif action_id == 'play_paper':
                move = Gesture.PAPER
            elif action_id == 'play_scissors':
                move = Gesture.SCISSORS
            else:
                logger.error(f'Invalid action_id received: {action_id}')
                raise ValueError("Invalid action")

            logger.info(f'Player {user_id} chose move: {move.value}')

            # Handle challenge response
            game_id = int(action_value.split()[0])
            logger.info(f'Processing game response for game {game_id}')

            # Get game
            game = get_game_by_id(game_id)
            logger.info(f'Found game: {game is not None}')

            if not game:
                response_message = {
                    'response_type': 'ephemeral',
                    'text': "Partie non trouvée ou expirée.",
                    'replace_original': False
                }
            else:
                target_id = game[3]
                if target_id is not None:
                    game_id, challenger_id, challenger_move, target_id, _ = game
                    if challenger_id == user_id:
                        response_message = {
                            'response_type': 'ephemeral',
                            'text': "C'est toi qui a lancé le défi patate",
                            'replace_original': False
                        }
                    # For challenges (where target_id is set), verify the user is the target
                    if target_id != user_id:
                        response_message = {
                            'response_type': 'ephemeral',
                            'text': "Ce défi ne t'est pas destiné !",
                            'replace_original': False
                        }
                    else:
                        challenger_nickname = get_nickname_with_cache(challenger_id) or f'<@{challenger_id}>'

                        # Complete the game
                        update_game(game_id, user_id, user_name, move.value)
                        logger.info(f'Updated game {game_id} with move {move.value}')

                        # Determine winner
                        move1 = Gesture(challenger_move)
                        move2 = move
                        logger.info(f'Game {game_id}: {move1.value} vs {move2.value}')

                        if move1 == move2:
                            result = "Egalité !"
                        elif (
                                (move1 == Gesture.ROCK and move2 == Gesture.SCISSORS) or
                                (move1 == Gesture.PAPER and move2 == Gesture.ROCK) or
                                (move1 == Gesture.SCISSORS and move2 == Gesture.PAPER)
                        ):
                            result = f"{challenger_nickname} gagne !"
                        else:
                            result = f"{user_nickname} gagne !"

                        response_message = {
                            'response_type': 'in_channel',
                            'text': f"Résultat {'du défi' if target_id else ''}:\n{challenger_nickname} a joué {move1.emoji}\n{user_nickname} a joué {move2.emoji}\n{result}",
                            'replace_original': True
                        }

                # Handle regular game response
                else:
                    game_id, player1_id, player1_move, _, _ = game

                    if player1_id == user_id:
                        response_message = {
                            'response_type': 'ephemeral',
                            'text': "Tu ne peux pas jouer contre toi-même !",
                            'replace_original': False
                        }
                    else:
                        # Complete the game
                        update_game(game_id, user_id, user_name, move.value)

                        player1_nickname = get_nickname_with_cache(player1_id) or f'<@{player1_id}>'

                        # Determine winner
                        move1 = Gesture(player1_move)
                        move2 = move

                        if move1 == move2:
                            result = "Egalité !"
                        elif (
                                (move1 == Gesture.ROCK and move2 == Gesture.SCISSORS) or
                                (move1 == Gesture.PAPER and move2 == Gesture.ROCK) or
                                (move1 == Gesture.SCISSORS and move2 == Gesture.PAPER)
                        ):
                            result = f"{player1_nickname} gagne !"
                        else:
                            result = f"{user_nickname} gagne !"

                        response_message = {
                            'response_type': 'in_channel',
                            'text': f"Résultat:\n{player1_nickname} a joué {move1.emoji}\n{user_nickname} a joué {move2.emoji}\n{result}",
                            'replace_original': True
                        }

            # Send response
            logger.info(f'Sending response to Slack: {response_message["text"][:100]}...')
            requests.post(response_url, json=response_message)

            # Send immediate empty 200 response
            self.send_response(200)
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
