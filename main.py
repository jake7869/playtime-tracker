import discord
from discord.ext import commands, tasks
import time
from datetime import timedelta
import os

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Environment variables
PANEL_CHANNEL_ID = int(os.getenv("PANEL_CHANNEL_ID", "1381017996524257442"))
LEADERBOARD_CHANNEL_ID = int(os.getenv("LEADERBOARD_CHANNEL_ID", "1379861500877078721"))
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", "1379861837075452035"))

user_sessions = {}
leaderboard_message = None

def format_time(seconds):
    return str(timedelta(seconds=int(seconds)))

def get_user_display(user_id, guild):
    member = guild.get_member(user_id)
    return member.display_name if member else f"<@{user_id}>"

class PlaytimeButtons(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🟢 Online", style=discord.ButtonStyle.success, custom_id="online")
    async def go_online(self, button, interaction):
        uid = interaction.user.id
        session = user_sessions.setdefault(uid, {"status": None, "online_total": 0, "afk_total": 0, "online_start": None, "afk_start": None})

        if session["status"] == "online":
            await interaction.response.send_message("You're already online.", ephemeral=True)
            return
        if session["status"] == "afk":
            afk_time = time.time() - session["afk_start"]
            session["afk_total"] += afk_time

        session["online_start"] = time.time()
        session["status"] = "online"
        await interaction.response.send_message("You're now marked as online.", ephemeral=True)

    @discord.ui.button(label="🟡 AFK", style=discord.ButtonStyle.secondary, custom_id="afk")
    async def go_afk(self, button, interaction):
        uid = interaction.user.id
        session = user_sessions.get(uid)

        if not session or session["status"] != "online":
            await interaction.response.send_message("You must be online to go AFK.", ephemeral=True)
            return

        online_time = time.time() - session["online_start"]
        session["online_total"] += online_time
        session["afk_start"] = time.time()
        session["status"] = "afk"
        await interaction.response.send_message("You're now AFK.", ephemeral=True)

    @discord.ui.button(label="🔁 Back from AFK", style=discord.ButtonStyle.primary, custom_id="back_from_afk")
    async def back_from_afk(self, button, interaction):
        uid = interaction.user.id
        session = user_sessions.get(uid)

        if not session or session["status"] != "afk":
            await interaction.response.send_message("You must be AFK to come back.", ephemeral=True)
            return

        afk_time = time.time() - session["afk_start"]
        session["afk_total"] += afk_time
        session["online_start"] = time.time()
        session["status"] = "online"
        await interaction.response.send_message("You're back from AFK and now online.", ephemeral=True)

    @discord.ui.button(label="🔴 Offline", style=discord.ButtonStyle.danger, custom_id="offline")
    async def go_offline(self, button, interaction):
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
        await interaction.response.send_message("You're now offline. Session saved.", ephemeral=True)

    @discord.ui.button(label="♻️ Reset Leaderboard", style=discord.ButtonStyle.danger, custom_id="reset")
    async def reset_leaderboard(self, button, interaction):
        if ADMIN_ROLE_ID not in [role.id for role in interaction.user.roles]:
            await interaction.response.send_message("You don't have permission to reset the leaderboard.", ephemeral=True)
            return

        user_sessions.clear()
        await update_leaderboard()
        await interaction.response.send_message("Leaderboard has been reset.", ephemeral=True)

@tasks.loop(seconds=30)
async def update_leaderboard():
    global leaderboard_message
    channel = bot.get_channel(LEADERBOARD_CHANNEL_ID)
    if not channel:
        return

    lines = []
    sorted_data = sorted(user_sessions.items(), key=lambda x: x[1]["online_total"], reverse=True)

    for uid, data in sorted_data:
        online = data["online_total"]
        afk = data["afk_total"]
        if data["status"] == "online":
            online += time.time() - data["online_start"]
        elif data["status"] == "afk":
            afk += time.time() - data["afk_start"]

        user_display = get_user_display(uid, channel.guild)
        lines.append(f"**{user_display}** - 🟢 {format_time(online)} | 🟡 {format_time(afk)}")

    text = "__**Leaderboard**__\n" + ("\n".join(lines) if lines else "*No activity yet.*")

    if leaderboard_message:
        await leaderboard_message.edit(content=text)
    else:
        leaderboard_message = await channel.send(text)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    panel_channel = bot.get_channel(PANEL_CHANNEL_ID)
    if panel_channel:
        await panel_channel.purge(limit=10)
        await panel_channel.send("**Playtime Tracker**\nClick your current status:", view=PlaytimeButtons())

    update_leaderboard.start()

bot.run(os.getenv("DISCORD_TOKEN"))
