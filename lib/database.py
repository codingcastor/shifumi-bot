import os
import psycopg2
from datetime import datetime
from lib.types import Gesture


def get_db_connection():
    """Get a PostgreSQL database connection"""
    return psycopg2.connect(os.getenv('DATABASE_URL'))


def init_tables():
    """Create the games and nicknames tables if they don't exist"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS nicknames (
            user_id TEXT PRIMARY KEY,
            nickname TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS games (
            id SERIAL PRIMARY KEY,
            channel_id TEXT NOT NULL,
            channel_name TEXT NOT NULL,
            player1_id TEXT NOT NULL,
            player1_name TEXT NOT NULL,
            player1_move TEXT NOT NULL,
            player2_id TEXT,
            player2_name TEXT,
            player2_move TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()


def get_pending_game(channel_id):
    """Get the most recent unfinished game in a channel (non-challenge only)"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT id, player1_id, player1_move, player2_id, player2_move 
        FROM games 
        WHERE channel_id = %s 
        AND player2_id IS NULL 
        AND status = 'pending'
        ORDER BY created_at DESC 
        LIMIT 1
    ''', (channel_id,))
    game = cur.fetchone()
    cur.close()
    conn.close()
    return game


def create_game(channel_id, channel_name, player_id, player_name, move, opponent_id=None, opponent_name=None):
    """Create a new game with the first player's move and optional opponent"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO games (channel_id, channel_name, player1_id, player1_name, player1_move, player2_id, player2_name)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    ''', (channel_id, channel_name, player_id, player_name, move, opponent_id, opponent_name))
    game_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return game_id


def update_game(game_id, player2_id, player2_name, move):
    """Update a game with the second player's move"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        UPDATE games 
        SET player2_id = %s, player2_name = %s, player2_move = %s, status = 'complete'
        WHERE id = %s
    ''', (player2_id, player2_name, move, game_id))
    conn.commit()
    cur.close()
    conn.close()

def get_pending_challenge(channel_id, challenger_id, opponent_id):
    """Get a pending challenge between two specific players"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT id, player1_id, player1_move
        FROM games 
        WHERE channel_id = %s 
        AND player1_id = %s
        AND player2_id = %s
        AND player2_move IS NULL
        AND status = 'pending'
        ORDER BY created_at DESC 
        LIMIT 1
    ''', (channel_id, challenger_id, opponent_id))
    game = cur.fetchone()
    cur.close()
    conn.close()
    return game
def get_nickname(user_id):
    """Get a user's nickname if it exists"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT nickname FROM nicknames WHERE user_id = %s', (user_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result[0] if result else None

def set_nickname(user_id, nickname):
    """Set or update a user's nickname"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO nicknames (user_id, nickname)
        VALUES (%s, %s)
        ON CONFLICT (user_id) 
        DO UPDATE SET nickname = EXCLUDED.nickname, updated_at = CURRENT_TIMESTAMP
    ''', (user_id, nickname))
    conn.commit()
    cur.close()
    conn.close()
