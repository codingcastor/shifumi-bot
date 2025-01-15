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
            user_name TEXT NOT NULL,
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


def get_pending_challenge(challenger_id, opponent_id):
    """Get a pending challenge between two specific players"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT id, player1_id, player1_move
        FROM games 
        WHERE (
            (player1_id = %s AND player2_id = %s) OR
            (player1_id = %s AND player2_id = %s)
        )
        AND player2_move IS NULL
        AND status = 'pending'
        ORDER BY created_at DESC 
        LIMIT 1
    ''', (challenger_id, opponent_id, opponent_id, challenger_id))
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
    
    # Update cache and return
    nickname = result[0] if result else None
    return nickname


def set_nickname(user_id, nickname, user_name):
    """Set or update a user's nickname and username"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO nicknames (user_id, nickname, user_name)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id) 
        DO UPDATE SET 
            nickname = EXCLUDED.nickname,
            user_name = EXCLUDED.user_name,
            updated_at = CURRENT_TIMESTAMP
    ''', (user_id, nickname, user_name))
    conn.commit()
    cur.close()
    conn.close()


def get_pending_challenges():
    """Get all pending challenges"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT 
            channel_id,
            player1_id,
            player2_id,
            created_at
        FROM games 
        WHERE status = 'pending'
        AND player2_id IS NOT NULL
        AND player2_move IS NULL
        ORDER BY created_at DESC
    ''')
    results = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            'channel_id': row[0],
            'challenger_id': row[1],
            'opponent_id': row[2],
            'created_at': row[3]
        }
        for row in results
    ]


def get_user_stats(user_id):
    """Get detailed stats for a specific user"""
    conn = get_db_connection()
    cur = conn.cursor()

    # Get overall stats
    cur.execute('''
        WITH game_results AS (
            -- First player wins
            SELECT 
                player1_id as winner_id,
                player1_name as winner_name,
                player2_id as loser_id,
                player2_name as loser_name,
                created_at,
                'WIN' as result
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
                player2_name as winner_name,
                player1_id as loser_id,
                player1_name as loser_name,
                created_at,
                'WIN' as result
            FROM games
            WHERE status = 'complete'
                AND EXTRACT(YEAR FROM created_at) = EXTRACT(YEAR FROM CURRENT_DATE)
                AND (
                    (player2_move = 'ROCK' AND player1_move = 'SCISSORS') OR
                    (player2_move = 'PAPER' AND player1_move = 'ROCK') OR
                    (player2_move = 'SCISSORS' AND player1_move = 'PAPER')
                )
            UNION ALL
             -- Draws as player 1
            SELECT
                player1_id as winner_id,
                player1_name as winner_name,
                player2_id as loser_id,
                player2_name as loser_name,
                created_at,
                'DRAW' as result
            FROM games
            WHERE status = 'complete'
                AND player1_id = %s
                AND EXTRACT(YEAR FROM created_at) = EXTRACT(YEAR FROM CURRENT_DATE)
                AND player1_move = player2_move
            UNION ALL
            -- Draws as player 2
            SELECT
                player2_id as winner_id,
                player2_name as winner_name,
                player1_id as loser_id,
                player1_name as loser_name,
                created_at,
                'DRAW' as result
            FROM games
            WHERE status = 'complete'
                AND player2_id = %s
                AND EXTRACT(YEAR FROM created_at) = EXTRACT(YEAR FROM CURRENT_DATE)
                AND player1_move = player2_move
        ),
        nemesis AS (
            SELECT 
                winner_id as opponent_id,
                winner_name as opponent_name,
                COUNT(*) as wins
            FROM game_results
            WHERE loser_id = %s
            AND result = 'WIN'
            GROUP BY winner_id, winner_name
            ORDER BY wins DESC
            LIMIT 1
        ),
        best_against AS (
            SELECT 
                loser_id as opponent_id,
                loser_name as opponent_name,
                COUNT(*) as wins
            FROM game_results
            WHERE winner_id = %s
            AND result = 'WIN'
            GROUP BY loser_id, loser_name
            ORDER BY wins DESC
            LIMIT 1
        ),
        most_draws AS (
            SELECT loser_id as opponent_id, loser_name as opponent_name,
                count(*) as draws
            FROM game_results
            WHERE result = 'DRAW'
            GROUP BY loser_id, loser_name
            ORDER BY draws DESC
            LIMIT 1
        ),
        user_stats AS (
            SELECT 
                COUNT(CASE WHEN winner_id = %s AND result = 'WIN' THEN 1 END) as wins,
                COUNT(CASE WHEN loser_id = %s  AND result = 'WIN' THEN 1 END) as losses,
                COUNT(CASE WHEN result = 'DRAW' THEN 1 END) as draws
            FROM game_results
            WHERE winner_id = %s OR loser_id = %s
        )
        SELECT 
            s.wins, s.losses, s.draws,
            n.opponent_id as nemesis_id,
            n.opponent_name as nemesis_name,
            n.wins as nemesis_wins,
            b.opponent_id as best_against_id,
            b.opponent_name as best_against_name,
            b.wins as best_against_wins,
            md.opponent_id as most_draws_id, md.opponent_name as most_draws_name,
            md.draws as most_draws_count
        FROM user_stats s
        LEFT JOIN nemesis n ON true
        LEFT JOIN best_against b ON true
        LEFT JOIN most_draws md ON true
    ''', (user_id, user_id, user_id, user_id, user_id, user_id, user_id, user_id))

    result = cur.fetchone()
    cur.close()
    conn.close()

    if not result:
        return None

    wins, losses, draws = result[0:3]
    nemesis_id, nemesis_name, nemesis_wins = result[3:6]
    best_against_id, best_again_name, best_against_wins = result[6:9]
    most_draws_id, most_draws_name, most_draws_wins = result[9:12]
    total_games = wins + losses + draws

    win_rate = round(wins / total_games * 100, 1) if total_games > 0 else 0

    return {
        'wins': wins,
        'losses': losses,
        'draws': draws,
        'total_games': total_games,
        'win_rate': win_rate,
        'nemesis': {
            'user_id': nemesis_id,
            'user_name': nemesis_name,
            'wins': nemesis_wins
        } if nemesis_id else None,
        'best_against': {
            'user_id': best_against_id,
            'user_name': best_again_name,
            'wins': best_against_wins
        } if best_against_id else None,
        'most_draws': {
            'user_id': most_draws_id,
            'user_name': most_draws_name,
            'draws': most_draws_wins
        }
    }


def get_unranked_players():
    """Get players who haven't played enough games to be ranked"""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute('''
        WITH game_results AS (
            -- First player participation
            SELECT 
                player1_id as player_id,
                player1_name as player_name
            FROM games 
            WHERE status = 'complete'
                AND EXTRACT(YEAR FROM created_at) = EXTRACT(YEAR FROM CURRENT_DATE)
            UNION ALL
            -- Second player participation
            SELECT 
                player2_id as player_id,
                player2_name as player_name
            FROM games 
            WHERE status = 'complete'
                AND EXTRACT(YEAR FROM created_at) = EXTRACT(YEAR FROM CURRENT_DATE)
                AND player2_id IS NOT NULL
        )
        SELECT 
            player_id,
            MAX(player_name) as player_name,
            COUNT(*) as games_played,
            5 - COUNT(*) as games_needed
        FROM game_results
        GROUP BY player_id
        HAVING COUNT(*) < 5
        ORDER BY COUNT(*) DESC, MAX(player_name)
    ''')

    results = cur.fetchall()
    cur.close()
    conn.close()

    return [
        {
            'player_id': row[0],
            'player_name': row[1],
            'games_played': row[2],
            'games_needed': row[3]
        }
        for row in results
    ]


def get_leaderboard():
    """Get the leaderboard for the current year"""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute('''
        WITH game_results AS (
            -- First player wins
            SELECT 
                player1_id as winner_id,
                player2_id as loser_id,
                player1_name as winner_name,
                player2_name as loser_name,
                'WIN' as result
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
                player1_id as loser_id,
                player2_name as winner_name,
                player1_name as loser_name,
                'WIN' as result
            FROM games 
            WHERE status = 'complete'
                AND EXTRACT(YEAR FROM created_at) = EXTRACT(YEAR FROM CURRENT_DATE)
                AND (
                    (player2_move = 'ROCK' AND player1_move = 'SCISSORS') OR
                    (player2_move = 'PAPER' AND player1_move = 'ROCK') OR
                    (player2_move = 'SCISSORS' AND player1_move = 'PAPER')
                )
            UNION ALL
            -- Draws (each player gets counted once)
            SELECT 
                player1_id as winner_id,
                player2_id as loser_id,
                player1_name as winner_name,
                player2_name as loser_name,
                'DRAW' as result
            FROM games 
            WHERE status = 'complete'
                AND EXTRACT(YEAR FROM created_at) = EXTRACT(YEAR FROM CURRENT_DATE)
                AND player1_move = player2_move
            UNION ALL
            SELECT 
                player2_id as winner_id,
                player1_id as loser_id,
                player2_name as winner_name,
                player1_name as loser_name,
                'DRAW' as result
            FROM games 
            WHERE status = 'complete'
                AND EXTRACT(YEAR FROM created_at) = EXTRACT(YEAR FROM CURRENT_DATE)
                AND player1_move = player2_move
        ),
        player_stats AS (
            SELECT 
                p.player_id,
                p.player_name,
                p.wins,
                p.losses,
                p.draws,
                p.total_games,
                ROUND(CAST(CAST(p.wins AS FLOAT) / NULLIF(p.total_games, 0) * 100 AS numeric), 1) as win_rate
            FROM (
                SELECT 
                    player_id,
                    player_name,
                    COUNT(CASE WHEN result = 'WIN' THEN 1 END) as wins,
                    COUNT(CASE WHEN result = 'DRAW' THEN 1 END) as draws,
                    COUNT(CASE WHEN result IS NULL THEN 1 END) as losses,
                    COUNT(*) as total_games
                FROM (
                    SELECT winner_id as player_id, winner_name as player_name, result FROM game_results
                    UNION ALL
                    SELECT loser_id as player_id, loser_name as player_name, NULL as result FROM game_results WHERE result = 'WIN'
                ) all_results
                GROUP BY player_id, player_name
            ) p
            WHERE p.total_games >= 5
        )
        SELECT 
            player_id,
            player_name as user_name,
            wins,
            losses,
            draws,
            total_games,
            win_rate
        FROM player_stats
        ORDER BY win_rate DESC, wins DESC,total_games DESC
    ''')

    results = cur.fetchall()
    cur.close()
    conn.close()

    return [
        {
            'player_id': row[0],
            'user_name': row[1],
            'wins': row[2],
            'losses': row[3],
            'draws': row[4],
            'total_games': row[5],
            'win_rate': row[6]
        }
        for row in results
    ]


def get_game_by_id(game_id):
    """Get a game by its ID.
    Returns (game_id, player1_id, player1_move, player2_id, player2_move) if found, None otherwise"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT id, player1_id, player1_move, player2_id, player2_move
        FROM games 
        WHERE id = %s
        AND status = 'pending'
        LIMIT 1
    ''', (game_id,))
    game = cur.fetchone()
    cur.close()
    conn.close()
    return game
