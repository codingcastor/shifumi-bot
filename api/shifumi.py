from http.server import BaseHTTPRequestHandler
import requests
from urllib.parse import parse_qs
import os
from lib.database import (
    init_game_table, get_pending_game, create_game, update_game
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

        # Initialize game table if needed
        init_game_table()

        # Parse the move
        try:
            move = Gesture(slack_params['text'].upper())
        except ValueError:
            delayed_response = {
                'response_type': 'ephemeral',
                'text': f"Geste invalide ! Valeurs possibles : {', '.join([g.value for g in Gesture])}"
            }
            requests.post(slack_params['response_url'], json=delayed_response)
            return

        # Check for pending game
        pending_game = get_pending_game(slack_params['channel_id'])

        if pending_game:
            game_id, player1_id, player1_move, _, _ = pending_game

            # Don't allow same player to play twice
            # if player1_id == slack_params['user_id']:
            #    delayed_response = {
            #        'response_type': 'ephemeral',
            #        'text': "You can't play against yourself! Wait for another player."
            #    }
            # else:
            # Complete the game
            update_game(game_id, slack_params['user_id'], move.value)

            # Determine winner
            move1 = Gesture(player1_move)
            move2 = move

            if move1 == move2:
                result = "Egalité !"
            elif (
                    (move1 == Gesture.PIERRE and move2 == Gesture.CISEAUX) or
                    (move1 == Gesture.FEUILLE and move2 == Gesture.PIERRE) or
                    (move1 == Gesture.CISEAUX and move2 == Gesture.FEUILLE)
            ):
                result = f"<@{player1_id}> gagne !"
            else:
                result = f"<@{slack_params['user_id']}> gagne !"

            delayed_response = {
                'response_type': 'in_channel',
                'text': f"Résultat:\n<@{player1_id}> a joué {move1.value}\n<@{slack_params['user_id']}> a joué {move2.value}\n{result}"
            }
        else:
            # Start new game
            create_game(slack_params['channel_id'], slack_params['user_id'], move.value)
            delayed_response = {
                'response_type': 'in_channel',
                'text': f"<@{slack_params['user_id']}> a joué {move.value}. En attente d'un adversaire !"
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
