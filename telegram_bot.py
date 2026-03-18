import json
import re
import os
import urllib.request
import urllib.error
import time
from datetime import datetime, timezone

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
MISTRAL_API_KEY = os.environ.get('MISTRAL_API_KEY', '')
TELEGRAM_API = 'https://api.telegram.org/bot' + TELEGRAM_TOKEN
MISTRAL_URL = 'https://api.mistral.ai/v1/chat/completions'
MISTRAL_MODEL = 'mistral-small-latest'


def tg_request(method, params=None):
    url = TELEGRAM_API + '/' + method
    data = json.dumps(params or {}).encode('utf-8')
    req = urllib.request.Request(
        url, data=data,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8'))


def send_message(chat_id, text, parse_mode='Markdown'):
    tg_request('sendMessage', {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': parse_mode
    })


def edit_message(chat_id, message_id, text, parse_mode='Markdown'):
    try:
        tg_request('editMessageText', {
            'chat_id': chat_id,
            'message_id': message_id,
            'text': text,
            'parse_mode': parse_mode
        })
    except Exception:
        send_message(chat_id, text, parse_mode)


def mistral_chat(system, user):
    payload = json.dumps({
        'model': MISTRAL_MODEL,
        'messages': [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': user}
        ],
        'temperature': 0.1,
        'max_tokens': 2000
    }).encode('utf-8')
    req = urllib.request.Request(
        MISTRAL_URL, data=payload,
        headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + MISTRAL_API_KEY
        },
        method='POST'
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    return data['choices'][0]['message']['content'].strip()


def fetch_todays_schedule():
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    url = 'https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        games = []
        game_dates = data.get('leagueSchedule', {}).get('gameDates', [])
        for gd in game_dates:
            if gd.get('gameDate', '').startswith(today):
                for g in gd.get('games', []):
                    home = g.get('homeTeam', {}).get('teamName', '')
                    away = g.get('awayTeam', {}).get('teamName', '')
                    home_city = g.get('homeTeam', {}).get('teamCity', '')
                    away_city = g.get('awayTeam', {}).get('teamCity', '')
                    game_time = g.get('gameDateTimeUTC', '')
                    games.append({
                        'home': home_city + ' ' + home,
                        'away': away_city + ' ' + away,
                        'home_abbr': g.get('homeTeam', {}).get('teamTricode', ''),
                        'away_abbr': g.get('awayTeam', {}).get('teamTricode', ''),
                        'time': game_time
                    })
        return games
    except Exception as e:
        print('Schedule fetch error: ' + str(e))
        return []


def find_player_game(player_name, schedule):
    if not schedule:
        return None, None
    system = 'You are an NBA expert. Given a player name and list of todays NBA games, identify which game the player is in. Return ONLY a JSON object: {"team": "full team name", "opponent": "full opponent name", "home_or_away": "home or away"}. If player not found return {"team": "unknown", "opponent": "unknown", "home_or_away": "unknown"}. No markdown.'
    games_str = '\n'.join([g['away'] + ' @ ' + g['home'] for g in schedule])
    user = 'Player: ' + player_name + '\nTodays games:\n' + games_str + '\nWhich game is this player in?'
    try:
        raw = mistral_chat(system, user)
        raw = re.sub(r'```(?:json)?', '', raw).strip()
        last_close = raw.rfind('}')
        if last_close == -1:
            return None, None
        depth = 0
        for i in range(last_close, -1, -1):
            if raw[i] == '}': depth += 1
            elif raw[i] == '{': depth -= 1
            if depth == 0:
                result = json.loads(raw[i:last_close+1])
                if result.get('opponent') and result['opponent'] != 'unknown':
                    return result.get('team', ''), result.get('opponent', '')
                return None, None
    except Exception as e:
        print('Player game lookup error: ' + str(e))
        return None, None


def extract_json(text):
    text = re.sub(r'```(?:json)?', '', text).strip()
    last_close = text.rfind('}')
    if last_close == -1:
        return None
    depth = 0
    for i in range(last_close, -1, -1):
        if text[i] == '}': depth += 1
        elif text[i] == '{': depth -= 1
        if depth == 0:
            try:
                return json.loads(text[i:last_close + 1])
            except json.JSONDecodeError:
                return None
    return None


def parse_prop(text):
    t = text.lower().strip()
    line_match = re.search(r'\b(\d+\.?\d*)\b', t)
    if not line_match:
        return None
    line = float(line_match.group(1))
    stat = 'points'
    if any(x in t for x in ['pra', 'points rebounds assists']):
        stat = 'points rebounds assists'
    elif any(x in t for x in ['p+a', 'points assists']):
        stat = 'points assists'
    elif any(x in t for x in ['p+r', 'points rebounds']):
        stat = 'points rebounds'
    elif any(x in t for x in ['3pm', 'three pointer', 'threes', '3 pointer']):
        stat = 'three pointers made'
    elif 'rebound' in t or ' reb' in t:
        stat = 'rebounds'
    elif 'assist' in t or ' ast' in t:
        stat = 'assists'
    elif 'steal' in t:
        stat = 'steals'
    elif 'block' in t:
        stat = 'blocks'
    stop_words = {
        'over', 'under', 'or', 'the', 'is', 'it', 'worth', 'points', 'point',
        'rebounds', 'rebound', 'assists', 'assist', 'steals', 'steal',
        'blocks', 'block', 'threes', 'three', 'pointers', 'pointer',
        '3pm', 'pra', 'pts', 'reb', 'ast', 'stl', 'blk',
        'tonight', 'today', 'game', 'prop', 'bet', 'take', 'hitting',
        'o/u', 'ou', str(int(line)), str(line)
    }
    words = text.split()
    player_words = []
    for word in words:
        clean = re.sub(r'[^a-zA-Z\-\.]', '', word).lower()
        if clean and clean not in stop_words and not re.match(r'^\d+\.?\d*$', word):
            player_words.append(word)
    if len(player_words) < 1:
        return None
    player = ' '.join(w.capitalize() for w in ' '.join(player_words[:4]).split())
    return {'player': player, 'stat': stat, 'line': line}


def analyze_prop(player, stat, line, team, opponent):
    today = datetime.now().strftime('%A, %B %d, %Y')
    system = 'You are an expert NBA prop analyst. You have accurate knowledge of NBA player stats for the 2025-26 season. Reply with ONLY raw JSON, no markdown, no explanation.'
    user = (
        'Analyze this NBA prop. Player: ' + player +
        '. Team: ' + team +
        '. Opponent TODAY: ' + opponent +
        '. Stat: ' + stat +
        '. Line: ' + str(line) +
        '. Date: ' + today + '.'
        ' Provide: realistic last 10 game logs for ' + stat + ' based on their 2025-26 season form.'
        ' Last 5 H2H games specifically vs ' + opponent + ' for this stat.'
        ' hit_rate_over = exact count of last 10 games where value exceeded ' + str(line) + '.'
        ' 3 detailed over points and 3 detailed under points each as one full sentence citing specific stats.'
        ' Return ONLY this JSON:'
        ' {"player_name":"' + player + '","team":"' + team + '","position":"","opponent":"' + opponent + '","game_time":"",'
        '"stat_type":"' + stat + '","line":' + str(line) + ',"season_avg":0.0,"last10_avg":0.0,'
        '"h2h_avg":0.0,"h2h_games":[{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0}],'
        '"last10_games":[{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0}],'
        '"injury_status":"Active","projected":0.0,"confidence":"HIGH",'
        '"summary":"2 sentence summary",'
        '"hit_rate_over":0,'
        '"over_points":["sentence with specific stats","sentence with H2H or matchup data","sentence with form or context"],'
        '"under_points":["sentence with specific stats","sentence with defensive data","sentence with risk factors"],'
        '"verdict":"OVER or UNDER or LEAN OVER or LEAN UNDER or PASS",'
        '"verdict_explanation":"2-3 sentences citing key stats"}'
    )
    raw = mistral_chat(system, user)
    return extract_json(raw)


def hit_rate_bar(hits, total=10):
    return 'O' * hits + 'X' * (total - hits) + '  *' + str(hits) + '/' + str(total) + '*'


def format_response(d, line):
    proj = float(d.get('projected') or d.get('last10_avg') or 0)
    diff = round(proj - float(line), 1)
    diff_s = ('+' if diff > 0 else '') + str(diff)
    verdict = (d.get('verdict') or 'PASS').upper()
    conf = (d.get('confidence') or 'MEDIUM').upper()
    conf_icon = {'HIGH': 'HIGH', 'MEDIUM': 'MED', 'LOW': 'LOW'}.get(conf, 'MED')
    hits = min(10, max(0, int(d.get('hit_rate_over') or 0)))
    hit_bar = hit_rate_bar(hits)

    h2h = d.get('h2h_games') or []
    h2h_rows = ''
    for g in h2h[:5]:
        v = float(g.get('value', 0))
        icon = 'O' if v > float(line) else 'X'
        h2h_rows += icon + ' ' + str(g.get('game', '?')) + '  *' + str(v) + '*\n'

    over_pts = d.get('over_points') or []
    under_pts = d.get('under_points') or []

    msg = (
        '*' + str(d.get('player_name', '')) + '  |  ' + str(d.get('stat_type', '')) + ' O/U ' + str(line) + '*\n'
        + str(d.get('team', '')) + ' vs *' + str(d.get('opponent', '?')) + '*  ' + str(d.get('game_time', '')) + '\n'
        + 'Injury: ' + str(d.get('injury_status', 'Active')) + '\n\n'
        + '*PROJECTIONS*\n'
        + 'Season Avg: *' + str(d.get('season_avg', '--')) + '*\n'
        + 'Last 10 Avg: *' + str(d.get('last10_avg', '--')) + '*\n'
        + 'Projected: *' + str(proj) + '*  (' + diff_s + ' vs line)\n\n'
        + '*CONFIDENCE: ' + conf_icon + '*\n'
        + str(d.get('summary', '')) + '\n\n'
        + '*HIT RATE  ' + str(hits) + '/10*\n'
        + hit_bar + '\n\n'
        + '*LAST 5 H2H vs ' + str(d.get('opponent', '?')) + '*\n'
        + (h2h_rows or 'No H2H data\n') + '\n'
        + '*CASE FOR OVER*\n'
        + '\n'.join(str(i+1) + '. ' + str(p) for i, p in enumerate(over_pts[:3])) + '\n\n'
        + '*CASE FOR UNDER*\n'
        + '\n'.join(str(i+1) + '. ' + str(p) for i, p in enumerate(under_pts[:3])) + '\n\n'
        + '*VERDICT: ' + verdict + '*\n'
        + str(d.get('verdict_explanation', '')) + '\n\n'
        + '_For entertainment only. Not financial advice._'
    )
    return msg


HELP_TEXT = (
    '*NBA Prop Analyst Bot*\n\n'
    'Just send me a player, stat, and line:\n\n'
    'LeBron James over 25.5 points\n'
    'Steph Curry 4.5 threes\n'
    'Jokic under 11.5 rebounds\n'
    'Jaylen Brown 21.5 points\n\n'
    '*Stats:* points, rebounds, assists, 3PM, steals, blocks, PRA, P+A, P+R\n\n'
    '_For entertainment only. Not financial advice._'
)


def handle_message(chat_id, text):
    text = text.strip()
    if text.lower() in ('/start', '/help', 'help'):
        send_message(chat_id, HELP_TEXT)
        return

    prop = parse_prop(text)
    if not prop:
        send_message(chat_id, 'Could not parse that. Try: LeBron James over 25.5 points')
        return

    player = prop['player']
    stat = prop['stat']
    line = prop['line']

    resp = tg_request('sendMessage', {
        'chat_id': chat_id,
        'text': 'Fetching todays NBA schedule...',
        'parse_mode': 'Markdown'
    })
    msg_id = resp['result']['message_id']

    try:
        # Step 1: Get real schedule from NBA.com
        schedule = fetch_todays_schedule()

        if schedule:
            edit_message(chat_id, msg_id, 'Schedule loaded - finding ' + player + ' game...')
            team, opponent = find_player_game(player, schedule)
        else:
            team, opponent = None, None

        if not opponent:
            edit_message(chat_id, msg_id, 'Could not find ' + player + ' in todays schedule. They may not be playing today.')
            return

        edit_message(chat_id, msg_id, 'Found: ' + team + ' vs ' + opponent + '\nAnalyzing ' + player + ' ' + stat + ' O/U ' + str(line) + '...')

        # Step 2: Run full analysis with confirmed opponent
        data = analyze_prop(player, stat, line, team, opponent)

        if not data or not data.get('player_name'):
            edit_message(chat_id, msg_id, 'Could not generate analysis for *' + player + '*. Try rephrasing.')
            return

        result = format_response(data, line)
        edit_message(chat_id, msg_id, result)

    except urllib.error.HTTPError as e:
        body = e.read().decode()
        edit_message(chat_id, msg_id, 'API error ' + str(e.code) + ': ' + body[:200])
    except Exception as e:
        edit_message(chat_id, msg_id, 'Error: ' + str(e)[:200])


def main():
    print('NBA Prop Bot starting...')
    offset = 0
    while True:
        try:
            resp = tg_request('getUpdates', {'offset': offset, 'timeout': 30})
            updates = resp.get('result', [])
            for update in updates:
                offset = update['update_id'] + 1
                message = update.get('message', {})
                chat_id = message.get('chat', {}).get('id')
                text = message.get('text', '')
                if chat_id and text:
                    try:
                        handle_message(chat_id, text)
                    except Exception as e:
                        print('Handler error: ' + str(e))
        except Exception as e:
            print('Poll error: ' + str(e))
            time.sleep(5)


if __name__ == '__main__':
    main()
import json
import re
import os
import urllib.request
import urllib.error
import time
from datetime import datetime, timezone

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
MISTRAL_API_KEY = os.environ.get('MISTRAL_API_KEY', '')
TELEGRAM_API = 'https://api.telegram.org/bot' + TELEGRAM_TOKEN
MISTRAL_URL = 'https://api.mistral.ai/v1/chat/completions'
MISTRAL_MODEL = 'mistral-small-latest'


def tg_request(method, params=None):
    url = TELEGRAM_API + '/' + method
    data = json.dumps(params or {}).encode('utf-8')
    req = urllib.request.Request(
        url, data=data,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8'))


def send_message(chat_id, text, parse_mode='Markdown'):
    tg_request('sendMessage', {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': parse_mode
    })


def edit_message(chat_id, message_id, text, parse_mode='Markdown'):
    try:
        tg_request('editMessageText', {
            'chat_id': chat_id,
            'message_id': message_id,
            'text': text,
            'parse_mode': parse_mode
        })
    except Exception:
        send_message(chat_id, text, parse_mode)


def mistral_chat(system, user):
    payload = json.dumps({
        'model': MISTRAL_MODEL,
        'messages': [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': user}
        ],
        'temperature': 0.1,
        'max_tokens': 2000
    }).encode('utf-8')
    req = urllib.request.Request(
        MISTRAL_URL, data=payload,
        headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + MISTRAL_API_KEY
        },
        method='POST'
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    return data['choices'][0]['message']['content'].strip()


def fetch_todays_schedule():
    # gameDateEst format is 'YYYY-MM-DDT00:00:00Z' - match on EST date
    from datetime import timedelta
    # Use ET date (UTC-5) for NBA schedule
    now_et = datetime.now(timezone.utc) - timedelta(hours=5)
    today_est = now_et.strftime('%Y-%m-%d') + 'T00:00:00Z'
    url = 'https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json'
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Referer': 'https://www.nba.com/'
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        games = []
        game_dates = data.get('leagueSchedule', {}).get('gameDates', [])
        print('Total game dates in schedule: ' + str(len(game_dates)))
        print('Looking for EST date: ' + today_est)
        for gd in game_dates:
            gdate = gd.get('gameDate', '')
            # Try gameDateEst field on each game, and also gameDate on the date group
            if gdate == today_est or gdate.startswith(now_et.strftime('%Y-%m-%d')):
                print('Found matching date group: ' + gdate)
                for g in gd.get('games', []):
                    home_city = g.get('homeTeam', {}).get('teamCity', '')
                    home_name = g.get('homeTeam', {}).get('teamName', '')
                    away_city = g.get('awayTeam', {}).get('teamCity', '')
                    away_name = g.get('awayTeam', {}).get('teamName', '')
                    games.append({
                        'home': home_city + ' ' + home_name,
                        'away': away_city + ' ' + away_name,
                        'home_abbr': g.get('homeTeam', {}).get('teamTricode', ''),
                        'away_abbr': g.get('awayTeam', {}).get('teamTricode', ''),
                    })
                break
            # Also check individual game dates
            for g in gd.get('games', []):
                gde = g.get('gameDateEst', '')
                if gde.startswith(now_et.strftime('%Y-%m-%d')):
                    home_city = g.get('homeTeam', {}).get('teamCity', '')
                    home_name = g.get('homeTeam', {}).get('teamName', '')
                    away_city = g.get('awayTeam', {}).get('teamCity', '')
                    away_name = g.get('awayTeam', {}).get('teamName', '')
                    entry = {
                        'home': home_city + ' ' + home_name,
                        'away': away_city + ' ' + away_name,
                        'home_abbr': g.get('homeTeam', {}).get('teamTricode', ''),
                        'away_abbr': g.get('awayTeam', {}).get('teamTricode', ''),
                    }
                    if entry not in games:
                        games.append(entry)
        print('Games found for today: ' + str(len(games)))
        for g in games:
            print('  ' + g['away'] + ' @ ' + g['home'])
        return games
    except Exception as e:
        print('Schedule fetch error: ' + str(e))
        return []


def find_player_game(player_name, schedule):
    if not schedule:
        return None, None
    system = 'You are an NBA expert. Given a player name and list of todays NBA games, identify which game the player is in. Return ONLY a JSON object: {"team": "full team name", "opponent": "full opponent name", "home_or_away": "home or away"}. If player not found return {"team": "unknown", "opponent": "unknown", "home_or_away": "unknown"}. No markdown.'
    games_str = '\n'.join([g['away'] + ' @ ' + g['home'] for g in schedule])
    user = 'Player: ' + player_name + '\nTodays games:\n' + games_str + '\nWhich game is this player in?'
    try:
        raw = mistral_chat(system, user)
        raw = re.sub(r'```(?:json)?', '', raw).strip()
        last_close = raw.rfind('}')
        if last_close == -1:
            return None, None
        depth = 0
        for i in range(last_close, -1, -1):
            if raw[i] == '}': depth += 1
            elif raw[i] == '{': depth -= 1
            if depth == 0:
                result = json.loads(raw[i:last_close+1])
                if result.get('opponent') and result['opponent'] != 'unknown':
                    return result.get('team', ''), result.get('opponent', '')
                return None, None
    except Exception as e:
        print('Player game lookup error: ' + str(e))
        return None, None


def extract_json(text):
    text = re.sub(r'```(?:json)?', '', text).strip()
    last_close = text.rfind('}')
    if last_close == -1:
        return None
    depth = 0
    for i in range(last_close, -1, -1):
        if text[i] == '}': depth += 1
        elif text[i] == '{': depth -= 1
        if depth == 0:
            try:
                return json.loads(text[i:last_close + 1])
            except json.JSONDecodeError:
                return None
    return None


def parse_prop(text):
    t = text.lower().strip()
    line_match = re.search(r'\b(\d+\.?\d*)\b', t)
    if not line_match:
        return None
    line = float(line_match.group(1))
    stat = 'points'
    if any(x in t for x in ['pra', 'points rebounds assists']):
        stat = 'points rebounds assists'
    elif any(x in t for x in ['p+a', 'points assists']):
        stat = 'points assists'
    elif any(x in t for x in ['p+r', 'points rebounds']):
        stat = 'points rebounds'
    elif any(x in t for x in ['3pm', 'three pointer', 'threes', '3 pointer']):
        stat = 'three pointers made'
    elif 'rebound' in t or ' reb' in t:
        stat = 'rebounds'
    elif 'assist' in t or ' ast' in t:
        stat = 'assists'
    elif 'steal' in t:
        stat = 'steals'
    elif 'block' in t:
        stat = 'blocks'
    stop_words = {
        'over', 'under', 'or', 'the', 'is', 'it', 'worth', 'points', 'point',
        'rebounds', 'rebound', 'assists', 'assist', 'steals', 'steal',
        'blocks', 'block', 'threes', 'three', 'pointers', 'pointer',
        '3pm', 'pra', 'pts', 'reb', 'ast', 'stl', 'blk',
        'tonight', 'today', 'game', 'prop', 'bet', 'take', 'hitting',
        'o/u', 'ou', str(int(line)), str(line)
    }
    words = text.split()
    player_words = []
    for word in words:
        clean = re.sub(r'[^a-zA-Z\-\.]', '', word).lower()
        if clean and clean not in stop_words and not re.match(r'^\d+\.?\d*$', word):
            player_words.append(word)
    if len(player_words) < 1:
        return None
    player = ' '.join(w.capitalize() for w in ' '.join(player_words[:4]).split())
    return {'player': player, 'stat': stat, 'line': line}


def analyze_prop(player, stat, line, team, opponent):
    today = datetime.now().strftime('%A, %B %d, %Y')
    system = 'You are an expert NBA prop analyst. You have accurate knowledge of NBA player stats for the 2025-26 season. Reply with ONLY raw JSON, no markdown, no explanation.'
    user = (
        'Analyze this NBA prop. Player: ' + player +
        '. Team: ' + team +
        '. Opponent TODAY: ' + opponent +
        '. Stat: ' + stat +
        '. Line: ' + str(line) +
        '. Date: ' + today + '.'
        ' Provide: realistic last 10 game logs for ' + stat + ' based on their 2025-26 season form.'
        ' Last 5 H2H games specifically vs ' + opponent + ' for this stat.'
        ' hit_rate_over = exact count of last 10 games where value exceeded ' + str(line) + '.'
        ' 3 detailed over points and 3 detailed under points each as one full sentence citing specific stats.'
        ' Return ONLY this JSON:'
        ' {"player_name":"' + player + '","team":"' + team + '","position":"","opponent":"' + opponent + '","game_time":"",'
        '"stat_type":"' + stat + '","line":' + str(line) + ',"season_avg":0.0,"last10_avg":0.0,'
        '"h2h_avg":0.0,"h2h_games":[{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0}],'
        '"last10_games":[{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0}],'
        '"injury_status":"Active","projected":0.0,"confidence":"HIGH",'
        '"summary":"2 sentence summary",'
        '"hit_rate_over":0,'
        '"over_points":["sentence with specific stats","sentence with H2H or matchup data","sentence with form or context"],'
        '"under_points":["sentence with specific stats","sentence with defensive data","sentence with risk factors"],'
        '"verdict":"OVER or UNDER or LEAN OVER or LEAN UNDER or PASS",'
        '"verdict_explanation":"2-3 sentences citing key stats"}'
    )
    raw = mistral_chat(system, user)
    return extract_json(raw)


def hit_rate_bar(hits, total=10):
    return 'O' * hits + 'X' * (total - hits) + '  *' + str(hits) + '/' + str(total) + '*'


def format_response(d, line):
    proj = float(d.get('projected') or d.get('last10_avg') or 0)
    diff = round(proj - float(line), 1)
    diff_s = ('+' if diff > 0 else '') + str(diff)
    verdict = (d.get('verdict') or 'PASS').upper()
    conf = (d.get('confidence') or 'MEDIUM').upper()
    conf_icon = {'HIGH': 'HIGH', 'MEDIUM': 'MED', 'LOW': 'LOW'}.get(conf, 'MED')
    hits = min(10, max(0, int(d.get('hit_rate_over') or 0)))
    hit_bar = hit_rate_bar(hits)

    h2h = d.get('h2h_games') or []
    h2h_rows = ''
    for g in h2h[:5]:
        v = float(g.get('value', 0))
        icon = 'O' if v > float(line) else 'X'
        h2h_rows += icon + ' ' + str(g.get('game', '?')) + '  *' + str(v) + '*\n'

    over_pts = d.get('over_points') or []
    under_pts = d.get('under_points') or []

    msg = (
        '*' + str(d.get('player_name', '')) + '  |  ' + str(d.get('stat_type', '')) + ' O/U ' + str(line) + '*\n'
        + str(d.get('team', '')) + ' vs *' + str(d.get('opponent', '?')) + '*  ' + str(d.get('game_time', '')) + '\n'
        + 'Injury: ' + str(d.get('injury_status', 'Active')) + '\n\n'
        + '*PROJECTIONS*\n'
        + 'Season Avg: *' + str(d.get('season_avg', '--')) + '*\n'
        + 'Last 10 Avg: *' + str(d.get('last10_avg', '--')) + '*\n'
        + 'Projected: *' + str(proj) + '*  (' + diff_s + ' vs line)\n\n'
        + '*CONFIDENCE: ' + conf_icon + '*\n'
        + str(d.get('summary', '')) + '\n\n'
        + '*HIT RATE  ' + str(hits) + '/10*\n'
        + hit_bar + '\n\n'
        + '*LAST 5 H2H vs ' + str(d.get('opponent', '?')) + '*\n'
        + (h2h_rows or 'No H2H data\n') + '\n'
        + '*CASE FOR OVER*\n'
        + '\n'.join(str(i+1) + '. ' + str(p) for i, p in enumerate(over_pts[:3])) + '\n\n'
        + '*CASE FOR UNDER*\n'
        + '\n'.join(str(i+1) + '. ' + str(p) for i, p in enumerate(under_pts[:3])) + '\n\n'
        + '*VERDICT: ' + verdict + '*\n'
        + str(d.get('verdict_explanation', '')) + '\n\n'
        + '_For entertainment only. Not financial advice._'
    )
    return msg


HELP_TEXT = (
    '*NBA Prop Analyst Bot*\n\n'
    'Just send me a player, stat, and line:\n\n'
    'LeBron James over 25.5 points\n'
    'Steph Curry 4.5 threes\n'
    'Jokic under 11.5 rebounds\n'
    'Jaylen Brown 21.5 points\n\n'
    '*Stats:* points, rebounds, assists, 3PM, steals, blocks, PRA, P+A, P+R\n\n'
    '_For entertainment only. Not financial advice._'
)


def handle_message(chat_id, text):
    text = text.strip()
    if text.lower() in ('/start', '/help', 'help'):
        send_message(chat_id, HELP_TEXT)
        return

    prop = parse_prop(text)
    if not prop:
        send_message(chat_id, 'Could not parse that. Try: LeBron James over 25.5 points')
        return

    player = prop['player']
    stat = prop['stat']
    line = prop['line']

    resp = tg_request('sendMessage', {
        'chat_id': chat_id,
        'text': 'Fetching todays NBA schedule...',
        'parse_mode': 'Markdown'
    })
    msg_id = resp['result']['message_id']

    try:
        # Step 1: Get real schedule from NBA.com
        schedule = fetch_todays_schedule()

        if schedule:
            edit_message(chat_id, msg_id, 'Schedule loaded - finding ' + player + ' game...')
            team, opponent = find_player_game(player, schedule)
        else:
            team, opponent = None, None

        if not opponent:
            edit_message(chat_id, msg_id, 'Could not find ' + player + ' in todays schedule. They may not be playing today.')
            return

        edit_message(chat_id, msg_id, 'Found: ' + team + ' vs ' + opponent + '\nAnalyzing ' + player + ' ' + stat + ' O/U ' + str(line) + '...')

        # Step 2: Run full analysis with confirmed opponent
        data = analyze_prop(player, stat, line, team, opponent)

        if not data or not data.get('player_name'):
            edit_message(chat_id, msg_id, 'Could not generate analysis for *' + player + '*. Try rephrasing.')
            return

        result = format_response(data, line)
        edit_message(chat_id, msg_id, result)

    except urllib.error.HTTPError as e:
        body = e.read().decode()
        edit_message(chat_id, msg_id, 'API error ' + str(e.code) + ': ' + body[:200])
    except Exception as e:
        edit_message(chat_id, msg_id, 'Error: ' + str(e)[:200])


def main():
    print('NBA Prop Bot starting...')
    offset = 0
    while True:
        try:
            resp = tg_request('getUpdates', {'offset': offset, 'timeout': 30})
            updates = resp.get('result', [])
            for update in updates:
                offset = update['update_id'] + 1
                message = update.get('message', {})
                chat_id = message.get('chat', {}).get('id')
                text = message.get('text', '')
                if chat_id and text:
                    try:
                        handle_message(chat_id, text)
                    except Exception as e:
                        print('Handler error: ' + str(e))
        except Exception as e:
            print('Poll error: ' + str(e))
            time.sleep(5)


if __name__ == '__main__':
    main()
