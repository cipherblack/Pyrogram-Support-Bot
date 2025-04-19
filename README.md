# Telegram Bot

A feature-rich Telegram bot built with Python and Pyrogram, designed to handle user registrations, content submissions, support messages, and admin functionalities. The bot interacts with a SQLite database to store user data, submissions, and support messages, and provides an admin panel for managing users and content.

## Table of Contents
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Database Schema](#database-schema)
- [Logging](#logging)
- [Contributing](#contributing)
- [License](#license)

## Features
- **User Registration**: Allows users to register with their personal information (name, card number, SHEBA number).
- **Content Submission**: Users can submit text or photo content, which is reviewed by the admin.
- **Support System**: Users can send support messages, and admins can reply to them.
- **Admin Panel**: Admins can:
  - View registered users.
  - Approve or reject submitted content.
  - Manage user balances.
  - Toggle bot status (online/offline).
  - View and respond to support messages.
- **Database Integration**: Uses SQLite for persistent storage of users, submissions, and support messages.
- **Thread-Safe State Management**: Ensures reliable handling of user states with thread-safe operations.
- **Error Handling and Logging**: Comprehensive error handling and logging for debugging and monitoring.

## Prerequisites
- Python 3.8 or higher
- Telegram Bot Token (obtained from [BotFather](https://t.me/BotFather))
- Pyrogram library
- SQLite (included with Python)

## Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/cipherblack/Pyrogram-Support-Bot.git
   cd telegram-bot
   ```

2. Create a virtual environment and activate it:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration
1. Obtain your Telegram API credentials:
   - Create a Telegram app at [my.telegram.org](https://my.telegram.org) to get `API_ID` and `API_HASH`.
   - Get a `BOT_TOKEN` from [BotFather](https://t.me/BotFather).

2. Update the bot configuration in the main script (e.g., `bot.py`):
   ```python
   API_ID = your_api_id
   API_HASH = "your_api_hash"
   BOT_TOKEN = "your_bot_token"
   ADMIN_ID = your_admin_user_id
   ```

3. Initialize the SQLite database:
   - The bot automatically creates the database (`bot_db.db`) and required tables on first run.

## Usage
1. Run the bot:
   ```bash
   python bot.py
   ```

2. Interact with the bot via Telegram:
   - Send `/start` to begin and register as a user.
   - Use the inline keyboard to navigate through features (submit content, check balance, contact support).
   - Admins can use `/admin` to access the admin panel.

3. Monitor logs:
   - Logs are saved to `bot.log` and printed to the console for debugging.

## Database Schema
The bot uses a SQLite database (`bot_db.db`) with the following tables:

- **users**:
  - `user_id` (INTEGER, PRIMARY KEY): Unique user ID.
  - `first_name` (TEXT): User's first name.
  - `last_name` (TEXT): User's last name.
  - `card_number` (TEXT): User's card number.
  - `sheba_number` (TEXT): User's SHEBA number.
  - `balance` (REAL): User's balance (default 0).
  - `approved_numbers` (INTEGER): Number of approved submissions (default 0).
  - `registered_at` (TEXT): Registration timestamp.

- **submissions**:
  - `id` (INTEGER, PRIMARY KEY, AUTOINCREMENT): Submission ID.
  - `user_id` (INTEGER): Foreign key referencing `users(user_id)`.
  - `content` (TEXT): Submitted content (text or photo file ID).
  - `content_type` (TEXT): Type of content ("text" or "photo").
  - `status` (TEXT): Submission status ("pending", "approved", "rejected").
  - `submitted_at` (TEXT): Submission timestamp.

- **support_messages**:
  - `id` (INTEGER, PRIMARY KEY, AUTOINCREMENT): Message ID.
  - `user_id` (INTEGER): Foreign key referencing `users(user_id)`.
  - `message` (TEXT): Support message content.
  - `direction` (TEXT): Message direction ("user_to_admin" or "admin_to_user").
  - `created_at` (TEXT): Message timestamp.

- **bot_status**:
  - `id` (INTEGER, PRIMARY KEY): Fixed to 1.
  - `is_active` (BOOLEAN): Bot online/offline status (default 1).

## Logging
- Logs are configured to output to both `bot.log` and the console.
- Log levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`.
- Each operation (e.g., content submission, support message, database error) is logged with relevant details.

## Contributing
Contributions are welcome! To contribute:
1. Fork the repository.
2. Create a new branch (`git checkout -b feature/your-feature`).
3. Make your changes and commit (`git commit -m "Add your feature"`).
4. Push to the branch (`git push origin feature/your-feature`).
5. Open a Pull Request.

Please ensure your code follows PEP 8 style guidelines and includes appropriate logging.

## License
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.