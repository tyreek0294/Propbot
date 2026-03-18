import discord
import json
import re
import os
import urllib.request
import urllib.error
from datetime import datetime

# ── Config ───────────────────────────────────────────────────────────────────
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN", "YOUR_DISCORD_TOKEN_HERE")
GROQ_API_KEY  = os.environ.get("GROQ_API_KEY",  "YOUR_GROQ_API_KEY_HERE")

GROQ_URL  = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"  # free, fast, highly capable

# ── Discord client ────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

# ── Groq API call (no external libraries needed) ──────────────────────────────
def groq_chat(system, user, max_tokens=4000):
    """Call Groq API using only Python stdlib — no pip install needed."""
    payload = json.dumps({
        "model": GROQ_MODEL,
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user}
        ]
    }).encode("utf-8")

    req = urllib.request.Request(
        GROQ_URL,
        data=payload,
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {GROQ_API_KEY}"
        },
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    return data["choices"][0]["message"]["content"].strip()


# ── JSON extractor ────────────────────────────────────────────────────────────
def extract_json(text):
    """Find the last valid JSON object in a string."""
    # Strip markdown fences if present
    text = re.sub(r"```(?:json)?", "", text).strip()
    last_close = text.rfind("}")
    if last_close == -1:
        return None
    depth = 0
    for i in range(last_close, -1, -1):
        if text[i] == "}":
            depth += 1
        elif text[i] == "{":
            depth -= 1
        if depth == 0:
            try:
                return json.loads(text[i:last_close + 1])
            except json.JSONDecodeError:
                return None
    return None


# ── Parse natural language prop request ───────────────────────────────────────
def parse_prop_request(message_text):
    """Extract player, stat, line from a natural language message."""
    system = (
        "You extract NBA prop bet details from messages. "
        "Return ONLY a JSON object with keys: "
        "player (full name string), "
        "stat (one of: points, rebounds, assists, three pointers made, steals, blocks, "
        "points rebounds assists, points assists, points rebounds), "
        "line (number). "
        'If you cannot find all three values return {"error": "missing info"}. '
        "No markdown, no explanation, just raw JSON."
    )
    try:
        raw  = groq_chat(system, message_text, max_tokens=200)
        data = extract_json(raw)
        if not data or "error" in data:
            return None
        if not all(k in data for k in ("player", "stat", "line")):
            return None
        return data
    except Exception:
        return None


# ── Full prop analysis ─────────────────────────────────────────────────────────
def analyze_prop(player, stat, line):
    """Run full prop analysis and return structured dict."""
    today = datetime.now().strftime("%A, %B %d, %Y")

    system = (
        f"You are an expert NBA prop betting analyst. Today is {today}. "
        "You have comprehensive knowledge of NBA player stats, season averages, "
        "recent game logs, head-to-head history, injuries, and team context. "
        "Always provide realistic, data-driven analysis. "
        "Respond with ONLY a raw JSON object — no markdown, no code fences, no explanation before or after."
    )

    user = f"""Analyze this NBA prop bet and return a JSON object.

Player: {player}
Stat: {stat}
Line: {line}
Today: {today}

INSTRUCTIONS:
1. Identify which team {player} plays for and their opponent today (within 24 hours).
2. List their last 10 game logs for {stat} with realistic values based on their known season form.
3. List last 5 head-to-head games vs today's opponent for this stat.
4. Note injury status and any relevant team context.
5. Project the stat and give a clear over/under verdict.

Return ONLY this exact JSON (fill all fields, no nulls):
{{
  "player_name": "full name",
  "team": "team name",
  "position": "position",
  "opponent": "opponent team",
  "game_time": "e.g. 7:30 PM ET",
  "stat_type": "{stat}",
  "line": {line},
  "season_avg": 0.0,
  "last10_avg": 0.0,
  "last10_games": [
    {{"game": "vs/@ TEAM Mon DD", "value": 0}}
  ],
  "h2h_avg": 0.0,
  "h2h_games": [
    {{"game": "vs/@ TEAM Mon DD", "value": 0}}
  ],
  "injury_status": "Active or injury detail",
  "projected": 0.0,
  "confidence": "HIGH or MEDIUM or LOW",
  "summary": "1-2 sentence punchy summary",
  "hit_rate_over": 0,
  "over_points": ["reason 1", "reason 2", "reason 3"],
  "under_points": ["reason 1", "reason 2", "reason 3"],
  "verdict": "OVER or UNDER or LEAN OVER or LEAN UNDER or PASS",
  "verdict_explanation": "2-3 sentence explanation"
}}"""

    raw = groq_chat(system, user, max_tokens=3000)
    return extract_json(raw)


# ── Embed builders ─────────────────────────────────────────────────────────────
def hit_rate_bar(hits, total=10):
    return "🟢" * hits + "🔴" * (total - hits) + f"  **{hits}/{total}**"

def confidence_emoji(conf):
    return {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}.get((conf or "").upper(), "⚪")

def verdict_emoji(verdict):
    v = (verdict or "").upper()
    if "OVER"  in v: return "📈"
    if "UNDER" in v: return "📉"
    return "⏸️"

def build_embed(d, line):
    proj   = float(d.get("projected") or d.get("last10_avg") or 0)
    diff   = round(proj - float(line), 1)
    diff_s = f"+{diff}" if diff > 0 else str(diff)

    verdict = (d.get("verdict") or "PASS").upper()
    conf    = (d.get("confidence") or "MEDIUM").upper()
    v_emoji = verdict_emoji(verdict)
    c_emoji = confidence_emoji(conf)

    colour = discord.Colour.green() if "OVER" in verdict else \
             discord.Colour.red()   if "UNDER" in verdict else \
             discord.Colour.greyple()

    embed = discord.Embed(
        title=f"{v_emoji}  {d.get('player_name','Player')}  —  {d.get('stat_type', stat)} O/U {line}",
        description=(
            f"**{d.get('team','?')}**  {d.get('position','')}  ·  "
            f"vs **{d.get('opponent','?')}**  ·  {d.get('game_time','Today')}\n"
            f"🩹 {d.get('injury_status','Active')}"
        ),
        colour=colour,
        timestamp=datetime.utcnow()
    )

    # Projections
    embed.add_field(
        name="📊 Projections",
        value=(
            f"Season Avg: **{d.get('season_avg','--')}**\n"
            f"Last 10 Avg: **{d.get('last10_avg','--')}**\n"
            f"Projected: **{proj}**  ({diff_s} vs line)"
        ),
        inline=True
    )

    # Confidence
    embed.add_field(
        name=f"{c_emoji} Confidence: {conf}",
        value=d.get("summary", "--"),
        inline=True
    )

    embed.add_field(name="\u200b", value="\u200b", inline=False)

    # Hit rate
    hits = min(10, max(0, int(d.get("hit_rate_over") or 0)))
    embed.add_field(
        name=f"🎯 Hit Rate — Last 10 over {line}",
        value=hit_rate_bar(hits),
        inline=False
    )

    # Last 10 games
    games10 = d.get("last10_games") or []
    if games10:
        rows = []
        for g in games10[:10]:
            v    = float(g.get("value", 0))
            icon = "🟢" if v > float(line) else "🔴"
            rows.append(f"{icon} `{str(g.get('game','?')):<18}` **{v}**")
        embed.add_field(
            name="📅 Last 10 Games",
            value="\n".join(rows),
            inline=True
        )

    # H2H
    h2h = d.get("h2h_games") or []
    if h2h:
        rows = []
        for g in h2h[:5]:
            v    = float(g.get("value", 0))
            icon = "🟢" if v > float(line) else "🔴"
            rows.append(f"{icon} `{str(g.get('game','?')):<18}` **{v}**")
        embed.add_field(
            name=f"🔄 Last 5 H2H vs {d.get('opponent','?')}",
            value="\n".join(rows),
            inline=True
        )

    embed.add_field(name="\u200b", value="\u200b", inline=False)

    # Over / Under cases
    over_pts  = d.get("over_points")  or []
    under_pts = d.get("under_points") or []
    embed.add_field(
        name="📈 Case for OVER",
        value="\n".join(f"**{i+1}.** {p}" for i, p in enumerate(over_pts[:3])) or "--",
        inline=True
    )
    embed.add_field(
        name="📉 Case for UNDER",
        value="\n".join(f"**{i+1}.** {p}" for i, p in enumerate(under_pts[:3])) or "--",
        inline=True
    )

    embed.add_field(name="\u200b", value="\u200b", inline=False)

    # Verdict
    embed.add_field(
        name=f"{v_emoji} VERDICT: {verdict}",
        value=d.get("verdict_explanation", "--"),
        inline=False
    )

    embed.set_footer(text="NBA Prop Analyst · Powered by Groq · For entertainment only")
    return embed


# ── Help text ─────────────────────────────────────────────────────────────────
HELP_TEXT = """
**NBA Prop Analyst Bot** 🏀

Just @ me with a player, stat, and line:

> `@PropBot LeBron James over 25.5 points`
> `@PropBot Steph Curry 4.5 three pointers`
> `@PropBot Jokic under 11.5 rebounds`
> `@PropBot Jaylen Brown 20.5 points over or under?`
> `@PropBot Is Luka over 8.5 assists worth it?`

**Stats:** points · rebounds · assists · 3PM · steals · blocks · PRA · P+A · P+R

⚠️ For entertainment only. Not financial advice.
""".strip()


# ── Discord events ────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅ {bot.user} is live!")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="NBA props 🏀"
        )
    )


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if bot.user not in message.mentions:
        return

    content = re.sub(r"<@!?\d+>", "", message.content).strip()

    if not content or content.lower() in ("help", "?", "commands"):
        await message.reply(HELP_TEXT)
        return

    async with message.channel.typing():

        # Parse the prop
        prop = parse_prop_request(content)
        if not prop:
            await message.reply(
                "❌ Couldn't parse that prop. Try:\n"
                "> `@PropBot LeBron James over 25.5 points`"
            )
            return

        player = prop["player"]
        stat   = prop["stat"]
        line   = prop["line"]

        # Thinking message
        thinking = await message.reply(
            f"🔍 Analyzing **{player}** — {stat} O/U **{line}**...\n"
            "_Checking last 10 games, H2H, injury status..._"
        )

        # Run analysis
        try:
            data = analyze_prop(player, stat, line)

            if not data or not data.get("player_name"):
                await thinking.edit(
                    content=f"❌ Couldn't generate analysis for **{player}**. Try rephrasing or check the name."
                )
                return

            embed = build_embed(data, line)
            await thinking.edit(content="", embed=embed)

        except urllib.error.HTTPError as e:
            body = e.read().decode()
            await thinking.edit(content=f"❌ Groq API error {e.code}: {body[:200]}")
        except Exception as e:
            await thinking.edit(content=f"❌ Error: {str(e)[:200]}")


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
