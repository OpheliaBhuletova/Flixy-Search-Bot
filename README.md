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

**Flixy Search Bot** is a Telegram file search bot that helps users quickly find and retrieve indexed files directly from Telegram using simple commands.

This project is a **modernized continuation** of the original search bot, upgraded to:
- **Pyrogram v2 (async-first)**
- **Python 3.11+**
- **Async MongoDB (Motor)**
- Cleaner structure and production-ready infrastructure

All existing commands and user-facing behavior are preserved, ensuring **full backward compatibility** while making the codebase easier to maintain and extend.

---

## ✨ Features

- 🔍 Fast file searching in indexed channels
- 📂 Instant file retrieval via inline and command-based search
- ⚡ Async architecture for better performance
- 🧩 Plugin-based modular structure
- 🛡 Admin-only controls for indexing and maintenance
- 🗃 MongoDB-backed persistent storage
- 🚀 Ready for modern deployment (Docker-friendly)

---

## 🤖 Available Commands

### User Commands
- `/start` – Start the bot and see the welcome message
- `/help` – Get information about how to use the bot (opens an interactive menu with categorized commands)
- `/search <query>` – Search for files by name
- `/ping` – Check if the bot is alive

### Admin Commands
- `/index` – Index files from a channel
- `/stats` – View bot statistics
- `/broadcast` – Send a message to all users
- `/restart` – Restart the bot (if enabled)

> ⚠️ Command names and behavior are kept identical to the original implementation.

---

## 🛠 Tech Stack

- **Language:** Python 3.11+
- **Framework:** Pyrogram v2
- **Database:** MongoDB (Motor – async)
- **Deployment:** Docker / VPS / Cloud platforms

---

## 📄 License

This project is open-source and available under the MIT License.

---

<p align="center">
  Made with ❤️ by <b>Popzy Bots</b>
</p>
