import os
import psycopg2


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


def get_leaderboard():
    """Get the leaderboard for the current year"""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute('''
        WITH game_results AS (
            -- First player wins
            SELECT 
                player1_id as winner_id,
                player2_id as loser_id
            FROM games 
            WHERE status = 'complete'
                AND EXTRACT(YEAR FROM created_at) = EXTRACT(YEAR FROM CURRENT_DATE)
                AND (
                    (player1_move = 'ROCK' AND player2_move = 'SCISSORS') OR
                    (player1_move = 'PAPER' AND player2_move = 'ROCK') OR
                    (player1_move = 'SCISSORS' AND player2_move = 'PAPER')
                )
            UNION ALL
            -- Second player wins
            SELECT 
                player2_id as winner_id,
                player1_id as loser_id
            FROM games 
            WHERE status = 'complete'
                AND EXTRACT(YEAR FROM created_at) = EXTRACT(YEAR FROM CURRENT_DATE)
                AND (
                    (player2_move = 'ROCK' AND player1_move = 'SCISSORS') OR
                    (player2_move = 'PAPER' AND player1_move = 'ROCK') OR
                    (player2_move = 'SCISSORS' AND player1_move = 'PAPER')
                )
        ),
        player_stats AS (
            SELECT 
                p.player_id,
                p.wins,
                p.losses,
                p.total_games,
                ROUND(CAST(CAST(p.wins AS FLOAT) / NULLIF(p.total_games, 0) * 100 AS numeric), 1) as win_rate
            FROM (
                SELECT 
                    player_id,
                    COUNT(CASE WHEN is_win THEN 1 END) as wins,
                    COUNT(CASE WHEN NOT is_win THEN 1 END) as losses,
                    COUNT(*) as total_games
                FROM (
                    SELECT winner_id as player_id, TRUE as is_win FROM game_results
                    UNION ALL
                    SELECT loser_id as player_id, FALSE as is_win FROM game_results
                ) all_results
                GROUP BY player_id
            ) p
            WHERE p.total_games > 0
        )
        SELECT 
            player_id,
            wins,
            losses,
            total_games,
            win_rate
        FROM player_stats
        ORDER BY  win_rate DESC, wins DESC,total_games DESC
    ''')

    results = cur.fetchall()
    cur.close()
    conn.close()

    return [
        {
            'player_id': row[0],
            'wins': row[1],
            'losses': row[2],
            'total_games': row[3],
            'win_rate': row[4]
        }
        for row in results
    ]
