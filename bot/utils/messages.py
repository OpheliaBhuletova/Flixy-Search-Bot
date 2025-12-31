class Texts:
    """
    Centralized user-facing text messages for Flixy Search Bot.
    """

    # ───────────────────────────────────
    # START / HELP / ABOUT
    # ───────────────────────────────────

    START_TXT = """
👋 Hey {},  
Welcome to **{}** — your smart movie search companion!

🎬 Just **type any movie name** and I’ll find it for you instantly.  
Sit back, relax, and enjoy unlimited entertainment 🍿✨
"""

    HELP_TXT = """
🛠 **Help Menu**

I can help you search movies, manage filters, connect chats, and more.  
Choose a category below to explore available commands 👇
"""

    ABOUT_TXT = """
📌 **Bot Information**

**🤖 Name:** {}  
**👨‍💻 Developer:** <a href="https://t.me/PopzyBots">Popzy Bots</a>  
**📚 Framework:** Pyrogram  
**🐍 Language:** Python 3.11+  
**🗄 Database:** MongoDB  
**🌐 Hosting:** Koyeb  
**🔖 Version:** v1.0 • Modernized  

Built for speed, stability, and smooth movie searching 🚀
"""

    SOURCE_TXT = """
📦 **Open Source**

Flixy Search Bot is an open-source project.

🔗 **Source Code:**  
https://github.com/PopzyBots/Flixy-Search-Bot

Contributions, issues, and forks are welcome 💡
"""

    # ───────────────────────────────────
    # FILTERS
    # ───────────────────────────────────

    MANUELFILTER_TXT = """
🎛 **Manual Filters — Guide**

Filters allow the bot to automatically reply when a keyword is detected.

🔔 **Important**
1. The bot must be **admin** in the chat  
2. Only **admins** can create filters  
3. Alert buttons support up to **64 characters**

📝 **Commands**
• `/filter` — add a new filter  
• `/filters` — list active filters  
• `/del` — delete a filter  
• `/delall` — delete all filters (owner only)
"""

    # ───────────────────────────────────
    # BUTTONS
    # ───────────────────────────────────

    BUTTON_TXT = """
🔘 **Inline Buttons — Guide**

The bot supports **URL buttons** and **Alert buttons**.

⚠️ **Notes**
1. Messages cannot contain buttons alone  
2. Buttons work with all media types  
3. Follow correct Markdown syntax

🔗 **URL Button**
`[Text](buttonurl:https://t.me/PopzyBots)`

⚠️ **Alert Button**
`[Text](buttonalert:This is an alert message)`
"""

    # ───────────────────────────────────
    # AUTO FILTER
    # ───────────────────────────────────

    AUTOFILTER_TXT = """
🤖 **Auto Filter — Overview**

Auto Filter automatically indexes files from a channel into the database.

📌 **Requirements**
1. Make me **admin** in your channel (private channels included)  
2. Channel must not contain:
   • camrips  
   • adult content  
   • fake or broken files  
3. Forward the **last message** from the channel **with quotes**

I’ll take care of indexing automatically 🗂
"""

    # ───────────────────────────────────
    # CONNECTIONS
    # ───────────────────────────────────

    CONNECTION_TXT = """
🔗 **Connections — Guide**

Connections let you manage filters in private chat  
without cluttering the group.

📌 **Notes**
1. Only admins can create connections  
2. Use `/connect` inside a group

📝 **Commands**
• `/connect` — connect a group  
• `/disconnect` — disconnect a chat  
• `/connections` — list your connections
"""

    # ───────────────────────────────────
    # EXTRA MODULES
    # ───────────────────────────────────

    EXTRAMOD_TXT = """
🧰 **Extra Tools**

Helpful commands for information and utilities.

📝 **Commands**
• `/id` — get user ID  
• `/info` — detailed user information  
• `/imdb` — fetch IMDb movie details  
• `/search` — search movies manually
"""

    # ───────────────────────────────────
    # ADMIN MODULES
    # ───────────────────────────────────

    ADMIN_TXT = """
🔐 **Admin Controls**

Restricted commands for bot administrators.

📝 **Commands**
• `/logs` — view recent error logs  
• `/stats` — database statistics  
• `/delete` — remove a file from database  
• `/users` — list bot users  
• `/chats` — list connected chats  
• `/leave` — leave a chat  
• `/disable` — disable a chat  
• `/ban` — ban a user  
• `/unban` — unban a user  
• `/channel` — list connected channels  
• `/broadcast` — broadcast a message
"""

    # ───────────────────────────────────
    # STATUS / LOGS
    # ───────────────────────────────────

    STATUS_TXT = """
📊 **Bot Status**

• **Total Files:** `{}`  
• **Total Users:** `{}`  
• **Total Chats:** `{}`  
• **Used Storage:** `{}`  
• **Free Storage:** `{}`  
"""

    LOG_TEXT_G = """
🆕 **New Group Connected**

🏷 **Group:** {} (`{}`)  
👥 **Members:** `{}`  
➕ **Added By:** {}
"""

    LOG_TEXT_P = """
🆕 **New User Started Bot**

🆔 **User ID:** `{}`  
👤 **Name:** {}
"""