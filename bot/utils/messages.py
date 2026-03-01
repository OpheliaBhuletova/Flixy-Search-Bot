# -*- coding: utf-8 -*-

class Texts:
    """
    Centralized user-facing text messages for Flixy Search Bot.
    """

    # ───────────────────────────────────
    # START / HELP / ABOUT
    # ───────────────────────────────────

    START_TXT = """
👋 Hey {}, I'm <b>F L I X Y</b> — your smart movie search companion!

🎬 <i>Just <b>type any movie name</b> and I'll find it for you instantly.</i> 
"""

    HELP_TXT = """
🛠 **Help Menu**

I can help you search movies, manage filters, connect chats, and more.  
Choose a category below to explore available commands 👇
"""

    # per–category descriptions used by callback handler
    HELP_SEARCH_TXT = """
🔍 **Search & IMDb**

• Type any movie name in any chat using inline mode:
  `@{} <movie name>`

• Private `/search` or `/imdb` requests are available **only to sudo
  users or admins**; normal users should use inline mode instead.
"""

    HELP_FILTERS_TXT = """
🎛 **Filters**

Manage automatic replies when keywords are detected in connected groups.

• `/filter <keyword>` (reply to a message) — save a filter
• `/filters` or `/viewfilters` — list active filters
• `/delete <keyword>` — remove a filter
"""

    HELP_CONNECTIONS_TXT = """
🔗 **Connections**

Link your groups to the bot and control them from PM.

• `/connect <group_id>` — connect a group to your account
• `/disconnect` — unlink the current group
• `/connections` — show all your linked groups
"""

    ABOUT_TXT = """
📌 <b>Bot Information</b>

<b>🤖 Name:</b> {}  
<b>👨‍💻 Developer:</b> <a href="https://t.me/OpheliaBhuletova">Ophelia Bhuletova</a>  
<b>📚 Framework:</b> Pyrogram  
<b>🐍 Language:</b> Python 3.11+  
<b>🗄 Database:</b> MongoDB  
<b>🌐 Hosting:</b> Koyeb  
<b>🔖 Version:</b> V2.1  

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
(Additionally, IDs listed under `SUDO_USERS` are treated as
super‑users and can bypass certain restrictions such as subscription
requirements and bans.)

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
• `/setstartup` — set startup image for /start command  
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