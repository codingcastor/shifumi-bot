import json
from http.server import BaseHTTPRequestHandler
import os
from urllib.parse import parse_qs
import requests

from lib.database import (
    init_tables, get_pending_game, update_game,
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
        payload = json.loads(params.get('payload', ['{}'])[0])
        
        # Extract action data
        action = payload.get('actions', [{}])[0]
        action_id = action.get('action_id', '')
        action_value = action.get('value', '')
        
        # Extract user data
        user = payload.get('user', {})
        user_id = user.get('id')
        user_name = user.get('username')
        
        # Extract other context
        channel = payload.get('channel', {})
        channel_id = channel.get('id')
        response_url = payload.get('response_url')

        # Initialize tables if needed
        init_tables()

        user_nickname = get_nickname(user_id) or f'<@{user_id}>'

        try:
            # Parse the move from action
            if action_id == 'play_rock':
                move = Gesture.ROCK
            elif action_id == 'play_paper':
                move = Gesture.PAPER
            elif action_id == 'play_scissors':
                move = Gesture.SCISSORS
            else:
                raise ValueError("Invalid action")

            # Handle challenge response
            if ' ' in action_value:  # Format: "userid MOVE"
                challenger_id = action_value.split()[0]
                # Get pending challenge
                pending_challenge = get_pending_challenge(challenger_id, user_id)
                
                if pending_challenge:
                    game_id, challenger_id, challenger_move = pending_challenge
                    challenger_nickname = get_nickname(challenger_id) or f'<@{challenger_id}>'
                    
                    # Complete the challenge
                    update_game(game_id, user_id, user_name, move.value)
                    
                    # Determine winner
                    move1 = Gesture(challenger_move)
                    move2 = move
                    
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
                        'text': f"Résultat du défi:\n{challenger_nickname} a joué {move1.emoji}\n{user_nickname} a joué {move2.emoji}\n{result}",
                        'replace_original': True
                    }
                else:
                    response_message = {
                        'response_type': 'ephemeral',
                        'text': "Défi non trouvé ou expiré.",
                        'replace_original': False
                    }
            
            # Handle regular game response
            else:
                pending_game = get_pending_game(channel_id)
                
                if pending_game:
                    game_id, player1_id, player1_move, _, _ = pending_game
                    
                    if player1_id == user_id:
                        response_message = {
                            'response_type': 'ephemeral',
                            'text': "Tu ne peux pas jouer contre toi-même !",
                            'replace_original': False
                        }
                    else:
                        # Complete the game
                        update_game(game_id, user_id, user_name, move.value)
                        
                        player1_nickname = get_nickname(player1_id) or f'<@{player1_id}>'
                        
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
                else:
                    response_message = {
                        'response_type': 'in_channel',
                        'text': "Partie non trouvée ou expirée.",
                        'replace_original': True
                    }

            # Send response
            requests.post(response_url, json=response_message)
            
            # Send immediate empty 200 response
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'')
            
        except Exception as e:
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            error_response = {
                'response_type': 'ephemeral',
                'text': f"Une erreur s'est produite: {str(e)}"
            }
            self.wfile.write(json.dumps(error_response).encode('utf-8'))

        return
