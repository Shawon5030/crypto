import logging
import os
import requests
import yfinance as yf
import pandas as pd
from transformers import pipeline
from dotenv import load_dotenv
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext

# Load environment variables
load_dotenv()

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Initialize Sentiment Model
sentiment_model = pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

# Notification Config
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
NTFY_TOPIC = "crypto_mj"

# Ensure token exists
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN is missing from environment variables!")

# Load previous data
def load_previous_data():
    try:
        with open("previous_data.json", "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return {"prices": {}, "signals": {}}

# Save current data
def save_current_data(data):
    with open("previous_data.json", "w") as file:
        json.dump(data, file, indent=4)

# Fetch crypto prices
def get_crypto_prices():
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=usd"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        return {
            "BTC": data.get("bitcoin", {}).get("usd", 0),
            "ETH": data.get("ethereum", {}).get("usd", 0),
            "SOL": data.get("solana", {}).get("usd", 0)
        }
    except requests.exceptions.RequestException as e:
        logging.error(f"⚠️ Error fetching prices: {e}")
        return {"BTC": 0, "ETH": 0, "SOL": 0}

# Fetch sentiment data from CoinGecko
def get_sentiment(coin_id):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        return {
            "up_votes": data.get("sentiment_votes_up_percentage", 0),
            "down_votes": data.get("sentiment_votes_down_percentage", 0)
        }
    except requests.exceptions.RequestException as e:
        logging.error(f"⚠️ Error fetching sentiment for {coin_id}: {e}")
        return {"up_votes": 0, "down_votes": 0}

# Determine trading signal
def determine_signal(sentiment):
    up = sentiment["up_votes"]
    if up > 75:
        return "BUY ✅"
    elif up > 50:
        return "HOLD ⚖️"
    else:
        return "SELL ❌"

# Send notifications
def send_telegram_notification(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
        logging.info("✅ Telegram notification sent.")
    except requests.exceptions.RequestException as e:
        logging.error(f"⚠️ Error sending Telegram message: {e}")

def send_ntfy_notification(report):
    try:
        url = f"https://ntfy.sh/{NTFY_TOPIC}"
        headers = {"Title": "Market Sentiment Report", "Priority": "high"}
        response = requests.post(url, data=report.encode("utf-8"), headers=headers, timeout=10)
        response.raise_for_status()
        logging.info("✅ NTFY notification sent.")
    except requests.exceptions.RequestException as e:
        logging.error(f"⚠️ Error sending NTFY message: {e}")

# Generate Market Report
def generate_report(check_changes=True):
    logging.info("📊 Running Market Analysis...")

    previous_data = load_previous_data()
    old_signals = previous_data.get("signals", {})

    prices = get_crypto_prices()

    sentiment_btc = get_sentiment("bitcoin")
    sentiment_eth = get_sentiment("ethereum")
    sentiment_sol = get_sentiment("solana")

    btc_signal = determine_signal(sentiment_btc)
    eth_signal = determine_signal(sentiment_eth)
    sol_signal = determine_signal(sentiment_sol)

    signals_changed = (
        old_signals.get("BTC") != btc_signal or
        old_signals.get("ETH") != eth_signal or
        old_signals.get("SOL") != sol_signal
    )

    if not check_changes or signals_changed:
        message = f"🚦 BTC: {btc_signal}\nETH: {eth_signal}\nSOL: {sol_signal}"
        send_telegram_notification(message)
        send_ntfy_notification(message)
        logging.info("✅ Signals sent successfully.")
    else:
        logging.info("No changes in trading signals.")

    save_current_data({"prices": prices, "signals": {"BTC": btc_signal, "ETH": eth_signal, "SOL": sol_signal}})

# Telegram Bot Commands
async def start(update: Update, context: CallbackContext):
    await update.message.reply_text("Welcome to the Crypto Bot! Use /signals to get the latest trading signals.")

async def signals(update: Update, context: CallbackContext):
    previous_data = load_previous_data()
    signals = previous_data.get("signals", {})

    message = f"""
🚦 **Trading Signals**
- BTC: {signals.get("BTC", "N/A")}
- ETH: {signals.get("ETH", "N/A")}
- SOL: {signals.get("SOL", "N/A")}
"""
    await update.message.reply_text(message)

# Run Telegram Bot
def main():
    logging.info("🚀 Starting Telegram Bot...")

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Ensure webhook is removed before polling to avoid conflicts
    try:
        application.bot.delete_webhook()
        logging.info("✅ Webhook removed.")
    except Exception as e:
        logging.warning(f"⚠️ Error removing webhook: {e}")

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("signals", signals))

    logging.info("🤖 Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()
