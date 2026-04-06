# Emoji Combiner Bot

A lightweight Discord bot that combines 2 emojis into a single image using Google Emoji Kitchen–style assets.

<img width="1000" height="1000" alt="Response from Discord Bot when running command" src="https://github.com/user-attachments/assets/ac348b94-1b09-4b00-9771-0c1c5498a793" />

## Setup

### Create Discord Application
#### Create Bot
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click New Application
3. Go to Bot → Add Bot
#### Enable Required Settings
In Bot → Privileged Gateway Intents enable `Message Content Intent`
#### Copy Token
1. Go to Bot → Reset Token
2. Copy it
#### Invite Bot
1. Go to OAuth2 → URL Generator
2. Select `bot` and `applications.commands`
3. Apply the permissions `Send Messages`, `Attach Files` and `Read Message History`
4. Open generated URL and invite bot

### Docker Installation
1. Clone repo: `git clone https://github.com/AdrianOsborne/Combine-Emoji-Discord-Bot.git`
2. Clone `.env` with:
```
cp .env.example .env
```
2. Paste `DISCORD_BOT_TOKEN` & `DISCORD_APPLICATION_ID` into `.env`
3. Run:
```
docker compose up -d --build
```

## Usage
### /emoji Command
Use the following command with two emojis:
```
/emoji emoji1:💔 emoji2:😭
```
The bot will respond privately in the server with the combined emoji for you to copy and paste.
### @ Mention
Mention the bot and write two emojis:
```
@BOTNAME 💔😭
```
The bot will respond in DMs with the combined emoji for you to copy and paste.
### DM Bot
Message two emojis to the bot in DMs:
```
💔😭
```
The bot will respond in DMs with the combined emoji for you to copy and paste.

## Donations
If you like this project and would like to support my work, please consider donating.

### PayPal
[PayPal Donation](https://paypal.me/adrianbosborne)

### Bitcoin
`bc1qhq2l6nz8qlgfhzhtdc36hr3mtcya5wx8j0meauuevyadzj3dqr9qz33l7t`
