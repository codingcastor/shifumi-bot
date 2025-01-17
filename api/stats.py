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

from lib.database import (
    init_tables, get_move_stats, get_nickname,
    get_player_stats, get_head_to_head_stats, get_move_stats_breakdown,
    get_head_to_head_stats_breakdown
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
            'user_id': params.get('user_id', [''])[0],
        }

        logger.info(f"Received stats request from user {slack_params['user_id']}")

        # Initialize tables if needed
        init_tables()

        try:
            # Check if users are specified
            text = slack_params.get('text', '').strip()
            logger.info(f"Command text received: '{text}'")
            
            # Check for breakdown flag
            show_breakdown = "--breakdown" in text
            if show_breakdown:
                text = text.replace("--breakdown", "").strip()
                logger.info("Breakdown flag detected")
            
            # Split text to check for multiple user mentions
            mentions = [part for part in text.split() if part.startswith('<@')]
            
            if len(mentions) == 2:
                # Head-to-head analysis
                player1_id = mentions[0][2:-1].split('|')[0]
                player2_id = mentions[1][2:-1].split('|')[0]
                logger.info(f"Computing head-to-head stats between {player1_id} and {player2_id}")
                
                player1_name = get_nickname(player1_id) or f"<@{player1_id}>"
                player2_name = get_nickname(player2_id) or f"<@{player2_id}>"
                logger.info(f"Players resolved to: {player1_name} vs {player2_name}")
                
                if show_breakdown:
                    stats = get_head_to_head_stats_breakdown(player1_id, player2_id)
                else:
                    stats = get_head_to_head_stats(player1_id, player2_id)
                
                if not stats:
                    text = f"Aucune partie jouée entre {player1_name} et {player2_name} cette année ! 😢"
                    logger.info(f"No head-to-head stats found")
                else:
                    logger.info(f"Found {stats['total_games']} games between players")
                    logger.info(f"Opponent's favorite move: {stats['opponent_favorite']}")
                    
                    # Create text output
                    lines = [
                        f"🤼 *Stats de {player1_name} contre {player2_name}* 🤼\n",
                        f"Total: `{stats['total_games']}` parties"
                    ]
                    
                    if show_breakdown:
                        # Add detailed breakdown stats for each move
                        for move_name in ['ROCK', 'PAPER', 'SCISSORS']:
                            move = Gesture(move_name)
                            move_stats = stats['moves'][move_name]
                            
                            lines.append(f"\n{move.emoji} *{move.value}*")
                            
                            if move_stats['first']:
                                first = move_stats['first']
                                lines.append(
                                    f"• En premier: "
                                    f"`{first['wins']}W/{first['losses']}L/{first['draws']}D` "
                                    f"(WR: {first['win_rate']}% sur {first['total_games']} parties)"
                                )
                            
                            if move_stats['second']:
                                second = move_stats['second']
                                lines.append(
                                    f"• En second: "
                                    f"`{second['wins']}W/{second['losses']}L/{second['draws']}D` "
                                    f"(WR: {second['win_rate']}% sur {second['total_games']} parties)"
                                )
                    else:
                        # Add regular stats for each move
                        for move_stat in stats['moves']:
                            move = Gesture(move_stat['move'])
                            logger.info(f"Processing stats for {move.value}: "
                                      f"W/L/D: {move_stat['wins']}/{move_stat['losses']}/{move_stat['draws']}")
                            
                            lines.append(
                                f"{move.emoji} *{move.value}* ({move_stat['play_rate']}%) - "
                                f"`{move_stat['wins']}W/{move_stat['losses']}L/{move_stat['draws']}D` "
                                f"(WR: {move_stat['win_rate']}%)"
                            )
                    
                    # Add opponent analysis with special case for Irene
                    if player2_id == "U05QD315XTP":  # Irene's user ID
                        lines.extend([
                            "",
                            "🤔 *Analyse de l'adversaire*",
                            "Irène est imprévisible, elle joue en 4D chess...",
                            "Même ChatGPT ne peut pas prédire ses coups !",
                            "Bonne chance ! 🎲"
                        ])
                    else:
                        # Add strategy analysis
                        lines.append("\n🎯 *Analyse stratégique*")
                        
                        if stats['opponent_favorite']:
                            opp_move = Gesture(stats['opponent_favorite'])
                            lines.append(f"• {player2_name} joue souvent {opp_move.emoji} *{opp_move.value}*")
                        
                        if stats['best_opener']:
                            opener = Gesture(stats['best_opener'])
                            lines.append(f"• Meilleur coup d'ouverture: {opener.emoji} *{opener.value}*")
                        
                        if stats['best_counter'] and stats['best_counter_against']:
                            counter = Gesture(stats['best_counter'])
                            against = Gesture(stats['best_counter_against'])
                            lines.append(f"• Meilleur contre: {counter.emoji} *{counter.value}* contre {against.emoji} *{against.value}*")
                    
                    text = "\n".join(lines)
            
            elif len(mentions) == 1:
                # Single player stats
                target_user_id = mentions[0][2:-1].split('|')[0]
                logger.info(f"Computing stats for specific user: {target_user_id}")
                user_name = get_nickname(target_user_id) or f"<@{target_user_id}>"
                logger.info(f"User nickname resolved to: {user_name}")
                
                if show_breakdown:
                    stats = get_move_stats_breakdown(target_user_id)
                else:
                    stats = get_player_stats(target_user_id)
            else:
                # Global stats
                logger.info("Computing global stats for all users")
                if show_breakdown:
                    stats = get_move_stats_breakdown()
                else:
                    stats = get_move_stats()
            
            if not stats and len(mentions) <= 1:
                text = f"{'Ce joueur' if mentions else 'Personne'} n'a pas encore joué cette année ! 😢"
                logger.info(f"No stats found: {text}")
            elif len(mentions) <= 1 and stats:
                if show_breakdown:
                    logger.info("Formatting breakdown stats")
                    lines = [f"📊 *Statistiques détaillées des coups{' de ' + user_name if len(mentions) == 1 else ''}* 📊\n"]
                    
                    for move_name in ['ROCK', 'PAPER', 'SCISSORS']:
                        move = Gesture(move_name)
                        move_stats = stats[move_name]
                        
                        lines.append(f"{move.emoji} *{move.value}*")
                        
                        if move_stats['first']:
                            first = move_stats['first']
                            lines.append(
                                f"• En premier: "
                                f"`{first['wins']}W/{first['losses']}L/{first['draws']}D` "
                                f"(WR: {first['win_rate']}% sur {first['total_games']} parties)"
                            )
                        
                        if move_stats['second']:
                            second = move_stats['second']
                            lines.append(
                                f"• En second: "
                                f"`{second['wins']}W/{second['losses']}L/{second['draws']}D` "
                                f"(WR: {second['win_rate']}% sur {second['total_games']} parties)"
                            )
                        
                        lines.append("")  # Add spacing between moves
                else:
                    logger.info("Formatting regular stats")
                    lines = [f"📊 *Statistiques des coups joués{' par ' + user_name if len(mentions) == 1 else ''}* 📊\n"]
                    
                    for move_stat in stats:
                        move = Gesture(move_stat['move'])
                        logger.info(f"Processing stats for {move.value}: "
                                  f"W/L/D: {move_stat['wins']}/{move_stat['losses']}/{move_stat['draws']} "
                                  f"(Win rate: {move_stat['win_rate']}%, Play rate: {move_stat['play_rate']}%)")
                        
                        lines.append(
                            f"{move.emoji} *{move.value}* ({move_stat['play_rate']}% des coups) - "
                            f"`{move_stat['wins']}W/{move_stat['losses']}L/{move_stat['draws']}D` "
                            f"(WR: {move_stat['win_rate']}%)"
                        )
                
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