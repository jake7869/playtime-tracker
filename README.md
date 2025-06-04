# Discord Playtime Tracker Bot

Tracks online/AFK playtime with buttons and shows a live leaderboard.

### Features
- Online, AFK, Back from AFK, and Offline buttons
- Live leaderboard
- Admin-only reset button
- No persistent storage (resets on bot restart)

### Railway Setup
1. Add environment variable: `DISCORD_TOKEN` with your bot's token.
2. Deploy the project.
3. Ensure required intents (Server Members, Message Content) are enabled on the Discord Dev Portal.

### File Summary
- `main.py` – Main bot logic
- `requirements.txt` – Dependencies
- `README.md` – Info