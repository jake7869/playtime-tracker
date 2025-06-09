
import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import time
from datetime import timedelta
import re

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

PANEL_CHANNEL_ID = int(os.getenv("PANEL_CHANNEL_ID", "1381017996524257442"))
LEADERBOARD_CHANNEL_ID = int(os.getenv("LEADERBOARD_CHANNEL_ID", "1379861500877078721"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "1381056616362803330"))
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", "1379861837075452035"))

user_sessions = {}
leaderboard_message = None
status_message = None
log_channel = None

def format_time(seconds):
    return str(timedelta(seconds=int(seconds)))

def parse_duration(duration_str):
    match = re.fullmatch(r"(\d+)([smh])", duration_str.strip().lower())
    if not match:
        return None
    value, unit = int(match[1]), match[2]
    return value * {"s": 1, "m": 60, "h": 3600}[unit]

async def log_to_discord(message):
    print("[LOG]", message)
    if log_channel:
        await log_channel.send(message)

class PlaytimeButtons(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🟢 Online", style=discord.ButtonStyle.success, custom_id="online")
    async def go_online(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        session = user_sessions.setdefault(uid, {"status": "offline", "online_total": 0, "afk_total": 0, "online_start": None, "afk_start": None})
        if session["status"] == "online":
            await interaction.response.send_message("You're already online.", ephemeral=True)
            return
        if session["status"] == "afk":
            session["afk_total"] += time.time() - session["afk_start"]
        session["online_start"] = time.time()
        session["status"] = "online"
        await interaction.response.send_message("You're now marked as online.", ephemeral=True)
        await log_to_discord(f"🟢 {interaction.user.display_name} is now ONLINE.")

    @discord.ui.button(label="🟡 AFK", style=discord.ButtonStyle.secondary, custom_id="afk")
    async def go_afk(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        session = user_sessions.get(uid)
        if not session or session["status"] != "online":
            await interaction.response.send_message("You must be online to go AFK.", ephemeral=True)
            return
        session["online_total"] += time.time() - session["online_start"]
        session["afk_start"] = time.time()
        session["status"] = "afk"
        await interaction.response.send_message("You're now AFK.", ephemeral=True)
        await log_to_discord(f"🟡 {interaction.user.display_name} is now AFK.")

    @discord.ui.button(label="🔁 Back from AFK", style=discord.ButtonStyle.primary, custom_id="back_from_afk")
    async def back_from_afk(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        session = user_sessions.get(uid)
        if not session or session["status"] != "afk":
            await interaction.response.send_message("You must be AFK to come back.", ephemeral=True)
            return
        session["afk_total"] += time.time() - session["afk_start"]
        session["online_start"] = time.time()
        session["status"] = "online"
        await interaction.response.send_message("You're now back from AFK.", ephemeral=True)
        await log_to_discord(f"🔁 {interaction.user.display_name} is back from AFK.")

    @discord.ui.button(label="🔴 Offline", style=discord.ButtonStyle.danger, custom_id="offline")
    async def go_offline(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        session = user_sessions.get(uid)
        if not session or session["status"] not in ["online", "afk"]:
            await interaction.response.send_message("You're already offline.", ephemeral=True)
            return
        now = time.time()
        if session["status"] == "online":
            session["online_total"] += now - session["online_start"]
        elif session["status"] == "afk":
            session["afk_total"] += now - session["afk_start"]
        session["status"] = "offline"
        session["online_start"] = None
        session["afk_start"] = None
        await interaction.response.send_message("You're now offline.", ephemeral=True)
        await log_to_discord(f"🔴 {interaction.user.display_name} is now OFFLINE.")

@bot.event
async def on_ready():
    global log_channel, leaderboard_message, status_message
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    guild = bot.guilds[0]
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    panel_channel = bot.get_channel(PANEL_CHANNEL_ID)
    leaderboard_channel = bot.get_channel(LEADERBOARD_CHANNEL_ID)

    await bot.tree.sync()

    if panel_channel:
        await panel_channel.purge(limit=5)
      await panel_channel.send("**Playtime Tracker**\\nClick your current status:", view=PlaytimeButtons())
Click your current status:", view=PlaytimeButtons())
    if leaderboard_channel:
        leaderboard_message = await leaderboard_channel.send("📊 Loading leaderboard...")
        status_message = await leaderboard_channel.send("🟢 Loading live status...")

    update_leaderboard.start()

@tasks.loop(seconds=30)
async def update_leaderboard():
    if not leaderboard_message or not status_message:
        return

    leaderboard_lines = []
    status_lines = ["**Live Status:**"]
    sorted_users = sorted(user_sessions.items(), key=lambda x: x[1]["online_total"], reverse=True)
    for uid, session in sorted_users:
        online = session["online_total"]
        afk = session["afk_total"]
        if session["status"] == "online":
            online += time.time() - session["online_start"]
        elif session["status"] == "afk":
            afk += time.time() - session["afk_start"]
        name = get_user_display(uid, leaderboard_message.guild)
        leaderboard_lines.append(f"**{name}** — Online: `{format_time(online)}`, AFK: `{format_time(afk)}`")
        status_lines.append(f"{name} → `{session['status'].upper()}`")

    await leaderboard_message.edit(content="**__Leaderboard__**
" + "\n".join(leaderboard_lines))
    await status_message.edit(content="\n".join(status_lines))

# Admin commands like /add_time, /set_afk, etc. can be added here...

print("🚀 Starting bot...")
bot.run(os.getenv("DISCORD_TOKEN"))
