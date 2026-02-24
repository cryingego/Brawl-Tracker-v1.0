# Brawl Tracker v1.0
**Brawl Tracker is a Telegram bot written in Python that allows you to conveniently track player statistics and activity.**

*What can the bot do?*

1. **Easy initial tracking of a player by their profile tag (#0X0X0X0X)**

The first button in the menu, "Add by Tag," asks you for a tag (without the hash mark). After that, you'll finally be asked whether a player with that tag actually exists. If so, you add it to the database; if not, it doesn't include the tag.

2. **Storing previously added profiles in a separate list (as a data source)**

The second button in the main menu, "My List." As mentioned earlier, profile tags are clickable. Click on one to display its statistics.

3. **Notifications about recently played matches (interval - 1 minute)**

Every minute, the activity of previously created profiles will be monitored and notifications about recently created matches will be sent to you. Important: each tag for a data collection cycle can only appear in up to 2 batches, with a maximum of 5 tags per cycle. The third button in the main menu allows you to turn notifications on/off.

4. **Current Statistics**

As mentioned earlier, each tag in the list is clickable. Clicking on it will display your current account statistics, namely:

- Nickname + (#tag)
- Cups + (Maximum number)
- Win rate for the last 25 games
- Number of wins (3v3, duet, solo)
- Mode of last match + (how long ago)
- Club

There will also be four buttons below the statistics:

- View battle log
- Refresh
- Delete
- Back to list

The battle save log shows the last 10 matches played. Each of these will have a separate button that allows you to view match details (mode, how long ago each was played, what group they were in, and the nicknames of these players + the brawlers they were in).

The "Refresh" button sends a request to the bot, after which it updates the latest profile changes via the Brawl Stars API. If the changes were in Advanced mode, the bot returns the latest statistics; if not, it returns the same low-level ones.

The "Delete" button selects a profile tag from the list of tracked objects, which can be added again.

*All of this is supported by a user-friendly and eye-pleasing design*

#HOW TO LAUNCH A BOT?
**You'll only need a few steps:**
1. Create a new project and upload two files: "main.py" and "database.py"
2. First, create a bot in Telegram using @BotFather. Then, we'll provide our bot's token, which we'll paste into the code instead of "PUT UR BOT TOKEN HERE" (file main.py).
3. Next, register on the [Brawl Stars API](https://developer.brawlstars.com/#/), create a key in your account, record all your data, copy the key we issued, and replace it with the code "BSAPI TOKEN" (file main.py).
4. Download the required libraries via the terminal: (`pip install aiogram aiohttp apscheduler brawlstats`)
5. Run the bot via the terminal: (`python main.py`)
6. Type /start in the bot and run it. The bot will run until you close the terminal.

#IMPORTANT!
When using the bot simultaneously by multiple users, errors may occur using the specific protocol; for example, the bot is calculated based on a single use.

*use<3*
