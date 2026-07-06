<p align="center">
  <img src="static/images/popzybots.png" alt="Popzy Bots" width="100">
</p>

<h1>Flixy Search Bot</h1>

<p>
  A modern, fast, and fully backward-compatible Telegram file search bot
  built with the latest Pyrogram and Python.
</p>

---

## 📌 About

**Flixy Search Bot** is a Telegram file search bot that helps users find and retrieve indexed files directly from Telegram using inline search, private message search, and admin tools.

This project is a **modernized continuation** of the original search bot, upgraded to:
- **Pyrogram v2 (async-first)**
- **Python 3.11+**
- **Async MongoDB (Motor)**
- Clear modular plugin structure for easier maintenance and extension

This version adds dedicated support for separate movie and series workflows while preserving the original user experience.

---

## ✨ Core Features

- 🎬 **Inline search for movies** using a dedicated inline movie database
- 📺 **Private message search for TV series** with a separate PM/series database
- 📌 **Dedicated movies and series channels** via `MOVIES_CHANNELS` and `SERIES_CHANNELS`
- 🧠 **TV series watchlist support** — users can add series and receive new episode notifications
- 🔍 **TMDb metadata search** through `/imdb` and `/imdbinfo`
- 🧩 **Plugin-based architecture** for clean separation of features
- 🛡 **Admin controls** for indexing, deleting, and database management
- ✅ **Persistent MongoDB storage** with async access via Motor
- 🚀 **Docker-friendly deployment** with modern production readiness

---

## 🔁 Inline vs PM Search

- **Inline search** is primarily used for **movies** and searches the `inline` movie database.
- **Private chat search** is used for **series** and searches the `pm` series database.
- PM search is available to all users, so anyone can search series in a private chat.
- This dual-database setup keeps movie and TV series search results separated and optimized for each use case.

---

## 🛠 Access Levels

- **Admin users** — full bot access, including PM/series replies, indexing, filter management, and admin-only commands.
- **Sudo users** — inline search, private search access, and bypass bans/subscription checks.
- **Normal users** — unrestricted inline movie search, private search access in PM, and access to public help text.

---

## 🤖 Key Commands

### General Commands
- `/start` — Start the bot and see the welcome message
- `/help` — Open the interactive help menu
- `/search <query>` — Search files by name
- `/ping` — Check bot availability

### Metadata and Discovery
- `/imdb <query>` — Search TMDb for movies or TV shows
- `/imdbinfo <query|tmdb_id>` — Fetch TMDb metadata by name or ID

### Watchlist and Series
- `/addwatchlist <TV series name>` — Add a TV series to your watchlist
- `/mywatchlist` — View your saved TV series
- Watchlist notifications are triggered when new episodes are indexed

### Group and Filter Management
- `/connect <group_id>` — Link a group to your PM session
- `/disconnect` — Unlink a connected group
- `/connections` — List connected groups
- `/filter <keyword>` — Save a filter in a connected group
- `/filters` or `/viewfilters` — List active filters
- `/delete <keyword>` or `/del <keyword>` — Remove a filter
- `/delall` — Remove all filters from a group

### Admin Tools
- `/genid` — Extract a file ID from replied media
- `/delete <file_id>` — Delete a file from the database
- `/setstartup` — Set the bot startup image from a photo
- `/recentfiles [movies|series|both] [limit]` — Show recently indexed files
- `/dbstats` — Show movies and series database statistics

---

## 🧠 Technical Notes

- The bot uses two separate MongoDB clusters for movie and PM search data when configured with `DATABASE_URL_INLINE` and `DATABASE_URL_PM`.
- `MOVIES_CHANNELS` are saved to the inline movie database.
- `SERIES_CHANNELS` are saved to the PM/series database.
- PM file deliveries are sent as cached media and include an automated cleanup reminder.

---

## 🛠 Tech Stack

- **Language:** Python 3.11+
- **Framework:** Pyrogram v2
- **Database:** MongoDB (Motor – async)
- **Deployment:** Docker / Koyeb / VPS / Cloud platforms

---

## 📄 License

This project is open-source and available under the MIT License.

---

<p align="center">
  Made with ❤️ by <b>Flixy Bots</b>
</p>
