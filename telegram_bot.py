import json
import re
import os
import urllib.request
import urllib.error
import time
from datetime import datetime

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


def ai_chat(system, user):
    payload = json.dumps({
        'model': MISTRAL_MODEL,
        'messages': [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': user}
        ],
        'temperature': 0.2,
        'max_tokens': 1500
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
    stop_words = {
        'over', 'under', 'or', 'the', 'is', 'it', 'worth', 'points', 'point',
        'rebounds', 'rebound', 'assists', 'assist', 'steals', 'steal',
        'blocks', 'block', 'threes', 'three', 'pointers', 'pointer',
        '3pm', 'pra', 'pts', 'reb', 'ast', 'stl', 'blk',
        'tonight', 'today', 'game', 'prop', 'bet', 'take', 'hitting',
        str(int(line)), str(line)
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


def analyze_prop(player, stat, line):
    today = datetime.now().strftime('%A, %B %d, %Y')
    system = 'You are an NBA prop analyst. Reply with ONLY raw JSON, no markdown, no explanation.'
    user = (
        'NBA prop: ' + player + ', ' + stat + ', line ' + str(line) + ', today ' + today + '.'
        ' Give realistic stats based on their known performance.'
        ' JSON: {"player_name":"","team":"","position":"","opponent":"todays opponent","game_time":"",'
        '"stat_type":"' + stat + '","line":' + str(line) + ',"season_avg":0.0,"last10_avg":0.0,'
        '"last10_games":[{"game":"vs TEAM Mon DD","value":0},{"game":"vs TEAM Mon DD","value":0},{"game":"vs TEAM Mon DD","value":0},{"game":"vs TEAM Mon DD","value":0},{"game":"vs TEAM Mon DD","value":0},{"game":"vs TEAM Mon DD","value":0},{"game":"vs TEAM Mon DD","value":0},{"game":"vs TEAM Mon DD","value":0},{"game":"vs TEAM Mon DD","value":0},{"game":"vs TEAM Mon DD","value":0}],'
        '"h2h_avg":0.0,"h2h_games":[{"game":"vs TEAM Mon DD","value":0},{"game":"vs TEAM Mon DD","value":0},{"game":"vs TEAM Mon DD","value":0},{"game":"vs TEAM Mon DD","value":0},{"game":"vs TEAM Mon DD","value":0}],'
        '"injury_status":"Active","projected":0.0,"confidence":"HIGH","summary":"brief",'
        '"hit_rate_over":0,"over_points":["r1","r2","r3"],"under_points":["r1","r2","r3"],'
        '"verdict":"OVER","verdict_explanation":"brief"}'
    )
    raw = ai_chat(system, user)
    return extract_json(raw)


def format_response(d, line):
    proj = float(d.get('projected') or d.get('last10_avg') or 0)
    diff = round(proj - float(line), 1)
    diff_s = ('+' if diff > 0 else '') + str(diff)
    verdict = (d.get('verdict') or 'PASS').upper()
    conf = (d.get('confidence') or 'MEDIUM').upper()

    if 'OVER' in verdict:
        v_icon = 'UP'
    elif 'UNDER' in verdict:
        v_icon = 'DOWN'
    else:
        v_icon = 'PASS'

    conf_icon = {'HIGH': 'HIGH', 'MEDIUM': 'MED', 'LOW': 'LOW'}.get(conf, 'MED')

    hits = min(10, max(0, int(d.get('hit_rate_over') or 0)))
    hit_bar = 'O' * hits + 'X' * (10 - hits)

    games10 = d.get('last10_games') or []
    game_rows = ''
    for g in games10[:10]:
        v = float(g.get('value', 0))
        icon = 'O' if v > float(line) else 'X'
        game_rows += icon + ' ' + str(g.get('game', '?')) + '  *' + str(v) + '*\n'

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
        + '*LAST 10 GAMES*\n'
        + (game_rows or 'No data\n') + '\n'
        + '*LAST 5 H2H vs ' + str(d.get('opponent', '?')) + '*\n'
        + (h2h_rows or 'No data\n') + '\n'
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
        'text': 'Analyzing *' + player + '* - ' + stat + ' O/U *' + str(line) + '*...',
        'parse_mode': 'Markdown'
    })
    msg_id = resp['result']['message_id']

    try:
        data = analyze_prop(player, stat, line)
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
