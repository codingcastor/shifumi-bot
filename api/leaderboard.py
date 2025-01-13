import json
from http.server import BaseHTTPRequestHandler
import os
from urllib.parse import parse_qs
from lib.database import init_tables, get_leaderboard, get_nickname, get_user_stats
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
            'text': params.get('text', [''])[0],
            'response_url': params.get('response_url', [''])[0],
            'user_id': params.get('user_id', [''])[0],
            'channel_id': params.get('channel_id', [''])[0],
        }

        # Initialize tables if needed
        init_tables()

        # Check if a user was specified
        text = slack_params['text'].strip()
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

                lines = [f"📊 *Statistiques de {user_name}* 📊\n"]

                # Overall stats
                lines.append(
                    f"• Bilan: {stats['wins']}W/{stats['losses']}L "
                    f"({stats['win_rate']}% sur {stats['total_games']} parties)"
                )

                # Nemesis info
                if stats['nemesis']:
                    nemesis_name = get_nickname(stats['nemesis']['user_id']) or f"<@{stats['nemesis']['user_id']}>"
                    lines.append(
                        f"• Némésis: {nemesis_name} "
                        f"({stats['nemesis']['wins']} victoires)"
                    )

                # Best against info
                if stats['best_against']:
                    best_against_name = get_nickname(
                        stats['best_against']['user_id']) or f"<@{stats['best_against']['user_id']}>"
                    lines.append(
                        f"• Meilleur contre: {best_against_name} "
                        f"({stats['best_against']['wins']} victoires)"
                    )

                text = "\n".join(lines)
        else:
            # Get leaderboard data
            leaderboard = get_leaderboard()

            # Format leaderboard for display
            if not leaderboard:
                text = "Aucune partie jouée cette année ! 😢"
            else:
                lines = ["🏆 *Classement de l'année* 🏆\n"]

                for i, player in enumerate(leaderboard, 1):
                    # Get player nickname and username
                    nickname = get_nickname(player['player_id'])
                    player_name = f"{nickname} (@{player['user_name']})" if nickname else f"<@{player['player_id']}>"

                    # Add medal for top 3
                    medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")

                    lines.append(
                        f"{medal} {player_name} - "
                        f"{player['wins']}W/{player['losses']}L "
                        f"({player['win_rate']}% sur {player['total_games']} parties)"
                    )

                text = "\n".join(lines)

        # Send response
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()

        response = {
            'response_type': 'in_channel',
            'text': text
        }

        self.wfile.write(json.dumps(response).encode('utf-8'))
        return
