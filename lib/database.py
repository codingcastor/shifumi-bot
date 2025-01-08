import os
import psycopg2
from datetime import datetime
from lib.types import Gesture


def get_db_connection():
    """Get a PostgreSQL database connection"""
    return psycopg2.connect(os.getenv('DATABASE_URL'))


def init_game_table():
    """Create the games table if it doesn't exist"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS games (
            id SERIAL PRIMARY KEY,
            channel_id TEXT NOT NULL,
            player1_id TEXT NOT NULL,
            player1_move TEXT NOT NULL,
            player2_id TEXT,
            player2_move TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()


def get_pending_game(channel_id):
    """Get the most recent unfinished game in a channel"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT id, player1_id, player1_move, player2_id, player2_move 
        FROM games 
        WHERE channel_id = %s AND player2_id IS NULL 
        ORDER BY created_at DESC 
        LIMIT 1
    ''', (channel_id,))
    game = cur.fetchone()
    cur.close()
    conn.close()
    return game


def create_game(channel_id, player_id, move):
    """Create a new game with the first player's move"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO games (channel_id, player1_id, player1_move)
        VALUES (%s, %s, %s)
        RETURNING id
    ''', (channel_id, player_id, move))
    game_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return game_id


def update_game(game_id, player2_id, move):
    """Update a game with the second player's move"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        UPDATE games 
        SET player2_id = %s, player2_move = %s
        WHERE id = %s
    ''', (player2_id, move, game_id))
    conn.commit()
    cur.close()
    conn.close()

