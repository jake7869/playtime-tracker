import discord
from discord.ext import commands, tasks
from discord import app_commands
import time
from datetime import timedelta
import os
import re

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

PANEL_CHANNEL_ID = int(os.getenv("PANEL_CHANNEL_ID", "1381017996524257442"))
LEADERBOARD_CHANNEL_ID = int(os.getenv("LEADERBOARD_CHANNEL_ID", "1379861500877078721"))
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", "1379861837075452035"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "1381056616362803330"))

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

def get_user_display(user_id, guild):
    member = guild.get_member(user_id)
    return member.display_name if member else f"<@{user_id}>"

class PlaytimeButtons(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🟢 Online", style=discord.ButtonStyle.success, custom_id="online")
    async def go_online(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        session = user_sessions.setdefault(uid, {"status": "offline", "online_total": 0, "afk_total": 0, "online_start": None, "afk_start": None})
        await log_to_discord(f"🟢 **{interaction.user.display_name}** is now ONLINE.")

        if session["status"] == "online":
            await interaction.response.send_message("You're already online.", ephemeral=True)
            return
        if session["status"] == "afk":
            session["afk_total"] += time.time() - session["afk_start"]

        session["online_start"] = time.time()
        session["status"] = "online"
        await interaction.response.send_message("You're now marked as online.", ephemeral=True)

    @discord.ui.button(label="🟡 AFK", style=discord.ButtonStyle.secondary, custom_id="afk")
    async def go_afk(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        session = user_sessions.get(uid)
        await log_to_discord(f"🟡 **{interaction.user.display_name}** is now AFK.")

        if not session or session["status"] != "online":
            await interaction.response.send_message("You must be online to go AFK.", ephemeral=True)
            return

        session["online_total"] += time.time() - session["online_start"]
        session["afk_start"] = time.time()
        session["status"] = "afk"
        await interaction.response.send_message("You're now AFK.", ephemeral=True)

    @discord.ui.button(label="🔁 Back from AFK", style=discord.ButtonStyle.primary, custom_id="back_from_afk")
    async def back_from_afk(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        session = user_sessions.get(uid)
        await log_to_discord(f"🔁 **{interaction.user.display_name}** is back from AFK.")

        if not session or session["status"] != "afk":
            await interaction.response.send_message("You must be AFK to come back.", ephemeral=True)
            return

        session["afk_total"] += time.time() - session["afk_start"]
        session["online_start"] = time.time()
        session["status"] = "online"
        await interaction.response.send_message("You're back from AFK and now online.", ephemeral=True)

    @discord.ui.button(label="🔴 Offline", style=discord.ButtonStyle.danger, custom_id="offline")
    async def go_offline(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        session = user_sessions.get(uid)
        await log_to_discord(f"🔴 **{interaction.user.display_name}** is now OFFLINE.")

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

@bot.tree.command(name="remove_time", description="Remove online time from a user (admin only).")
@app_commands.describe(user="User to remove time from", amount="Amount (10s, 5m, 2h)")
async def remove_time(interaction: discord.Interaction, user: discord.Member, amount: str):
    if ADMIN_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    seconds = parse_duration(amount)
    if seconds is None:
        await interaction.response.send_message("Invalid format. Use 10s, 5m, or 2h.", ephemeral=True)
        return

    session = user_sessions.setdefault(user.id, {"status": "offline", "online_total": 0, "afk_total": 0, "online_start": None, "afk_start": None})
    session["online_total"] = max(0, session["online_total"] - seconds)

    await log_to_discord(f"🧮 **{interaction.user.display_name}** removed {format_time(seconds)} from **{user.display_name}**.")
    await interaction.response.send_message(f"Removed {format_time(seconds)} from {user.mention}'s online time.")

@bot.tree.command(name="reset_leaderboard", description="Reset all playtime data (admin only).")
async def reset_leaderboard(interaction: discord.Interaction):
    if ADMIN_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You don't have permission to reset.", ephemeral=True)
        return
    user_sessions.clear()
    await log_to_discord(f"🧨 **{interaction.user.display_name}** reset the entire leaderboard.")
    await interaction.response.send_message("Leaderboard has been reset.")
    await update_leaderboard()
    await update_status_tracker()

async def update_status_tracker():
    global status_message
    channel = bot.get_channel(LEADERBOARD_CHANNEL_ID)
    if not channel:
        return

    online, afk, offline = [], [], []
    for uid, data in user_sessions.items():
        user = get_user_display(uid, channel.guild)
        if data["status"] == "online":
            online.append(user)
        elif data["status"] == "afk":
            afk.append(user)
        else:
            offline.append(user)

    text = "__**Live Status Tracker**__\n"
    text += f"🟢 **Online:** {', '.join(online) if online else 'None'}\n"
    text += f"🟡 **AFK:** {', '.join(afk) if afk else 'None'}\n"
    text += f"🔴 **Offline:** {', '.join(offline) if offline else 'None'}"

    if status_message:
        await status_message.edit(content=text)
    else:
        status_message = await channel.send(text)

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

        name = get_user_display(uid, channel.guild)
        lines.append(f"**{name}** - 🟢 {format_time(online)} | 🟡 {format_time(afk)}")

    text = "__**Leaderboard**__\n" + ("\n".join(lines) if lines else "*No activity yet.*")
    if leaderboard_message:
        await leaderboard_message.edit(content=text)
    else:
        leaderboard_message = await channel.send(text)

    await update_status_tracker()

@bot.event
async def on_ready():
    global log_channel
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    panel_channel = bot.get_channel(PANEL_CHANNEL_ID)
    log_channel = bot.get_channel(LOG_CHANNEL_ID)

    if panel_channel:
        await panel_channel.purge(limit=10)
        await panel_channel.send("**Playtime Tracker**\nClick your current status:", view=PlaytimeButtons())

    await bot.tree.sync()
    update_leaderboard.start()

bot.run(os.getenv("DISCORD_TOKEN"))
