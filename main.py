
import discord
from discord.ext import commands, tasks
import time
import os

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

TOKEN = os.getenv("DISCORD_TOKEN")
PANEL_CHANNEL_ID = int(os.getenv("PANEL_CHANNEL_ID"))
LEADERBOARD_CHANNEL_ID = int(os.getenv("LEADERBOARD_CHANNEL_ID"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID"))

user_sessions = {}
leaderboard_message = None
status_message = None

def format_time(seconds):
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"

class PlaytimeButtons(discord.ui.View):
    @discord.ui.button(label="🟢 Online", style=discord.ButtonStyle.success)
    async def go_online(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        now = time.time()
        session = user_sessions.setdefault(uid, {"online_total": 0, "afk_total": 0, "status": "offline"})
        if session["status"] == "afk":
            session["afk_total"] += now - session["afk_start"]
        if session["status"] != "online":
            session["online_start"] = now
        session["status"] = "online"
        await interaction.response.send_message("Status set to 🟢 Online.", ephemeral=True)

    @discord.ui.button(label="🌙 AFK", style=discord.ButtonStyle.secondary)
    async def go_afk(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        now = time.time()
        session = user_sessions.setdefault(uid, {"online_total": 0, "afk_total": 0, "status": "offline"})
        if session["status"] == "online":
            session["online_total"] += now - session["online_start"]
        if session["status"] != "afk":
            session["afk_start"] = now
        session["status"] = "afk"
        await interaction.response.send_message("Status set to 🌙 AFK.", ephemeral=True)

    @discord.ui.button(label="🔁 Back from AFK", style=discord.ButtonStyle.primary)
    async def back_from_afk(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        now = time.time()
        session = user_sessions.setdefault(uid, {"online_total": 0, "afk_total": 0, "status": "offline"})
        if session["status"] == "afk":
            session["afk_total"] += now - session["afk_start"]
        session["online_start"] = now
        session["status"] = "online"
        await interaction.response.send_message("Returned from AFK. Status set to 🟢 Online.", ephemeral=True)

    @discord.ui.button(label="🔴 Offline", style=discord.ButtonStyle.danger)
    async def go_offline(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        now = time.time()
        session = user_sessions.setdefault(uid, {"online_total": 0, "afk_total": 0, "status": "offline"})
        if session["status"] == "online":
            session["online_total"] += now - session["online_start"]
        elif session["status"] == "afk":
            session["afk_total"] += now - session["afk_start"]
        session["status"] = "offline"
        await interaction.response.send_message("Status set to 🔴 Offline.", ephemeral=True)

@tasks.loop(seconds=30)
async def update_leaderboard():
    if not leaderboard_message or not status_message:
        return

    leaderboard_lines = ["**__Leaderboard__**"]
    status_lines = ["**__Live Status__**"]
    sorted_users = sorted(user_sessions.items(), key=lambda x: x[1]["online_total"], reverse=True)

    for i, (uid, session) in enumerate(sorted_users, start=1):
        online = session["online_total"]
        afk = session["afk_total"]
        if session["status"] == "online":
            online += time.time() - session["online_start"]
        elif session["status"] == "afk":
            afk += time.time() - session["afk_start"]

        name = f"<@{uid}>"
        leaderboard_lines.append(f"{i}. **{name}** — Online: `{format_time(online)}`, AFK: `{format_time(afk)}`")

        if session["status"] == "online":
            icon = "🟢"
        elif session["status"] == "afk":
            icon = "🌙"
        else:
            icon = "🔴"
        status_lines.append(f"{icon} {name}")

    leaderboard_text = "
".join(leaderboard_lines)
    status_text = "
".join(status_lines)

    await leaderboard_message.edit(content=leaderboard_text)
    await status_message.edit(content=status_text)

@bot.event
async def on_ready():
    global leaderboard_message, status_message
    panel_channel = bot.get_channel(PANEL_CHANNEL_ID)
    leaderboard_channel = bot.get_channel(LEADERBOARD_CHANNEL_ID)
    if panel_channel:
        await panel_channel.purge(limit=5)
        await panel_channel.send("**__Playtime Tracker__**
Click your current status:", view=PlaytimeButtons())
    if leaderboard_channel:
        leaderboard_message = await leaderboard_channel.send("📊 Loading leaderboard...")
        status_message = await leaderboard_channel.send("🟢 Loading live status...")
    update_leaderboard.start()

bot.run(TOKEN)
