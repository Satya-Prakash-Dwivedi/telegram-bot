# 💬 Telegram UPI Payment Bot

A simple Telegram bot built with **Python** and **python-telegram-bot** that helps users make payments via UPI and allows the admin to manually verify them.

---

## 🚀 Features
- `/start` — Welcomes the user and explains how to begin.  
- `/pay` — Shows UPI payment details (UPI ID + amount).  
- Users upload payment screenshots after completing payment.  
- Bot automatically forwards the payment proof to a private **admin channel**.  
- Admin can view each payment screenshot and (optionally) approve or reject manually.

---

## 🧩 How It Works
1. **User Flow**
   - User opens the bot → sees prompt to type `/start`.
   - `/start` → shows welcome message.
   - `/pay` → shows UPI payment details (ID + amount).
   - User pays manually and uploads a screenshot.
   - Bot sends that screenshot to the admin channel for verification.

2. **Admin Flow**
   - Admin receives screenshot in a private channel.
   - Admin checks the payment in their UPI app and confirms manually.

---

## ⚙️ Setup Instructions

### 1. Create a Telegram Bot
- Talk to **[@BotFather](https://t.me/BotFather)** on Telegram.  
- Use `/newbot` to create one and get your **Bot Token**.

### 2. Create a Private Channel
- Add your bot as an **admin** in that channel.  
- Get the channel ID:
  1. Send a test message in the channel.
  2. Visit:  
     ```
     https://api.telegram.org/bot<BOT_TOKEN>/getUpdates
     ```
  3. Look for `"chat": { "id": ... }`.

### 3. Get Your Admin User ID
- Send a message to your bot.
- Visit the same `/getUpdates` URL.
- Find your `"from": { "id": ... }`.

### 4. Create a `.env` file
```env
BOT_TOKEN=your_bot_token_here
UPI_ID=your_upi_id_here
PAYEE_NAME=your_name_here
AMOUNT=amount
ADMIN_CHAT_ID=your_admin_user_id
CHANNEL_ID=your_admin_channel_id
