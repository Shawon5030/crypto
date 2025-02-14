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
from threading import Thread

# Load environment variables
load_dotenv()

# Initialize Sentiment Model
sentiment_model = pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

# Notification Config
TELEGRAM_BOT_TOKEN = '7641277983:AAEw_lC8aeX6vLFPu_xhx8VMHtNKUOBSvxo'
TELEGRAM_CHAT_ID = '5642129186'
NTFY_TOPIC = 'crypto_mj'
TRADING_TYPE = 'intraday'

# Logging setup
logging.basicConfig(level=logging.INFO)

# Load previous data
def load_previous_data():
    try:
        with open("previous_data.json", "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return {"prices": {}, "deviations": {}, "signals": {}}

# Save current data
def save_current_data(data):
    with open("previous_data.json", "w") as file:
        json.dump(data, file, indent=4)

# Fetch crypto prices
def get_crypto_prices():
    url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=usd"
    response = requests.get(url)
    data = response.json()
    return {
        "BTC": data["bitcoin"]["usd"],
        "ETH": data["ethereum"]["usd"],
        "SOL": data.get("solana", {}).get("usd", 0)  # Handle missing Solana data
    }

# Fetch market data from Yahoo Finance
def get_market_data(ticker, period="1mo"):
    return yf.download(ticker, period=period)["Close"]

# Calculate correlation between two assets
def calculate_correlation(series1, series2):
    df = pd.concat([series1, series2], axis=1, join='inner').dropna()
    correlation = df.corr().iloc[0, 1] if len(df) >= 2 else None
    if correlation is None:
        return "Data Unavailable"
    elif correlation > 0.5:
        return f"{correlation:.2f} (Strong Positive)"
    elif 0.2 < correlation <= 0.5:
        return f"{correlation:.2f} (Moderate Positive)"
    elif -0.2 <= correlation <= 0.2:
        return f"{correlation:.2f} (Weak/No Correlation)"
    elif -0.5 <= correlation < -0.2:
        return f"{correlation:.2f} (Moderate Negative)"
    else:
        return f"{correlation:.2f} (Strong Negative)"

# Analyze sentiment using NLP model
def analyze_sentiment(text):
    result = sentiment_model(text)
    return result[0]['label']

# Fetch sentiment data from CoinGecko
def get_sentiment(coin_id):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
    response = requests.get(url)
    data = response.json()
    
    up_votes = data.get("sentiment_votes_up_percentage", 0)
    down_votes = data.get("sentiment_votes_down_percentage", 0)
    
    return {"up_votes": up_votes, "down_votes": down_votes}

# Determine trading signal based on sentiment
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
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    requests.post(url, data=payload)

def send_ntfy_notification(report):
    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    headers = {"Title": "Market Sentiment Report", "Priority": "high"}
    requests.post(url, data=report.encode("utf-8"), headers=headers)

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
        send_telegram_notification(f"🚦 BTC: {btc_signal}\nETH: {eth_signal}\nSOL: {sol_signal}")
        send_ntfy_notification(f"BTC: {btc_signal}, ETH: {eth_signal}, SOL: {sol_signal}")
        logging.info("✅ Signals sent successfully.")
    else:
        logging.info("No changes in trading signals.")

    save_current_data({"prices": prices, "signals": {"BTC": btc_signal, "ETH": eth_signal, "SOL": sol_signal}})

# Telegram Bot Commands
def start(update: Update, context: CallbackContext):
    update.message.reply_text("Welcome to the Crypto Bot! Use /signals to get the latest trading signals.")

def signals(update: Update, context: CallbackContext):
    previous_data = load_previous_data()
    signals = previous_data.get("signals", {})

    message = f"""
🚦 **Trading Signals**
- BTC: {signals.get("BTC", "N/A")}
- ETH: {signals.get("ETH", "N/A")}
- SOL: {signals.get("SOL", "N/A")}
"""
    update.message.reply_text(message)

# Run Telegram Bot
def main():
    # Create an Application instance instead of Updater
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("signals", signals))

    # Start the bot and run it
    application.run_polling()

if __name__ == "__main__":
    main()
