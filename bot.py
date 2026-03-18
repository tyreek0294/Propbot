import discord
import json
import re
import os
import urllib.request
import urllib.error
from datetime import datetime

DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN', '')
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions'
GROQ_MODEL = 'llama-3.3-70b-versatile'

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)


def groq_chat(system, user, max_tokens=4000):
    payload = json.dumps({
        'model': GROQ_MODEL,
        'max_tokens': max_tokens,
        'temperature': 0.3,
        'messages': [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': user}
        ]
    }).encode('utf-8')
    req = urllib.request.Request(
        GROQ_URL,
        data=payload,
        headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + GROQ_API_KEY
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


def parse_prop_request(message_text):
    # Pure Python regex parsing - no API call needed
    text = message_text.lower().strip()

    # Extract line number
    line_match = re.search(r'\b(\d+\.?\d*)\b', text)
    if not line_match:
        return None
    line = float(line_match.group(1))

    # Extract stat
    stat = 'points'
    if any(x in text for x in ['pra', 'pts+reb+ast', 'points rebounds assists']):
        stat = 'points rebounds assists'
    elif any(x in text for x in ['p+a', 'pts+ast', 'points assists']):
        stat = 'points assists'
    elif any(x in text for x in ['p+r', 'pts+reb', 'points rebounds']):
        stat = 'points rebounds'
    elif any(x in text for x in ['3pm', 'three pointer', 'threes', '3 pointer', 'three-pointer']):
        stat = 'three pointers made'
    elif 'rebound' in text or ' reb' in text:
        stat = 'rebounds'
    elif 'assist' in text or ' ast' in text:
        stat = 'assists'
    elif 'steal' in text or ' stl' in text:
        stat = 'steals'
    elif 'block' in text or ' blk' in text:
        stat = 'blocks'
    elif 'point' in text or ' pts' in text or ' pt ' in text:
        stat = 'points'

    # Extract player name - remove common words and the line number
    stop_words = [
        'over', 'under', 'or', 'the', 'is', 'it', 'worth', 'points', 'point',
        'rebounds', 'rebound', 'assists', 'assist', 'steals', 'steal',
        'blocks', 'block', 'threes', 'three', 'pointers', 'pointer',
        '3pm', 'pra', 'pts', 'reb', 'ast', 'stl', 'blk', 'p+a', 'p+r',
        'tonight', 'today', 'game', 'prop', 'bet', 'take', 'hitting',
        str(int(line)), str(line)
    ]
    words = message_text.split()
    player_words = []
    for word in words:
        clean = re.sub(r'[^a-zA-Z\-\.]', '', word).lower()
        if clean and clean not in stop_words and not re.match(r'^\d+\.?\d*$', word):
            player_words.append(word)

    if len(player_words) < 1:
        return None

    player = ' '.join(player_words[:4])
    # Capitalise each word
    player = ' '.join(w.capitalize() for w in player.split())

    return {'player': player, 'stat': stat, 'line': line}


def analyze_prop(player, stat, line):
    today = datetime.now().strftime('%A, %B %d, %Y')
    system = (
        'You are an expert NBA prop betting analyst. Today is ' + today + '. '
        'You have deep knowledge of NBA player stats, schedules, recent form, '
        'head-to-head matchups, and injury reports. '
        'Respond with ONLY a raw JSON object, no markdown, no code fences, no explanation.'
    )
    schema = (
        '{'
        '"player_name": "string", '
        '"team": "string", '
        '"position": "string", '
        '"opponent": "string", '
        '"game_time": "string", '
        '"stat_type": "' + stat + '", '
        '"line": ' + str(line) + ', '
        '"season_avg": 0.0, '
        '"last10_avg": 0.0, '
        '"last10_games": [{"game": "vs/@ TEAM Mon DD", "value": 0}], '
        '"h2h_avg": 0.0, '
        '"h2h_games": [{"game": "vs/@ TEAM Mon DD", "value": 0}], '
        '"injury_status": "Active", '
        '"projected": 0.0, '
        '"confidence": "HIGH", '
        '"summary": "1-2 sentence summary", '
        '"hit_rate_over": 0, '
        '"over_points": ["reason1", "reason2", "reason3"], '
        '"under_points": ["reason1", "reason2", "reason3"], '
        '"verdict": "OVER", '
        '"verdict_explanation": "2-3 sentences"'
        '}'
    )
    user = (
        'Analyze this NBA prop: Player=' + player +
        ' Stat=' + stat +
        ' Line=' + str(line) +
        ' Today=' + today +
        '\n1. Find their team and opponent today (within 24 hours).'
        '\n2. Give last 10 game logs for this stat (realistic values).'
        '\n3. Give last 5 H2H games vs today opponent.'
        '\n4. Check injury status.'
        '\n5. Project and give verdict.'
        '\nReturn ONLY this JSON: ' + schema
    )
    raw = groq_chat(system, user, max_tokens=3000)
    return extract_json(raw)


def hit_rate_bar(hits, total=10):
    return 'O' * hits + 'X' * (total - hits) + '  **' + str(hits) + '/' + str(total) + '**'


def build_embed(d, line):
    proj = float(d.get('projected') or d.get('last10_avg') or 0)
    diff = round(proj - float(line), 1)
    diff_s = ('+' if diff > 0 else '') + str(diff)
    verdict = (d.get('verdict') or 'PASS').upper()
    conf = (d.get('confidence') or 'MEDIUM').upper()

    if 'OVER' in verdict:
        colour = discord.Colour.green()
    elif 'UNDER' in verdict:
        colour = discord.Colour.red()
    else:
        colour = discord.Colour.greyple()

    c_icon = {'HIGH': 'GREEN', 'MEDIUM': 'YELLOW', 'LOW': 'RED'}.get(conf, 'WHITE')
    v_icon = 'UP' if 'OVER' in verdict else ('DOWN' if 'UNDER' in verdict else 'PAUSE')

    embed = discord.Embed(
        title=str(v_icon) + '  ' + str(d.get('player_name', 'Player')) + '  -  ' + str(d.get('stat_type', '')) + ' O/U ' + str(line),
        description=(
            str(d.get('team', '?')) + '  ' + str(d.get('position', '')) +
            '  vs  ' + str(d.get('opponent', '?')) +
            '  ' + str(d.get('game_time', 'Today')) +
            '\nInjury: ' + str(d.get('injury_status', 'Active'))
        ),
        colour=colour,
        timestamp=datetime.utcnow()
    )

    embed.add_field(
        name='Projections',
        value=(
            'Season Avg: **' + str(d.get('season_avg', '--')) + '**\n'
            'Last 10 Avg: **' + str(d.get('last10_avg', '--')) + '**\n'
            'Projected: **' + str(proj) + '**  (' + diff_s + ' vs line)'
        ),
        inline=True
    )

    embed.add_field(
        name=c_icon + ' Confidence: ' + conf,
        value=str(d.get('summary', '--')),
        inline=True
    )

    embed.add_field(name='\u200b', value='\u200b', inline=False)

    hits = min(10, max(0, int(d.get('hit_rate_over') or 0)))
    embed.add_field(
        name='Hit Rate - Last 10 over ' + str(line),
        value=hit_rate_bar(hits),
        inline=False
    )

    games10 = d.get('last10_games') or []
    if games10:
        rows = []
        for g in games10[:10]:
            v = float(g.get('value', 0))
            icon = 'O' if v > float(line) else 'X'
            rows.append(icon + ' ' + str(g.get('game', '?')) + '  **' + str(v) + '**')
        embed.add_field(name='Last 10 Games', value='\n'.join(rows), inline=True)

    h2h = d.get('h2h_games') or []
    if h2h:
        rows = []
        for g in h2h[:5]:
            v = float(g.get('value', 0))
            icon = 'O' if v > float(line) else 'X'
            rows.append(icon + ' ' + str(g.get('game', '?')) + '  **' + str(v) + '**')
        embed.add_field(name='Last 5 H2H vs ' + str(d.get('opponent', '?')), value='\n'.join(rows), inline=True)

    embed.add_field(name='\u200b', value='\u200b', inline=False)

    over_pts = d.get('over_points') or []
    under_pts = d.get('under_points') or []

    embed.add_field(
        name='Case for OVER',
        value='\n'.join('**' + str(i+1) + '.** ' + str(p) for i, p in enumerate(over_pts[:3])) or '--',
        inline=True
    )
    embed.add_field(
        name='Case for UNDER',
        value='\n'.join('**' + str(i+1) + '.** ' + str(p) for i, p in enumerate(under_pts[:3])) or '--',
        inline=True
    )

    embed.add_field(name='\u200b', value='\u200b', inline=False)
    embed.add_field(
        name='VERDICT: ' + verdict,
        value=str(d.get('verdict_explanation', '--')),
        inline=False
    )
    embed.set_footer(text='NBA Prop Analyst - Powered by Groq - For entertainment only')
    return embed


HELP_TEXT = (
    '**NBA Prop Analyst Bot**\n\n'
    'Just @ me with a player, stat, and line:\n\n'
    '> `@Propbot LeBron James over 25.5 points`\n'
    '> `@Propbot Steph Curry 4.5 threes`\n'
    '> `@Propbot Jokic under 11.5 rebounds`\n'
    '> `@Propbot Jaylen Brown 20.5 points`\n\n'
    '**Stats:** points, rebounds, assists, 3PM, steals, blocks, PRA, P+A, P+R\n\n'
    'For entertainment only. Not financial advice.'
)


@bot.event
async def on_ready():
    print('Propbot is live: ' + str(bot.user))
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name='NBA props'
        )
    )


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if bot.user not in message.mentions:
        return

    content = re.sub(r'<@!?\d+>', '', message.content).strip()

    if not content or content.lower() in ('help', '?', 'commands'):
        await message.reply(HELP_TEXT)
        return

    async with message.channel.typing():
        prop = parse_prop_request(content)
        if not prop:
            await message.reply(
                'Could not parse that prop. Try:\n'
                '`@Propbot LeBron James over 25.5 points`'
            )
            return

        player = prop['player']
        stat = prop['stat']
        line = prop['line']

        thinking = await message.reply(
            'Analyzing **' + player + '** - ' + stat + ' O/U **' + str(line) + '**...\n'
            '_Checking last 10 games, H2H, injury status..._'
        )

        try:
            data = analyze_prop(player, stat, line)
            if not data or not data.get('player_name'):
                await thinking.edit(
                    content='Could not generate analysis for **' + player + '**. Try rephrasing.'
                )
                return
            embed = build_embed(data, line)
            await thinking.edit(content='', embed=embed)

        except urllib.error.HTTPError as e:
            body = e.read().decode()
            await thinking.edit(content='Groq API error ' + str(e.code) + ': ' + body[:150])
        except Exception as e:
            await thinking.edit(content='Error: ' + str(e)[:200])


if __name__ == '__main__':
    bot.run(DISCORD_TOKEN)
