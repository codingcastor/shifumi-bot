import json
import logging
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs

import requests

from lib.database import init_tables, get_leaderboard, get_nickname, get_user_stats, get_unranked_players
from lib.slack import verify_slack_request

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('shifumi.leaderboard')


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
            'channel_id': params.get('channel_id', [''])[0],
        }

        logger.info(f"Received leaderboard request from user {slack_params['user_id']}")

        # Initialize tables if needed
        init_tables()

        # Check if a user was specified
        text = slack_params['text'].strip()
        blocks = None
        try:
            if text and text.startswith('<@'):
                # Extract user ID from mention
                target_user_id = text[2:-1].split('|')[0]
                # Get user stats
                stats = get_user_stats(target_user_id)

                if not stats or stats['total_games'] == 0:
                    text = f"<@{target_user_id}> n'a pas encore joué cette année ! 😢"
                else:
                    # Get user nickname or fallback to mention
                    user_name = get_nickname(target_user_id) or f"<@{target_user_id}>"

                    blocks = [
                        {
                            "type": "header",
                            "text": {
                                "type": "plain_text",
                                "text": f"📊 Statistiques de {user_name} 📊",
                                "emoji": True
                            }
                        },
                        {
                            "type": "section",
                            "fields": [
                                {
                                    "type": "mrkdwn",
                                    "text": "*Victoires* " + f"`{stats['wins']}`"
                                },
                                {
                                    "type": "mrkdwn",
                                    "text": "*Défaites* " + f"`{stats['losses']}`"
                                },
                                {
                                    "type": "mrkdwn",
                                    "text": "*Egalités* " + f"`{stats['draws']}`"
                                },
                                {
                                    "type": "mrkdwn",
                                    "text": "*Total parties* " + f"`{stats['total_games']}`"
                                },
                                {
                                    "type": "mrkdwn",
                                    "text": "*Taux de victoire* " + f"`{stats['win_rate']}%`"
                                }
                            ]
                        }
                    ]

                    # Add relationships section if any exist
                    relationships = []

                    if stats['nemesis']:
                        nemesis_name = get_nickname(stats['nemesis']['user_id']) or f"<@{stats['nemesis']['user_id']}>"
                        relationships.append(f"☠️ *Némésis*: {nemesis_name} ({stats['nemesis']['user_name']}) ({stats['nemesis']['wins']} victoires)")

                    if stats['best_against']:
                        best_against_name = get_nickname(
                            stats['best_against']['user_id']) or f"<@{stats['best_against']['user_id']}>"
                        relationships.append(
                            f"💪 *Meilleur contre*: {best_against_name} ({stats['best_against']['user_name']}) ({stats['best_against']['wins']} victoires)")

                    if stats['most_draws']:
                        most_draws_name = get_nickname(
                            stats['most_draws']['user_id']) or f"<@{stats['most_draws']['user_id']}>"
                        relationships.append(
                            f"🤝 *Égalités avec*: {most_draws_name} ({stats['most_draws']['user_name']}) ({stats['most_draws']['draws']} égalités)")

                    if relationships:
                        blocks.append({"type": "divider"})
                        blocks.append({
                            "type": "section",
                            "fields": [
                                {"type": "mrkdwn", "text": rel}
                                for rel in relationships
                            ]
                        })

                    text = None  # Fallback text not needed with blocks
            else:
                # Get leaderboard and unranked data
                leaderboard = get_leaderboard()
                unranked = get_unranked_players()

                lines = []

                # Format ranked players
                if leaderboard:
                    lines.append("🏆 *Classement de l'année* 🏆\n")

                    for i, player in enumerate(leaderboard, 1):
                        # Get player nickname and username
                        nickname = get_nickname(player['player_id'])
                        player_name = f"{nickname} (@{player['user_name']})" if nickname else f"<@{player['player_id']}>"

                        # Add medal for top 3
                        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, '')

                        lines.append(
                            f"{i}. {player_name} {medal} - "
                            f"{player['wins']}W/{player['draws']}D/{player['losses']}L "
                            f"({player['win_rate']}% sur {player['total_games']} parties)"
                        )

                # Format unranked players
                if unranked:
                    if lines:  # Add spacing if there were ranked players
                        lines.append("")
                    lines.append("👥 *Joueurs non classés* 👥")
                    for player in unranked:
                        nickname = get_nickname(player['player_id'])
                        player_name = f"{nickname} (@{player['player_name']})" if nickname else f"<@{player['player_id']}>"
                        lines.append(
                            f"• {player_name} - "
                            f"{player['games_played']}/5 parties jouées "
                            f"(encore {player['games_needed']} parties)"
                        )

                if not leaderboard and not unranked:
                    text = "Aucune partie jouée cette année ! 😢"
                    blocks = None
                else:
                    text = "\n".join(lines)
                    blocks = None

            response_message = {
                'response_type': 'in_channel',
                'blocks': blocks if not text else None,
                'text': text if text else None
            }

            # Send delayed response with leaderboard
            logger.info(f'Sending response to Slack: {json.dumps(response_message["blocks"])[:100]}...')
            logger.info(f'Message size : {len(json.dumps(response_message))}')
            requests.post(
                slack_params['response_url'],
                json=response_message,
            )

            # Send immediate empty response
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

