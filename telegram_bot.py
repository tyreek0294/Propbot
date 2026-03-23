import json
import re
import os
import urllib.request
import urllib.error
import time
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
MISTRAL_API_KEY = os.environ.get('MISTRAL_API_KEY', '')
TELEGRAM_API = 'https://api.telegram.org/bot' + TELEGRAM_TOKEN
MISTRAL_URL = 'https://api.mistral.ai/v1/chat/completions'
MISTRAL_MODEL = 'mistral-small-latest'

# 2025-26 NBA rosters - covers recent trades
NBA_ROSTERS = {
    'trae young': 'Atlanta Hawks', 'jalen johnson': 'Atlanta Hawks',
    'dejounte murray': 'Atlanta Hawks', 'clint capela': 'Atlanta Hawks',
    'jayson tatum': 'Boston Celtics', 'jaylen brown': 'Boston Celtics',
    'jrue holiday': 'Boston Celtics', 'al horford': 'Boston Celtics',
    'kristaps porzingis': 'Boston Celtics', 'derrick white': 'Boston Celtics',
    'payton pritchard': 'Boston Celtics',
    'cam thomas': 'Brooklyn Nets', 'nic claxton': 'Brooklyn Nets',
    'lamelo ball': 'Charlotte Hornets', 'miles bridges': 'Charlotte Hornets',
    'brandon miller': 'Charlotte Hornets', 'nique clifford': 'Charlotte Hornets',
    'mark williams': 'Charlotte Hornets',
    'zach lavine': 'Chicago Bulls', 'nikola vucevic': 'Chicago Bulls',
    'coby white': 'Chicago Bulls', 'josh giddey': 'Chicago Bulls',
    'ayo dosunmu': 'Chicago Bulls', 'dalen terry': 'Chicago Bulls',
    'donovan mitchell': 'Cleveland Cavaliers', 'darius garland': 'Cleveland Cavaliers',
    'evan mobley': 'Cleveland Cavaliers', 'jarrett allen': 'Cleveland Cavaliers',
    'max strus': 'Cleveland Cavaliers', 'sam merrill': 'Cleveland Cavaliers',
    'luka doncic': 'Dallas Mavericks', 'kyrie irving': 'Dallas Mavericks',
    'pj washington': 'Dallas Mavericks', 'daniel gafford': 'Dallas Mavericks',
    'klay thompson': 'Dallas Mavericks',
    'nikola jokic': 'Denver Nuggets', 'jamal murray': 'Denver Nuggets',
    'michael porter jr': 'Denver Nuggets', 'aaron gordon': 'Denver Nuggets',
    'kentavious caldwell-pope': 'Denver Nuggets',
    'cade cunningham': 'Detroit Pistons', 'jalen duren': 'Detroit Pistons',
    'ausar thompson': 'Detroit Pistons', 'bojan bogdanovic': 'Detroit Pistons',
    'stephen curry': 'Golden State Warriors', 'steph curry': 'Golden State Warriors',
    'draymond green': 'Golden State Warriors', 'andrew wiggins': 'Golden State Warriors',
    'jonathan kuminga': 'Golden State Warriors', 'brandin podziemski': 'Golden State Warriors',
    'alperen sengun': 'Houston Rockets', 'jalen green': 'Houston Rockets',
    'fred vanvleet': 'Houston Rockets', 'jabari smith jr': 'Houston Rockets',
    'dillon brooks': 'Houston Rockets', 'amen thompson': 'Houston Rockets',
    'tyrese haliburton': 'Indiana Pacers', 'pascal siakam': 'Indiana Pacers',
    'myles turner': 'Indiana Pacers', 'bennedict mathurin': 'Indiana Pacers',
    'andrew nembhard': 'Indiana Pacers', 'obi toppin': 'Indiana Pacers',
    'kawhi leonard': 'Los Angeles Clippers', 'james harden': 'Los Angeles Clippers',
    'ivica zubac': 'Los Angeles Clippers', 'norman powell': 'Los Angeles Clippers',
    'lebron james': 'Los Angeles Lakers', 'anthony davis': 'Los Angeles Lakers',
    'austin reaves': 'Los Angeles Lakers', 'rui hachimura': 'Los Angeles Lakers',
    'ja morant': 'Memphis Grizzlies', 'jaren jackson jr': 'Memphis Grizzlies',
    'desmond bane': 'Memphis Grizzlies', 'marcus smart': 'Memphis Grizzlies',
    'jimmy butler': 'Miami Heat', 'bam adebayo': 'Miami Heat',
    'tyler herro': 'Miami Heat', 'terry rozier': 'Miami Heat',
    'jaime jaquez jr': 'Miami Heat',
    'giannis antetokounmpo': 'Milwaukee Bucks', 'damian lillard': 'Milwaukee Bucks',
    'khris middleton': 'Milwaukee Bucks', 'brook lopez': 'Milwaukee Bucks',
    'bobby portis': 'Milwaukee Bucks',
    'anthony edwards': 'Minnesota Timberwolves', 'rudy gobert': 'Minnesota Timberwolves',
    'mike conley': 'Minnesota Timberwolves', 'jaden mcdaniels': 'Minnesota Timberwolves',
    'zion williamson': 'New Orleans Pelicans', 'cj mccollum': 'New Orleans Pelicans',
    'brandon ingram': 'New Orleans Pelicans', 'jonas valanciunas': 'New Orleans Pelicans',
    'herb jones': 'New Orleans Pelicans', 'trey murphy': 'New Orleans Pelicans',
    'jalen brunson': 'New York Knicks', 'julius randle': 'New York Knicks',
    'og anunoby': 'New York Knicks', 'mitchell robinson': 'New York Knicks',
    'donte divincenzo': 'New York Knicks', 'karl-anthony towns': 'New York Knicks',
    'shai gilgeous-alexander': 'Oklahoma City Thunder', 'chet holmgren': 'Oklahoma City Thunder',
    'jalen williams': 'Oklahoma City Thunder', 'luguentz dort': 'Oklahoma City Thunder',
    'isaiah joe': 'Oklahoma City Thunder',
    'paolo banchero': 'Orlando Magic', 'franz wagner': 'Orlando Magic',
    'wendell carter jr': 'Orlando Magic', 'jalen suggs': 'Orlando Magic',
    'joel embiid': 'Philadelphia 76ers', 'tyrese maxey': 'Philadelphia 76ers',
    'tobias harris': 'Philadelphia 76ers', 'kelly oubre jr': 'Philadelphia 76ers',
    'kevin durant': 'Phoenix Suns', 'devin booker': 'Phoenix Suns',
    'bradley beal': 'Phoenix Suns', 'jusuf nurkic': 'Phoenix Suns',
    'anfernee simons': 'Portland Trail Blazers', 'jerami grant': 'Portland Trail Blazers',
    'scoot henderson': 'Portland Trail Blazers', 'deandre ayton': 'Portland Trail Blazers',
    'domantas sabonis': 'Sacramento Kings', 'keegan murray': 'Sacramento Kings',
    'malik monk': 'Sacramento Kings', 'de aaron fox': 'Sacramento Kings',
    'victor wembanyama': 'San Antonio Spurs', 'devin vassell': 'San Antonio Spurs',
    'keldon johnson': 'San Antonio Spurs', 'jeremy sochan': 'San Antonio Spurs',
    'scottie barnes': 'Toronto Raptors', 'immanuel quickley': 'Toronto Raptors',
    'jakob poeltl': 'Toronto Raptors', 'rj barrett': 'Toronto Raptors',
    'lauri markkanen': 'Utah Jazz', 'jordan clarkson': 'Utah Jazz',
    'collin sexton': 'Utah Jazz', 'john collins': 'Utah Jazz',
    'kyle kuzma': 'Washington Wizards', 'deni avdija': 'Washington Wizards',
    'tyus jones': 'Washington Wizards',
}

def get_player_team(player_name):
    key = player_name.lower().strip()
    if key in NBA_ROSTERS:
        return NBA_ROSTERS[key]
    for roster_name, team in NBA_ROSTERS.items():
        if roster_name in key or key in roster_name:
            return team
    return None


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


def send_message(chat_id, text):
    tg_request('sendMessage', {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'Markdown'
    })


def edit_message(chat_id, message_id, text):
    try:
        tg_request('editMessageText', {
            'chat_id': chat_id,
            'message_id': message_id,
            'text': text,
            'parse_mode': 'Markdown'
        })
    except Exception:
        send_message(chat_id, text)


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


def extract_json(text):
    text = re.sub(r'```(?:json)?', '', text).strip()
    last_close = text.rfind('}')
    if last_close == -1:
        return None
    depth = 0
    for i in range(last_close, -1, -1):
        if text[i] == '}':
            depth += 1
        elif text[i] == '{':
            depth -= 1
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
    opponent = None
    vs_match = re.search(r'\bvs\.?\s+([a-z\s]+?)(?:\s+over|\s+under|\s+o/u|\s+\d|$)', t)
    if vs_match:
        opp_raw = vs_match.group(1).strip()
        opponent = ' '.join(w.capitalize() for w in opp_raw.split())
    stop_words = {
        'over', 'under', 'or', 'the', 'is', 'it', 'worth', 'points', 'point',
        'rebounds', 'rebound', 'assists', 'assist', 'steals', 'steal',
        'blocks', 'block', 'threes', 'three', 'pointers', 'pointer',
        '3pm', 'pra', 'pts', 'reb', 'ast', 'stl', 'blk', 'vs',
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
    return {'player': player, 'stat': stat, 'line': line, 'opponent': opponent}


def analyze_prop(player, stat, line, opponent):
    today = datetime.now().strftime('%A, %B %d, %Y')
    opp_text = opponent if opponent else 'their next opponent'
    known_team = get_player_team(player)
    team_text = known_team if known_team else 'their NBA team'
    system = (
        'You are an expert NBA prop analyst for the 2025-26 season. '
        'The player ' + player + ' plays for ' + team_text + '. '
        'Use this exact team in your response. '
        'Reply with ONLY raw JSON, no markdown, no explanation.'
    )
    user = (
        'Analyze: ' + player + ' (' + team_text + ') vs ' + opp_text +
        ', ' + stat + ', line ' + str(line) + ', date ' + today + '.'
        ' Provide realistic 2025-26 season stats.'
        ' hit_rate_over = games over ' + str(line) + ' in last 10.'
        ' Return ONLY this JSON:'
        ' {"player_name":"' + player + '","team":"' + team_text + '","position":"","opponent":"' + opp_text + '","game_time":"ET",'
        '"stat_type":"' + stat + '","line":' + str(line) + ',"season_avg":0.0,"last10_avg":0.0,'
        '"h2h_avg":0.0,"h2h_games":[{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0},{"game":"vs/@ TEAM Mon DD","value":0}],'
        '"injury_status":"Active","projected":0.0,"confidence":"HIGH",'
        '"summary":"2 sentences",'
        '"hit_rate_over":0,'
        '"over_points":["stat reason","matchup reason","form reason"],'
        '"under_points":["stat reason","defense reason","risk reason"],'
        '"verdict":"OVER or UNDER or LEAN OVER or LEAN UNDER or PASS",'
        '"verdict_explanation":"2-3 sentences"}'
    )
    raw = mistral_chat(system, user)
    return extract_json(raw)


def hit_rate_bar(hits, total=10):
    return 'O' * hits + 'X' * (total - hits) + '  *' + str(hits) + '/' + str(total) + '*'


def format_response(d, line):
    proj = float(d.get('projected') or d.get('last10_avg') or 0)
    verdict = (d.get('verdict') or 'PASS').upper()
    conf = (d.get('confidence') or 'MEDIUM').upper()
    hits = min(10, max(0, int(d.get('hit_rate_over') or 0)))
    l5_games = (d.get('h2h_games') or [])[:5]
    l5_vals = [float(g.get('value', 0)) for g in l5_games]
    l5_avg = round(sum(l5_vals) / len(l5_vals), 1) if l5_vals else proj
    over_pts = d.get('over_points') or []
    under_pts = d.get('under_points') or []
    player = str(d.get('player_name', ''))
    stat = str(d.get('stat_type', ''))
    team = str(d.get('team', ''))
    opp = str(d.get('opponent', '?'))
    game_time = str(d.get('game_time', ''))
    injury = str(d.get('injury_status', 'Active'))
    verdict_exp = str(d.get('verdict_explanation', ''))

    # Header line like: tari eason hasn't hit 10.5 once in his last 10 games
    summary = str(d.get('summary', ''))

    # Format: PLAYER STAT — VERDICT LINE
    title = '*' + player + ' ' + stat.upper() + ' — ' + verdict + ' ' + str(line) + '*'

    # Subheader: TEAM @ OPP · Proj: X · CONF confidence
    home_away = team + ' @ ' + opp
    subheader = home_away + ' · Proj: ' + str(proj) + ' · ' + conf + ' confidence'

    # Injury note if not active
    injury_note = ''
    if injury.lower() != 'active':
        injury_note = '_' + injury + '_\n'

    # Over points
    over_section = '*Pushing him OVER:*\n'
    for p in over_pts[:3]:
        over_section += '• ' + str(p) + '\n'

    # Under points
    under_section = '*Pushing him UNDER:*\n'
    for p in under_pts[:3]:
        under_section += '• ' + str(p) + '\n'

    # Verdict line
    verdict_line = '*Verdict: ' + verdict + '* — ' + verdict_exp

    # Recent stats line
    recent = '*Recent:* L5: ' + str(l5_avg) + ' | L10: ' + str(d.get('last10_avg', proj)) + ' | Hit rate: ' + str(hits) + '/10'

    msg = (
        '_' + summary + '_\n\n'
        + title + '\n'
        + subheader + '\n'
        + (injury_note if injury_note else '') + '\n'
        + over_section + '\n'
        + under_section + '\n'
        + verdict_line + '\n\n'
        + recent + '\n\n'
        + '_For entertainment only. Not financial advice._'
    )
    return msg


HELP_TEXT = (
    '*NBA Prop Analyst Bot*\n\n'
    'Include the opponent with vs for best results:\n\n'
    'Jaylen Brown vs Heat over 24.5 points\n'
    'Josh Giddey vs Raptors under 9.5 rebounds\n'
    'CJ McCollum vs Warriors 17.5 points\n'
    'Jokic vs Bulls under 11.5 rebounds\n\n'
    '*Stats:* points, rebounds, assists, 3PM, steals, blocks, PRA\n\n'
    '_For entertainment only. Not financial advice._'
)


def handle_message(chat_id, text):
    text = text.strip()
    if text.lower() in ('/start', '/help', 'help'):
        send_message(chat_id, HELP_TEXT)
        return
    prop = parse_prop(text)
    if not prop:
        send_message(chat_id, 'Could not parse. Try: Josh Giddey vs Raptors under 9.5 rebounds')
        return
    player = prop['player']
    stat = prop['stat']
    line = prop['line']
    opponent = prop['opponent']
    known_team = get_player_team(player)
    opp_display = ' vs ' + opponent if opponent else ''
    team_display = ' (' + known_team + ')' if known_team else ''
    resp = tg_request('sendMessage', {
        'chat_id': chat_id,
        'text': 'Analyzing *' + player + team_display + opp_display + '* - ' + stat + ' O/U *' + str(line) + '*...',
        'parse_mode': 'Markdown'
    })
    msg_id = resp['result']['message_id']
    try:
        data = analyze_prop(player, stat, line, opponent)
        if not data or not data.get('player_name'):
            edit_message(chat_id, msg_id, 'Could not generate analysis. Try: ' + player + ' vs OpponentTeam over ' + str(line) + ' ' + stat)
            return
        result = format_response(data, line)
        edit_message(chat_id, msg_id, result)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        edit_message(chat_id, msg_id, 'API error ' + str(e.code) + ': ' + body[:200])
    except Exception as e:
        edit_message(chat_id, msg_id, 'Error: ' + str(e)[:200])


def run_bot():
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


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'OK')
    def log_message(self, format, *args):
        pass


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    print('Bot running on port ' + str(port))
    server.serve_forever()
