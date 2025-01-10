import json
from http.server import BaseHTTPRequestHandler
import os
from lib.database import init_tables, get_pending_challenges, get_nickname
from lib.slack import verify_slack_request
from datetime import datetime


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

        # Initialize tables if needed
        init_tables()

        # Get pending challenges
        challenges = get_pending_challenges()
        
        if not challenges:
            text = "Aucun défi en attente ! 🎮"
        else:
            lines = ["🎯 *Défis en attente* 🎯\n"]
            
            for challenge in challenges:
                # Get nicknames or fallback to mentions
                challenger = get_nickname(challenge['challenger_id']) or f"<@{challenge['challenger_id']}>"
                opponent = get_nickname(challenge['opponent_id']) or f"<@{challenge['opponent_id']}>"
                
                # Format creation time
                created_at = challenge['created_at']
                time_str = created_at.strftime("%H:%M")
                
                lines.append(
                    f"• {challenger} → {opponent} "
                    f"(depuis {time_str})"
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
