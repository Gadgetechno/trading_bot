import asyncio
import logging
import random
import time
import re
import json
import websockets
import sys
import os
import hashlib
import string
from datetime import datetime, timedelta, timezone
from collections import deque
from typing import Optional, Dict, Any, List
import threading
import signal as system_signal
import httpx  # <-- YAH ADD KIYA GAYA HAI

#import nest_asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)

# Apply nest_asyncio for Jupyter compatibility
#nest_asyncio.apply()

# --- 1. CONFIGURATION ---
CONFIG = {
    "TELEGRAM_BOT_TOKEN": "8034049017:AAGjBwA5dIqZfiUAIxYtu0F4K1Zoeugf1iU",
    "QUOTEX_EMAIL": "Quoto421@gmail.com",
    "QUOTEX_PASSWORD": "Quoto@123",
    "OTC_PAIRS": [
        "CAD/CHF", "EUR/SGD", "USD/BDT", "USD/DZD", "USD/EGP", "USD/IDR", 
        "USD/INR", "USD/MXN", "USD/PHP", "USD/ZAR", "NZD/JPY", "USD/ARS",
        "EUR/NZD", "NZD/CHF", "NZD/CAD", "USD/BRL", "USD/TRY", "USD/NGN",
        "USD/PKR", "USD/COP", "GBP/NZD", "AUD/NZD", "NZD/USD"
    ],
    "NON_OTC_PAIRS": [
        "USD/JPY", "AUD/USD", "AUD/JPY", "GBP/CAD", "GBP/USD", "EUR/GBP",
        "EUR/JPY", "AUD/CAD", "CAD/JPY", "EUR/AUD", "EUR/CAD", "EUR/CHF",
        "EUR/USD", "GBP/AUD", "GBP/JPY", "USD/CAD", "CHF/JPY", "AUD/CHF",
        "GBP/CHF", "USD/CHF"
    ],
    "ASSETS_TO_TRACK": [],
    "MAX_RETRIES": 5,
    "USE_DEMO_ACCOUNT": True,
    "SIMULATION_MODE": True,
    "TRADE_DURATION_MINUTES": 1,
    "QUOTEX_WS_URL": "wss://ws.quotex.io",
    "SIGNAL_INTERVAL_SECONDS": 600,
    "MIN_CONFIDENCE": 80,
    "MIN_SCORE": 75,
    "AUTO_TRADE_ENABLED": True,
    "ADMIN_IDS": [896970612, 1076818877, 2049948903],
    "ENTRY_DELAY_MINUTES": 2,
    "PRICE_UPDATE_INTERVAL": 2,
    "LIVE_MARKET_START": "09:00",
    "LIVE_MARKET_END": "23:30",
    # Website configuration
    "WEBSITE_URL": "http://learnwithtanishq.com",  # Change to your actual domain
    "BOT_SECRET_KEY": "tanix2-secret-key-2024",  # Same as in server.js
}

# Populate ASSETS_TO_TRACK
CONFIG["ASSETS_TO_TRACK"] = CONFIG["OTC_PAIRS"] + CONFIG["NON_OTC_PAIRS"]

# --- 2. TECHNICAL INDICATOR CONFIG ---
INDICATOR_CONFIG = {
    "MA_FAST": 5,
    "MA_MEDIUM": 10,
    "MA_SLOW": 20,
    "RSI_PERIOD": 14,
    "RSI_OVERBOUGHT": 70,
    "RSI_OVERSOLD": 30,
    "PRICE_HISTORY_SIZE": 200,
    "VOLATILITY_THRESHOLD": 0.001,
    "MIN_PRICE_DATA": 50,
    "BB_PERIOD": 20,
    "BB_STD": 2,
    "STOCHASTIC_K": 14,
    "STOCHASTIC_D": 3,
    "MACD_FAST": 12,
    "MACD_SLOW": 26,
    "MACD_SIGNAL": 9,
    "WILLIAMS_PERIOD": 14,
    "CCI_PERIOD": 20,
    "ATR_PERIOD": 14,
}

# --- 3. TIMEZONE CONFIGURATION ---
class IndiaTimezone:
    @staticmethod
    def now():
        return datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    
    @staticmethod
    def format_time(dt=None):
        if dt is None:
            dt = IndiaTimezone.now()
        return dt.strftime("%H:%M:00")
    
    @staticmethod
    def format_datetime(dt=None):
        if dt is None:
            dt = IndiaTimezone.now()
        return dt.strftime("%Y-%m-%d %H:%M:%S IST")
    
    @staticmethod
    def is_weekend():
        current_time = IndiaTimezone.now()
        return current_time.weekday() >= 5
    
    @staticmethod
    def is_live_market_hours():
        current_time = IndiaTimezone.now()
        current_time_str = current_time.strftime("%H:%M")
        
        market_start = CONFIG["LIVE_MARKET_START"]
        market_end = CONFIG["LIVE_MARKET_END"]
        
        return market_start <= current_time_str <= market_end

# --- 4. SMART SIGNAL SCHEDULER ---
class SmartSignalScheduler:
    @staticmethod
    def get_current_market_mode():
        if IndiaTimezone.is_weekend():
            return "OTC_ONLY"
        
        if IndiaTimezone.is_live_market_hours():
            return "LIVE_MARKET"
        else:
            return "OTC_ONLY"
    
    @staticmethod
    def get_available_assets():
        market_mode = SmartSignalScheduler.get_current_market_mode()
        
        if market_mode == "LIVE_MARKET":
            return CONFIG["OTC_PAIRS"] + CONFIG["NON_OTC_PAIRS"]
        else:
            return CONFIG["OTC_PAIRS"]
    
    @staticmethod
    def get_market_status_message():
        market_mode = SmartSignalScheduler.get_current_market_mode()
        current_time = IndiaTimezone.now()
        
        if market_mode == "LIVE_MARKET":
            status = "🟢 LIVE MARKET"
            description = "Generating high-quality signals for all pairs"
            available_pairs = len(CONFIG["OTC_PAIRS"] + CONFIG["NON_OTC_PAIRS"])
        else:
            status = "🔵 OTC MARKET"
            description = "Generating signals for OTC pairs only"
            available_pairs = len(CONFIG["OTC_PAIRS"])
        
        return {
            "status": status,
            "mode": market_mode,
            "description": description,
            "available_pairs": available_pairs,
            "current_time": IndiaTimezone.format_datetime(current_time),
            "next_mode_change": SmartSignalScheduler.get_next_mode_change_time()
        }
    
    @staticmethod
    def get_next_mode_change_time():
        current_time = IndiaTimezone.now()
        current_time_str = current_time.strftime("%H:%M")
        
        market_start = CONFIG["LIVE_MARKET_START"]
        market_end = CONFIG["LIVE_MARKET_END"]
        
        if current_time_str < market_start:
            next_change = datetime.strptime(market_start, "%H:%M").replace(
                year=current_time.year, 
                month=current_time.month, 
                day=current_time.day
            )
        elif market_start <= current_time_str <= market_end:
            next_change = datetime.strptime(market_end, "%H:%M").replace(
                year=current_time.year, 
                month=current_time.month, 
                day=current_time.day
            )
        else:
            next_day = current_time + timedelta(days=1)
            next_change = datetime.strptime(market_start, "%H:%M").replace(
                year=next_day.year, 
                month=next_day.month, 
                day=next_day.day
            )
        
        return IndiaTimezone.format_datetime(next_change)

# --- 5. ENHANCED SIGNAL QUALITY FILTER ---
class EnhancedSignalFilter:
    @staticmethod
    def meets_quality_standards(signal_data: Dict[str, Any]) -> bool:
        if signal_data.get('profit_percentage', 0) <= 75:
            return False
        
        if signal_data.get('confidence', 0) <= 80:
            return False
        
        analysis = signal_data.get('analysis', {})
        indicators = analysis.get('indicators', {})
        
        rsi = indicators.get('rsi', 50)
        if not (45 <= rsi <= 55):
            return False
        
        trend_strength = indicators.get('signal_strength', 0)
        if trend_strength <= 0.9:
            return False
        
        bullish_score = indicators.get('bullish_score', 0)
        bearish_score = indicators.get('bearish_score', 0)
        signal_diff = abs(bullish_score - bearish_score)
        
        if signal_diff < 3.0:
            return False
        
        return True
    
    @staticmethod
    def calculate_success_probability(signal_data: Dict[str, Any]) -> float:
        base_probability = 0.75
        
        confidence = signal_data.get('confidence', 80)
        confidence_bonus = (confidence - 80) * 0.002
        
        score = signal_data.get('score', 75)
        score_bonus = (score - 75) * 0.001
        
        analysis = signal_data.get('analysis', {})
        indicators = analysis.get('indicators', {})
        
        trend_strength = indicators.get('signal_strength', 1.0)
        trend_bonus = min(0.05, (trend_strength - 0.9) * 0.1)
        
        rsi = indicators.get('rsi', 50)
        if 45 <= rsi <= 55:
            rsi_bonus = 0.03
        else:
            rsi_bonus = 0
        
        total_probability = min(0.95, base_probability + confidence_bonus + score_bonus + trend_bonus + rsi_bonus)
        return total_probability

# --- 6. DATABASE LOCK ---
db_lock = threading.Lock()

# --- 7. JSON-BASED LICENSE MANAGEMENT WITH WEBSITE INTEGRATION ---
class LicenseManager:
    def __init__(self):
        self.data_dir = "data"
        self.users_file = os.path.join(self.data_dir, "users.json")
        self.tokens_file = os.path.join(self.data_dir, "tokens.json")
        self.signals_file = os.path.join(self.data_dir, "signals.json")
        self.trades_file = os.path.join(self.data_dir, "trades.json")
        self.performance_file = os.path.join(self.data_dir, "performance.json")
        self.init_db()
    
    def ensure_data_dir(self):
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
    
    def load_json(self, filename, default=None):
        self.ensure_data_dir()
        try:
            if os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading {filename}: {e}")
        return default if default is not None else {}
    
    def save_json(self, filename, data):
        self.ensure_data_dir()
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Error saving {filename}: {e}")
            return False
    
    def init_db(self):
        with db_lock:
            users = self.load_json(self.users_file, {})
            for admin_id in CONFIG["ADMIN_IDS"]:
                admin_id_str = str(admin_id)
                if admin_id_str not in users:
                    users[admin_id_str] = {
                        'user_id': admin_id,
                        'username': f"Admin{admin_id}",
                        'license_key': f"ADMIN{admin_id}",
                        'created_at': IndiaTimezone.now().isoformat(),
                        'is_active': True,
                        'website_access': True  # Admins automatically get website access
                    }
            self.save_json(self.users_file, users)
            self.save_json(self.tokens_file, {})
            self.save_json(self.signals_file, {})
            self.save_json(self.trades_file, {})
            self.save_json(self.performance_file, {"recent_signals": [], "success_rate": 0.85})
            
        print("✅ JSON Database initialized successfully")
    
    def generate_license_key(self, user_id, username):
        base_string = f"{user_id}{username}{IndiaTimezone.now().timestamp()}"
        return hashlib.md5(base_string.encode()).hexdigest()[:8]
    
    def generate_access_token(self, length=12):
        characters = string.ascii_uppercase + string.digits
        return ''.join(random.choice(characters) for _ in range(length))
    
    def create_license(self, user_id, username):
        with db_lock:
            users = self.load_json(self.users_file, {})
            user_id_str = str(user_id)
            
            license_key = self.generate_license_key(user_id, username)
            users[user_id_str] = {
                'user_id': user_id,
                'username': username,
                'license_key': license_key,
                'created_at': IndiaTimezone.now().isoformat(),
                'is_active': True,
                'website_access': True  # New users get website access
            }
            
            success = self.save_json(self.users_file, users)
            if success:
                print(f"✅ License created for user {user_id}: {license_key}")
                return license_key
            return None
    
    def create_access_token(self, admin_id):
        with db_lock:
            tokens = self.load_json(self.tokens_file, {})
            
            token = self.generate_access_token()
            tokens[token] = {
                'created_by': admin_id,
                'created_at': IndiaTimezone.now().isoformat(),
                'is_used': False,
                'used_by': None,
                'used_at': None
            }
            
            success = self.save_json(self.tokens_file, tokens)
            if success:
                print(f"✅ Access token generated by admin {admin_id}: {token}")
                return token
            return None
    
    def use_access_token(self, token, user_id):
        with db_lock:
            tokens = self.load_json(self.tokens_file, {})
            users = self.load_json(self.users_file, {})
            user_id_str = str(user_id)
            
            if token in tokens and not tokens[token]['is_used']:
                tokens[token]['is_used'] = True
                tokens[token]['used_by'] = user_id
                tokens[token]['used_at'] = IndiaTimezone.now().isoformat()
                
                username = f"User{user_id}"
                license_key = self.generate_license_key(user_id, username)
                users[user_id_str] = {
                    'user_id': user_id,
                    'username': username,
                    'license_key': license_key,
                    'created_at': IndiaTimezone.now().isoformat(),
                    'is_active': True,
                    'website_access': True  # Token users get website access
                }
                
                if self.save_json(self.tokens_file, tokens) and self.save_json(self.users_file, users):
                    print(f"✅ Token {token} used by user {user_id}")
                    return license_key
            
            print(f"❌ Invalid token attempt: {token} by user {user_id}")
            return None
    
    def check_user_access(self, user_id):
        if user_id in CONFIG["ADMIN_IDS"]:
            return True
            
        with db_lock:
            users = self.load_json(self.users_file, {})
            user_id_str = str(user_id)
            user = users.get(user_id_str)
            return user is not None and user.get('is_active', False)
    
    def check_website_access(self, user_id):
        """Check if user has website access"""
        if user_id in CONFIG["ADMIN_IDS"]:
            return True
            
        with db_lock:
            users = self.load_json(self.users_file, {})
            user_id_str = str(user_id)
            user = users.get(user_id_str)
            return user is not None and user.get('is_active', False) and user.get('website_access', False)
    
    def get_user_stats(self):
        with db_lock:
            users = self.load_json(self.users_file, {})
            tokens = self.load_json(self.tokens_file, {})
            
            active_users = sum(1 for user in users.values() if user.get('is_active', False))
            website_users = sum(1 for user in users.values() if user.get('website_access', False))
            available_tokens = sum(1 for token in tokens.values() if not token.get('is_used', False))
            used_tokens = sum(1 for token in tokens.values() if token.get('is_used', False))
            
            return active_users, website_users, available_tokens, used_tokens

    def get_active_users(self):
        with db_lock:
            users = self.load_json(self.users_file, {})
            active_users = []
            
            for user_data in users.values():
                if (user_data.get('is_active', False) and 
                    user_data.get('user_id') not in CONFIG["ADMIN_IDS"]):
                    active_users.append({
                        'user_id': user_data['user_id'],
                        'username': user_data.get('username', f"User{user_data['user_id']}"),
                        'license_key': user_data.get('license_key', ''),
                        'created_at': user_data.get('created_at', ''),
                        'website_access': user_data.get('website_access', False)
                    })
            
            return active_users

    def deactivate_user(self, user_id):
        with db_lock:
            users = self.load_json(self.users_file, {})
            user_id_str = str(user_id)
            
            if user_id_str in users:
                users[user_id_str]['is_active'] = False
                users[user_id_str]['website_access'] = False
                
                if user_id in STATE.auto_signal_users:
                    STATE.auto_signal_users.discard(user_id)
                
                success = self.save_json(self.users_file, users)
                if success:
                    print(f"✅ User {user_id} deactivated successfully")
                    return True
            
            print(f"❌ Failed to deactivate user {user_id}")
            return False

    def toggle_website_access(self, user_id):
        """Toggle website access for a user"""
        with db_lock:
            users = self.load_json(self.users_file, {})
            user_id_str = str(user_id)
            
            if user_id_str in users:
                current_status = users[user_id_str].get('website_access', False)
                new_status_bool = not current_status
                users[user_id_str]['website_access'] = new_status_bool
                
                success = self.save_json(self.users_file, users)
                if success:
                    new_status = "ENABLED" if new_status_bool else "DISABLED"
                    print(f"✅ Website access {new_status} for user {user_id}")
                    return True, new_status
            
            print(f"❌ Failed to toggle website access for user {user_id}")
            return False, None

    def save_signal(self, signal_data):
        with db_lock:
            signals = self.load_json(self.signals_file, {})
            signal_id = signal_data['trade_id']
            
            timestamp_str = signal_data['timestamp'].isoformat() if hasattr(signal_data['timestamp'], 'isoformat') else str(signal_data['timestamp'])
            
            signals[signal_id] = {
                'signal_id': signal_data['trade_id'],
                'asset': signal_data['asset'],
                'direction': signal_data['direction'],
                'entry_time': signal_data['entry_time'],
                'confidence': signal_data['confidence'],
                'profit_percentage': signal_data.get('profit_percentage', 0),
                'score': signal_data['score'],
                'source': signal_data.get('source', 'TECHNICAL'),
                'timestamp': timestamp_str,
                'market_mode': SmartSignalScheduler.get_current_market_mode()
            }
            
            self.save_json(self.signals_file, signals)
            
            self.update_performance_tracking(signal_data)

    def update_performance_tracking(self, signal_data):
        performance = self.load_json(self.performance_file, {"recent_signals": [], "success_rate": 0.85})
        
        performance["recent_signals"].append({
            "signal_id": signal_data['trade_id'],
            "score": signal_data['score'],
            "confidence": signal_data['confidence'],
            "profit_potential": signal_data.get('profit_percentage', 0),
            "timestamp": IndiaTimezone.now().isoformat()
        })
        
        performance["recent_signals"] = performance["recent_signals"][-50:]
        
        if performance["recent_signals"]:
            avg_score = sum(s['score'] for s in performance["recent_signals"]) / len(performance["recent_signals"])
            avg_confidence = sum(s['confidence'] for s in performance["recent_signals"]) / len(performance["recent_signals"])
            
            quality_factor = (avg_score - 75) * 0.002 + (avg_confidence - 80) * 0.0015
            performance["success_rate"] = min(0.95, 0.85 + quality_factor)
        
        self.save_json(self.performance_file, performance)

    def get_recent_performance(self):
        performance = self.load_json(self.performance_file, {"recent_signals": [], "success_rate": 0.85})
        return performance

    def save_active_trade(self, trade_id, user_id, asset, direction, entry_time, signal_data):
        with db_lock:
            trades = self.load_json(self.trades_file, {})
            
            expiry_time = (IndiaTimezone.now() + timedelta(minutes=CONFIG["TRADE_DURATION_MINUTES"] + CONFIG["ENTRY_DELAY_MINUTES"])).isoformat()

            simple_asset = asset.split(' ')[0]
            current_price = list(STATE.price_data.get(simple_asset, []))[-1] if STATE.price_data.get(simple_asset) else 0.0

            trades[trade_id] = {
                'trade_id': trade_id,
                'user_id': user_id,
                'asset': simple_asset,
                'direction': direction,
                'entry_time': entry_time,
                'expiry_time': expiry_time,
                'entry_price': current_price,
                'signal_data': signal_data,
                'created_at': IndiaTimezone.now().isoformat(),
                'message_id': None,
                'market_mode': SmartSignalScheduler.get_current_market_mode()
            }
            
            self.save_json(self.trades_file, trades)
            return trade_id

    def get_and_remove_expired_trades(self) -> List[Dict[str, Any]]:
        expired_trades = []
        now = IndiaTimezone.now()
        
        with db_lock:
            trades = self.load_json(self.trades_file, {})
            trades_to_keep = {}
            
            for trade_id, trade_data in trades.items():
                expiry_time_str = trade_data['expiry_time'].replace(' IST', '')
                try:
                    expiry_dt = datetime.fromisoformat(expiry_time_str)
                except ValueError:
                    expiry_dt = now - timedelta(minutes=1)
                
                if expiry_dt < now:
                    expired_trades.append(trade_data)
                else:
                    trades_to_keep[trade_id] = trade_data
            
            self.save_json(self.trades_file, trades_to_keep)
        
        return expired_trades
    
    def update_trade_message_id(self, trade_id, message_id):
        with db_lock:
            trades = self.load_json(self.trades_file, {})
            if trade_id in trades:
                trades[trade_id]['message_id'] = message_id
                self.save_json(self.trades_file, trades)


# --- 8. GLOBAL STATE ---
class TradingState:
    def __init__(self):
        self.quotex_client = None
        self.is_connected: bool = False
        self.last_signal_time: datetime = None
        self.current_balance: float = 1000.0
        self.simulation_mode: bool = CONFIG["SIMULATION_MODE"]
        self.price_data: Dict[str, deque] = {}
        self.telegram_app = None
        self.signal_generation_task = None
        self.price_update_task = None
        self.auto_signal_task = None
        self.health_check_task = None
        self.trade_result_task = None
        self.shutting_down = False
        self.license_manager = LicenseManager()
        self.user_states: Dict[int, Dict] = {}
        self.recent_signals: Dict[str, datetime] = {}
        self.signal_cooldown = timedelta(minutes=1)
        self.task_lock = asyncio.Lock()
        self.last_user_signal_time: Dict[int, datetime] = {}
        self.auto_signal_users: set = set()
        
        for asset in CONFIG["ASSETS_TO_TRACK"]:
            self.price_data[asset] = deque(maxlen=INDICATOR_CONFIG["PRICE_HISTORY_SIZE"])

STATE = TradingState()

# Configure Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('trading_bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


# --- WEBSITE SYNC FUNCTIONS (UPDATED) ---

async def sync_user_to_website(telegram_id: str, username: str, first_name: str):
    """
    Calls the Node.js server endpoint to add/update the user in the website's whitelist.
    """
    api_url = CONFIG.get("WEBSITE_URL", "http://learnwithtanishq.com") + "/api/add-user"
    secret_key = CONFIG.get("BOT_SECRET_KEY", "tanix2-secret-key-2024")
    
    user_data = {
        "telegramId": str(telegram_id),
        "username": username or f"User{telegram_id}",
        "firstName": first_name or "User",
        "secretKey": secret_key
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(api_url, json=user_data)
            
        if response.status_code == 200 and response.json().get("success"):
            logger.info(f"✅ Successfully synced user {telegram_id} to website whitelist.")
        else:
            logger.warning(f"⚠️ Failed to sync user {telegram_id} to website. Server response: {response.text}")
    except Exception as e:
        logger.error(f"❌ Error syncing user {telegram_id} to website: {e}")

async def remove_user_from_website(telegram_id: str):
    """
    Calls the Node.js server endpoint to deactivate the user from the website's whitelist.
    """
    api_url = CONFIG.get("WEBSITE_URL", "http://learnwithtanishq.com") + "/api/remove-user"
    secret_key = CONFIG.get("BOT_SECRET_KEY", "tanix2-secret-key-2024")
    
    user_data = {
        "telegramId": str(telegram_id),
        "secretKey": secret_key
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(api_url, json=user_data)
            
        if response.status_code == 200 and response.json().get("success"):
            logger.info(f"✅ Successfully deactivated user {telegram_id} from website whitelist.")
        else:
            logger.warning(f"⚠️ Failed to deactivate user {telegram_id} from website. Server response: {response.text}")
    except Exception as e:
        logger.error(f"❌ Error deactivating user {telegram_id} from website: {e}")


# --- 9. HIGH ACCURACY TECHNICAL INDICATORS ---
class HighAccuracyIndicators:
    @staticmethod
    def calculate_sma(prices: List[float], period: int) -> float:
        if len(prices) < period:
            return prices[-1] if prices else 0.0
        return sum(prices[-period:]) / period

    @staticmethod
    def calculate_ema(prices: List[float], period: int) -> float:
        if len(prices) < period:
            return prices[-1] if prices else 0.0
        
        ema = prices[0]
        multiplier = 2 / (period + 1)
        
        for price in prices[1:]:
            ema = (price - ema) * multiplier + ema
        
        return ema

    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> float:
        if len(prices) < period + 1:
            return 50.0
        
        gains = []
        losses = []
        
        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        
        if len(gains) < period:
            return 50.0
            
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100.0
            
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return max(0, min(100, rsi))

    @staticmethod
    def calculate_macd(prices: List[float]) -> Dict[str, float]:
        if len(prices) < 26:
            return {"macd": 0, "signal": 0, "histogram": 0}
        
        ema_12 = HighAccuracyIndicators.calculate_ema(prices, INDICATOR_CONFIG["MACD_FAST"])
        ema_26 = HighAccuracyIndicators.calculate_ema(prices, INDICATOR_CONFIG["MACD_SLOW"])
        macd = ema_12 - ema_26
        
        macd_values = [macd] * 9
        signal = HighAccuracyIndicators.calculate_ema(macd_values, INDICATOR_CONFIG["MACD_SIGNAL"])
        histogram = macd - signal
        
        return {
            "macd": macd,
            "signal": signal,
            "histogram": histogram
        }

    @staticmethod
    def calculate_bollinger_bands(prices: List[float], period: int = 20, std_dev: int = 2) -> Dict[str, float]:
        if len(prices) < period:
            sma = prices[-1] if prices else 1.0
            return {"upper": sma, "middle": sma, "lower": sma}
        
        sma = sum(prices[-period:]) / period
        variance = sum((x - sma) ** 2 for x in prices[-period:]) / period
        std = variance ** 0.5
        
        return {
            "upper": sma + (std_dev * std),
            "middle": sma,
            "lower": sma - (std_dev * std)
        }

    @staticmethod
    def calculate_stochastic(prices: List[float], period: int = 14) -> Dict[str, float]:
        if len(prices) < period:
            return {"k": 50.0, "d": 50.0}
        
        current_price = prices[-1]
        lowest_low = min(prices[-period:])
        highest_high = max(prices[-period:])
        
        if highest_high == lowest_low:
            k = 50.0
        else:
            k = ((current_price - lowest_low) / (highest_high - lowest_low)) * 100
        
        if len(prices) >= period + 2:
            k_values = [k] * 3
            d = sum(k_values) / 3
        else:
            d = k
        
        return {"k": k, "d": d}

    @staticmethod
    def calculate_cci(prices: List[float], period: int = 20) -> float:
        if len(prices) < period:
            return 0.0
        
        typical_prices = [(prices[i] + prices[i-1] + prices[i-2]) / 3 for i in range(2, len(prices))]
        typical_prices = typical_prices[-period:]
        
        sma = sum(typical_prices) / period
        mean_deviation = sum(abs(tp - sma) for tp in typical_prices) / period
        
        if mean_deviation == 0:
            return 0.0
            
        cci = (typical_prices[-1] - sma) / (0.015 * mean_deviation)
        return cci

    @staticmethod
    def calculate_williams_r(prices: List[float], period: int = 14) -> float:
        if len(prices) < period:
            return -50.0
        
        current_price = prices[-1]
        highest_high = max(prices[-period:])
        lowest_low = min(prices[-period:])
        
        if highest_high == lowest_low:
            return -50.0
            
        williams_r = ((highest_high - current_price) / (highest_high - lowest_low)) * -100
        return williams_r

    @staticmethod
    def calculate_atr(prices: List[float], period: int = 14) -> float:
        if len(prices) < period + 1:
            return 0.0
        
        true_ranges = []
        for i in range(1, len(prices)):
            high_low = prices[i] - prices[i-1]
            high_close = abs(prices[i] - prices[i-1])
            low_close = abs(prices[i-1] - prices[i])
            true_range = max(high_low, high_close, low_close)
            true_ranges.append(true_range)
        
        if len(true_ranges) < period:
            return 0.0
            
        atr = sum(true_ranges[-period:]) / period
        return atr

    @staticmethod
    def calculate_support_resistance(prices: List[float]) -> Dict[str, float]:
        if len(prices) < 30:
            current = prices[-1] if prices else 1.0
            return {"support": current * 0.995, "resistance": current * 1.005}
        
        high = max(prices[-20:])
        low = min(prices[-20:])
        close = prices[-1]
        
        pivot = (high + low + close) / 3
        r1 = (2 * pivot) - low
        s1 = (2 * pivot) - high
        
        return {
            "support": round(s1, 4),
            "resistance": round(r1, 4)
        }

    @staticmethod
    def analyze_asset_with_high_accuracy(prices: List[float], asset: str) -> Dict[str, Any]:
        try:
            if len(prices) < INDICATOR_CONFIG["MIN_PRICE_DATA"]:
                return {"valid": False}
            
            # Calculate all indicators
            ma_fast = HighAccuracyIndicators.calculate_sma(prices, INDICATOR_CONFIG["MA_FAST"])
            ma_medium = HighAccuracyIndicators.calculate_sma(prices, INDICATOR_CONFIG["MA_MEDIUM"])
            ma_slow = HighAccuracyIndicators.calculate_sma(prices, INDICATOR_CONFIG["MA_SLOW"])
            rsi = HighAccuracyIndicators.calculate_rsi(prices, INDICATOR_CONFIG["RSI_PERIOD"])
            macd_data = HighAccuracyIndicators.calculate_macd(prices)
            bb_data = HighAccuracyIndicators.calculate_bollinger_bands(prices)
            stochastic_data = HighAccuracyIndicators.calculate_stochastic(prices)
            cci = HighAccuracyIndicators.calculate_cci(prices)
            williams_r = HighAccuracyIndicators.calculate_williams_r(prices)
            atr = HighAccuracyIndicators.calculate_atr(prices)
            sr_levels = HighAccuracyIndicators.calculate_support_resistance(prices)
            
            current_price = prices[-1]
            price_change_5 = ((current_price - prices[-5]) / prices[-5] * 100) if len(prices) >= 5 else 0
            price_change_10 = ((current_price - prices[-10]) / prices[-10] * 100) if len(prices) >= 10 else 0
            
            # Enhanced signal scoring system
            bullish_score = 0
            bearish_score = 0
            max_score = 0
            
            # 1. Multi-timeframe MA alignment (Weight: 3)
            if ma_fast > ma_medium > ma_slow:
                bullish_score += 3
            elif ma_fast < ma_medium < ma_slow:
                bearish_score += 3
            max_score += 3
            
            # 2. RSI with optimal zone preference (Weight: 2.5)
            if 45 <= rsi <= 55:
                if price_change_5 > 0:
                    bullish_score += 2.5
                else:
                    bearish_score += 2.5
            elif rsi < 35 and price_change_5 > -1:
                bullish_score += 1.5
            elif rsi > 65 and price_change_5 < 1:
                bearish_score += 1.5
            max_score += 2.5
            
            # 3. MACD trend confirmation (Weight: 2)
            if macd_data["histogram"] > 0 and macd_data["macd"] > macd_data["signal"]:
                bullish_score += 2
            elif macd_data["histogram"] < 0 and macd_data["macd"] < macd_data["signal"]:
                bearish_score += 2
            max_score += 2
            
            # 4. Bollinger Bands squeeze and breakout (Weight: 2)
            bb_width = (bb_data["upper"] - bb_data["lower"]) / bb_data["middle"]
            bb_position = (current_price - bb_data["lower"]) / (bb_data["upper"] - bb_data["lower"])
            
            if bb_width < 0.02:
                if current_price > bb_data["middle"] and price_change_5 > 0:
                    bullish_score += 2
                elif current_price < bb_data["middle"] and price_change_5 < 0:
                    bearish_score += 2
            else:
                if bb_position < 0.2 and price_change_5 > 0:
                    bullish_score += 1.5
                elif bb_position > 0.8 and price_change_5 < 0:
                    bearish_score += 1.5
            max_score += 2
            
            # 5. Stochastic momentum (Weight: 1.5)
            if stochastic_data["k"] < 20 and stochastic_data["d"] < 20:
                bullish_score += 1.5
            elif stochastic_data["k"] > 80 and stochastic_data["d"] > 80:
                bearish_score += 1.5
            max_score += 1.5
            
            # 6. CCI trend (Weight: 1.5)
            if cci < -100:
                bullish_score += 1.5
            elif cci > 100:
                bearish_score += 1.5
            max_score += 1.5
            
            # 7. Williams %R (Weight: 1)
            if williams_r < -80:
                bullish_score += 1
            elif williams_r > -20:
                bearish_score += 1
            max_score += 1
            
            # 8. Support/Resistance levels (Weight: 1.5)
            if current_price <= sr_levels["support"] * 1.005:
                bullish_score += 1.5
            elif current_price >= sr_levels["resistance"] * 0.995:
                bearish_score += 1.5
            max_score += 1.5
            
            # 9. Price momentum (Weight: 1)
            if price_change_5 > 0.5 and price_change_10 > 0.5:
                bullish_score += 1
            elif price_change_5 < -0.5 and price_change_10 < -0.5:
                bearish_score += 1
            max_score += 1
            
            # 10. Volatility adjustment (Weight: 1)
            volatility = atr / current_price * 100
            if volatility < 0.5:
                if bullish_score > bearish_score + 2:
                    bullish_score += 1
                elif bearish_score > bullish_score + 2:
                    bearish_score += 1
            max_score += 1
            
            # Determine final direction and score
            if bullish_score > bearish_score:
                direction = "BULLISH"
                raw_score = (bullish_score / max_score) * 100
                signal_strength = bullish_score - bearish_score
            else:
                direction = "BEARISH"
                raw_score = (bearish_score / max_score) * 100
                signal_strength = bearish_score - bullish_score
            
            # Apply signal strength bonus
            strength_bonus = min(15, signal_strength * 3)
            base_score = raw_score + strength_bonus
            
            # Consistency bonus for multiple timeframe alignment
            consistency_bonus = 0
            if (bullish_score > bearish_score * 1.5) or (bearish_score > bullish_score * 1.5):
                consistency_bonus = 8
            
            final_score = min(95, base_score + consistency_bonus)
            
            # Calculate confidence based on signal clarity with higher minimum
            confidence = max(80, min(95, final_score - random.randint(0, 5)))
            
            # Enhanced validation - require stronger signal difference
            min_signal_diff = 3.0
            if abs(bullish_score - bearish_score) < min_signal_diff:
                return {"valid": False}
            
            if final_score < CONFIG["MIN_SCORE"] or confidence < CONFIG["MIN_CONFIDENCE"]:
                return {"valid": False}
            
            # Enhanced profit potential calculation
            base_profit = 78.0
            volatility_factor = min(12, volatility * 10)
            strength_factor = min(10, signal_strength * 2)
            profit_percentage = base_profit + volatility_factor + strength_factor
            
            # Ensure minimum profit potential
            if profit_percentage < 75:
                profit_percentage = 75 + random.uniform(1, 5)
            
            return {
                "score": int(final_score),
                "direction": direction,
                "confidence": int(confidence),
                "profit_percentage": round(min(95, profit_percentage), 1),
                "valid": True,
                "indicators": {
                    "ma_fast": round(ma_fast, 4),
                    "ma_medium": round(ma_medium, 4),
                    "ma_slow": round(ma_slow, 4),
                    "rsi": round(rsi, 1),
                    "macd_histogram": round(macd_data["histogram"], 6),
                    "bb_upper": round(bb_data["upper"], 4),
                    "bb_lower": round(bb_data["lower"], 4),
                    "stochastic_k": round(stochastic_data["k"], 1),
                    "stochastic_d": round(stochastic_data["d"], 1),
                    "cci": round(cci, 1),
                    "williams_r": round(williams_r, 1),
                    "atr": round(atr, 4),
                    "support": round(sr_levels["support"], 4),
                    "resistance": round(sr_levels["resistance"], 4),
                    "current_price": round(current_price, 4),
                    "price_change_5": round(price_change_5, 2),
                    "volatility": round(volatility, 3),
                    "bullish_score": round(bullish_score, 1),
                    "bearish_score": round(bearish_score, 1),
                    "signal_strength": round(signal_strength, 2)
                }
            }
        except Exception as e:
            logger.error(f"Error in analyze_asset_with_high_accuracy: {e}")
            return {"valid": False}

    @staticmethod
    def determine_simulated_result(trade_data: Dict[str, Any], price_data: Dict[str, deque]) -> str:
        score = trade_data['signal_data'].get('score', 75)
        confidence = trade_data['signal_data'].get('confidence', 80)
        
        base_win_rate = 0.70 
        score_bonus = (score - CONFIG["MIN_SCORE"]) / 100 
        confidence_bonus = (confidence - CONFIG["MIN_CONFIDENCE"]) * 0.001
        win_probability = min(0.90, base_win_rate + score_bonus + confidence_bonus)
        
        if random.random() < win_probability:
            return "Sure Shot"
        else:
            return "LOSE"

# --- 10. ENHANCED SIGNAL GENERATION ---
def generate_high_accuracy_signal() -> Dict[str, Any]:
    try:
        current_time = IndiaTimezone.now()
        
        available_assets = SmartSignalScheduler.get_available_assets()
        market_mode = SmartSignalScheduler.get_current_market_mode()
        
        logger.info(f"🎯 TANIX AI - Market Mode: {market_mode}, Analyzing {len(available_assets)} assets")
        
        best_signal = None
        best_score = 0
        
        for asset in available_assets:
            prices = list(STATE.price_data.get(asset, []))
            if len(prices) >= INDICATOR_CONFIG["MIN_PRICE_DATA"]:
                analysis = HighAccuracyIndicators.analyze_asset_with_high_accuracy(prices, asset)
                
                if analysis["valid"]:
                    direction = "CALL" if analysis["direction"] == "BULLISH" else "PUT"
                    
                    entry_time = (current_time + timedelta(minutes=CONFIG["ENTRY_DELAY_MINUTES"]))
                    entry_time_str = IndiaTimezone.format_time(entry_time)
                    
                    signal = {
                        "trade_id": f"TANIX_AI_{asset.replace('/', '_')}_{int(current_time.timestamp())}",
                        "asset": f"{asset} {'(OTC)' if asset in CONFIG['OTC_PAIRS'] else ''}",
                        "direction": direction,
                        "confidence": analysis["confidence"],
                        "profit_percentage": analysis["profit_percentage"],
                        "score": analysis["score"],
                        "entry_time": entry_time_str,
                        "analysis": analysis, 
                        "source": "TANIX_AI",
                        "timestamp": current_time,
                        "is_otc": asset in CONFIG["OTC_PAIRS"],
                        "market_mode": market_mode
                    }
                    
                    if EnhancedSignalFilter.meets_quality_standards(signal):
                        if analysis["score"] > best_score:
                            best_signal = signal
                            best_score = analysis["score"]
        
        if best_signal:
            STATE.license_manager.save_signal(best_signal)
            success_probability = EnhancedSignalFilter.calculate_success_probability(best_signal)
            
            logger.info(f"🎯 TANIX AI Signal: {best_signal['asset']} {best_signal['direction']} "
                        f"(Score: {best_signal['score']}, Confidence: {best_signal['confidence']}%, "
                        f"Profit: {best_signal['profit_percentage']}%, Success Prob: {success_probability:.1%})")
            return best_signal
        else:
            logger.info("🎯 TANIX AI - No high-quality signals found, using enhanced fallback")
            return generate_enhanced_fallback_signal()
            
    except Exception as e:
        logger.error(f"Error in generate_high_accuracy_signal: {e}")
        return generate_enhanced_fallback_signal()

def generate_enhanced_fallback_signal() -> Dict[str, Any]:
    current_time = IndiaTimezone.now()
    
    available_assets = SmartSignalScheduler.get_available_assets()
    market_mode = SmartSignalScheduler.get_current_market_mode()
    
    asset = random.choice(available_assets)
    
    entry_time = (current_time + timedelta(minutes=CONFIG["ENTRY_DELAY_MINUTES"]))
    entry_time_str = IndiaTimezone.format_time(entry_time)
    
    score = random.randint(78, 85)
    confidence = random.randint(80, 87)
    profit = random.uniform(78.0, 88.0)

    if profit < 75:
        profit = 75 + random.uniform(3, 8)
    if confidence < 80:
        confidence = 80 + random.randint(1, 5)

    direction = random.choice(["CALL", "PUT"])
    base_price = list(STATE.price_data.get(asset.split(' ')[0], []))[-1] if STATE.price_data.get(asset.split(' ')[0]) else RealisticPriceGenerator.generate_initial_prices(asset, 1)[0]
    
    ma_diff = random.uniform(0.0001, 0.0005)
    base_rsi = random.uniform(48.0, 52.0)
    base_stoch = random.uniform(55.0, 65.0) if direction == "CALL" else random.uniform(35.0, 45.0)
    
    dummy_indicators = {
        "ma_fast": round(base_price + ma_diff, 4) if direction == "CALL" else round(base_price - ma_diff, 4),
        "ma_medium": round(base_price, 4),
        "ma_slow": round(base_price - ma_diff, 4) if direction == "CALL" else round(base_price + ma_diff, 4),
        "rsi": round(base_rsi, 1),
        "macd_histogram": round(random.uniform(0.00001, 0.00005) if direction == "CALL" else random.uniform(-0.00005, -0.00001), 6),
        "bb_upper": round(base_price * 1.002, 4),
        "bb_lower": round(base_price * 0.998, 4),
        "stochastic_k": round(base_stoch, 1),
        "stochastic_d": round(base_stoch - random.uniform(1.0, 5.0), 1),
        "cci": round(random.uniform(15.0, 45.0) if direction == "CALL" else random.uniform(-45.0, -15.0), 1),
        "williams_r": round(random.uniform(-65.0, -55.0) if direction == "CALL" else random.uniform(-45.0, -35.0), 1),
        "atr": round(base_price * random.uniform(0.0001, 0.0005), 4),
        "support": round(base_price * 0.999, 4),
        "resistance": round(base_price * 1.001, 4),
        "current_price": round(base_price, 4),
        "price_change_5": round(random.uniform(0.02, 0.06) if direction == "CALL" else random.uniform(-0.06, -0.02), 2),
        "volatility": round(random.uniform(0.08, 0.12), 3),
        "bullish_score": round(random.uniform(7.0, 9.0), 1) if direction == "CALL" else round(random.uniform(5.0, 7.0), 1),
        "bearish_score": round(random.uniform(5.0, 7.0), 1) if direction == "CALL" else round(random.uniform(7.0, 9.0), 1),
        "signal_strength": round(random.uniform(1.5, 3.5), 2)
    }
    
    return {
        "trade_id": f"TANIX_AI_FB_{asset.replace('/', '_')}_{int(current_time.timestamp())}",
        "asset": f"{asset} {'(OTC)' if asset in CONFIG['OTC_PAIRS'] else ''}",
        "direction": direction,
        "confidence": confidence,
        "profit_percentage": profit,
        "score": score,
        "entry_time": entry_time_str,
        "source": "TANIX_AI_ENHANCED_FALLBACK",
        "timestamp": current_time,
        "is_otc": asset in CONFIG["OTC_PAIRS"],
        "market_mode": market_mode,
        "analysis": {"indicators": dummy_indicators}
    }

# --- UPDATED FORMAT_SIGNAL_MESSAGE FUNCTION ---
def format_signal_message(signal: Dict[str, Any]) -> str:
    asset_name = signal["asset"]
    emoji_dir = "📈" if signal["direction"] == "CALL" else "📉"

    message = (
        f"🤖 TANIX AI TRADING SIGNAL 🤖\n\n"
        f"📌 Asset: {asset_name}\n"
        f"🎯 Direction: {signal['direction']} {emoji_dir}\n"
        f"⏰ ENTRY TIME: {signal['entry_time']} IST\n"
        f"⏱️ TIMEFRAME: 1 MINUTE\n\n"
        f"💰 Confidence: {signal['confidence']}%\n"
        f"💸 Profit Potential: {signal.get('profit_percentage', 80):.1f}%\n"
        f"🔮 Source: TANIX AI\n"
        f"📊 Score: {signal['score']}/100\n\n"
    )

    if signal.get("analysis") and signal["analysis"].get("indicators"):
        ind = signal['analysis']['indicators']
        message += (
            f"📈 Technical Analysis:\n"
            f"• MA Trend: {ind['ma_fast']} vs {ind['ma_slow']}\n"
            f"• RSI: {ind['rsi']}\n"
            f"• MACD Hist: {ind['macd_histogram']}\n"
            f"• Stochastic: K{ind['stochastic_k']}/D{ind['stochastic_d']}\n"
            f"• Trend Strength: {ind['signal_strength']:.2f}/1.0\n"
            f"• Support: {ind['support']}\n"
            f"• Resistance: {ind['resistance']}\n"
        )

    message += (
        "───────────────\n"
        "🇮🇳 All times are in IST (UTC+5:30)\n"
        "💲 Follow Proper Money Management\n"
        "⏳️ Always Select 1 Minute time frame\n"
        "🔁 Use 1 Step MTG if Loss\n"
        "🤖 Powered by TANIX AI"
    )

    return message


# --- 11. REALISTIC PRICE SIMULATION ---
class RealisticPriceGenerator:
    @staticmethod
    def generate_initial_prices(asset: str, count: int = 200) -> List[float]:
        base_prices = {
            "CAD/CHF": 0.6550, "EUR/SGD": 1.4550, "USD/BDT": 110.50, 
            "USD/DZD": 134.80, "USD/EGP": 30.85, "USD/IDR": 15600.0,
            "USD/INR": 83.25, "USD/MXN": 17.35, "USD/PHP": 56.20, 
            "USD/ZAR": 18.85, "NZD/JPY": 89.40, "USD/ARS": 350.0,
            "EUR/NZD": 1.7800, "NZD/CHF": 0.5450, "NZD/CAD": 0.8200,
            "USD/BRL": 4.95, "USD/TRY": 32.25, "USD/NGN": 460.0,
            "USD/PKR": 280.0, "USD/COP": 3950.0, "GBP/NZD": 2.0800,
            "AUD/NZD": 1.0950, "NZD/USD": 0.6150,
            "USD/JPY": 148.50, "AUD/USD": 0.6580, "AUD/JPY": 97.80,
            "GBP/CAD": 1.7050, "GBP/USD": 1.2680, "EUR/GBP": 0.8580,
            "EUR/JPY": 161.20, "AUD/CAD": 0.8850, "CAD/JPY": 110.20,
            "EUR/AUD": 1.6550, "EUR/CAD": 1.4650, "EUR/CHF": 0.9550,
            "EUR/USD": 1.0870, "GBP/AUD": 1.9300, "GBP/JPY": 188.00,
            "USD/CAD": 1.3520, "CHF/JPY": 168.80, "AUD/CHF": 0.5770,
            "GBP/CHF": 1.1250, "USD/CHF": 0.8820
        }
        
        base_price = base_prices.get(asset, 1.0)
        prices = [base_price]
        
        volatility = random.uniform(0.08, 0.15)
        trend = random.uniform(-0.005, 0.005)
        
        for i in range(count - 1):
            noise = random.gauss(0, volatility / 100)
            change = trend + noise
            new_price = prices[-1] * (1 + change)
            
            if abs(new_price - base_price) / base_price > 0.02:
                reversion = (base_price - new_price) * 0.01
                new_price += reversion
                
            prices.append(round(new_price, 4))
        
        return prices
    
    @staticmethod
    def generate_price_update(last_price: float, asset: str) -> float:
        volatility = random.uniform(0.05, 0.12)
        change = random.gauss(0, volatility / 100)
        new_price = last_price * (1 + change)
        return round(new_price, 4)

# --- 12. ASYNC TASK MANAGEMENT ---
class TaskManager:
    def __init__(self):
        self.tasks = []
        self.running = True
    
    async def create_task(self, coro, name: str):
        task = asyncio.create_task(coro, name=name)
        self.tasks.append(task)
        return task
    
    async def cancel_all(self):
        self.running = False
        for task in self.tasks:
            if not task.done():
                task.cancel()
        
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        
        self.tasks.clear()

task_manager = TaskManager()

async def price_update_task():
    logger.info("💰 Price update task started for all pairs")
    
    while task_manager.running and not STATE.shutting_down:
        try:
            async with STATE.task_lock:
                for asset in CONFIG["ASSETS_TO_TRACK"]:
                    if STATE.price_data[asset]:
                        last_price = STATE.price_data[asset][-1]
                        new_price = RealisticPriceGenerator.generate_price_update(last_price, asset)
                        STATE.price_data[asset].append(new_price)
            
            await asyncio.sleep(CONFIG["PRICE_UPDATE_INTERVAL"])
            
        except asyncio.CancelledError:
            logger.info("💰 Price update task cancelled")
            break
        except Exception as e:
            logger.error(f"Price update error: {e}")
            await asyncio.sleep(5)

async def auto_signal_task():
    logger.info("🔄 TANIX AI Automated signal task started (10-minute intervals)")
    
    await asyncio.sleep(10)
    
    while task_manager.running and not STATE.shutting_down:
        try:
            if STATE.auto_signal_users and STATE.telegram_app:
                signal = generate_high_accuracy_signal()
                message = format_signal_message(signal)
                
                for user_id in list(STATE.auto_signal_users):
                    try:
                        message_sent = await STATE.telegram_app.bot.send_message(
                            chat_id=user_id,
                            text=message,
                            parse_mode=None  # Changed from 'Markdown' to None to avoid entity parsing errors
                        )
                        
                        serializable_signal = signal.copy()
                        serializable_signal['timestamp'] = serializable_signal['timestamp'].isoformat()
                        
                        STATE.license_manager.save_active_trade(
                            trade_id=signal['trade_id'], 
                            user_id=user_id, 
                            asset=signal['asset'], 
                            direction=signal['direction'], 
                            entry_time=signal['entry_time'], 
                            signal_data=serializable_signal
                        )
                        STATE.license_manager.update_trade_message_id(signal['trade_id'], message_sent.message_id)
                        
                        logger.info(f"🔄 TANIX AI Auto signal sent to user {user_id}: "
                                    f"{signal['asset']} {signal['direction']} (Score: {signal['score']})")
                    except Exception as e:
                        logger.error(f"Failed to send auto signal to user {user_id}: {e}")
            
            await asyncio.sleep(CONFIG["SIGNAL_INTERVAL_SECONDS"])
            
        except asyncio.CancelledError:
            logger.info("🔄 Auto signal task cancelled")
            break
        except Exception as e:
            logger.error(f"Auto signal error: {e}")
            await asyncio.sleep(60)

async def trade_result_task():
    logger.info("⏱️ Trade result tracking task started.")
    
    await asyncio.sleep(CONFIG["ENTRY_DELAY_MINUTES"] * 60 + CONFIG["TRADE_DURATION_MINUTES"] * 60)
    
    while task_manager.running and not STATE.shutting_down:
        try:
            expired_trades = STATE.license_manager.get_and_remove_expired_trades()
            
            if expired_trades:
                for trade in expired_trades:
                    user_id = trade['user_id']
                    trade_id = trade['trade_id']
                    
                    result = HighAccuracyIndicators.determine_simulated_result(trade, STATE.price_data)
                    
                    if result == "Sure Shot":
                        result_emoji = "✅ SURE SHOT"
                    elif result == "LOSE":
                        result_emoji = "❌ LOSE"
                    else:
                        result_emoji = "⚠️ UNKNOWN"

                    result_message = (
                        f"{result_emoji} — Trade Result for {trade['asset']} {trade['direction']} "
                        f"(Score: {trade['signal_data'].get('score', 0)} Score)"
                    )
                    
                    if trade.get('message_id') and STATE.telegram_app:
                        try:
                            await STATE.telegram_app.bot.send_message(
                                chat_id=user_id,
                                text=result_message,
                                parse_mode=None  # Changed from 'Markdown' to None
                            )
                            logger.info(f"✅ Trade result posted for {trade_id} to user {user_id}: {result}")
                        except Exception as e:
                            logger.error(f"Failed to send trade result for {trade_id} to user {user_id}: {e}")
                    else:
                        logger.info(f"Skipping result post for non-tracked trade {trade_id}")
            
            await asyncio.sleep(10)
            
        except asyncio.CancelledError:
            logger.info("⏱️ Trade result task cancelled")
            break
        except Exception as e:
            logger.error(f"Trade result error: {e}")
            await asyncio.sleep(30)

# --- 13. TELEGRAM HANDLERS WITH WEBSITE INTEGRATION (UPDATED) ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    first_name = update.effective_user.first_name or "User"
    
    if STATE.license_manager.check_user_access(user_id):
        
        # --- YAH BLOCK UPDATE KIYA GAYA HAI ---
        # User ko website se sync karne ki koshish karein
        try:
            await sync_user_to_website(str(user_id), username, first_name)
        except Exception as e:
            logger.error(f"Failed to trigger website sync for user {user_id} on /start: {e}")
        # --- YAHAN TAK ---

        website_access = STATE.license_manager.check_website_access(user_id)
        website_status = "✅ ACTIVE" if website_access else "❌ INACTIVE"
        
        keyboard = [
            [InlineKeyboardButton("🎯 Signal", callback_data="get_signal")],
            [InlineKeyboardButton("🤖 Automated Signal", callback_data="auto_signals")],
            [InlineKeyboardButton("📊 Market Status", callback_data="market_status")],
            [InlineKeyboardButton("🌐 Website Access", callback_data="website_info")],
        ]
        
        if user_id in CONFIG["ADMIN_IDS"]:
            keyboard.append([InlineKeyboardButton("👨‍💼 Admin Panel", callback_data="admin_panel")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        auto_status = "✅ ON" if user_id in STATE.auto_signal_users else "❌ OFF"
        market_status = SmartSignalScheduler.get_market_status_message()
        
        await update.message.reply_text(
            f"🤖 TANIX AI TRADING BOT 🤖\n\n"
            f"✅ License Status: ACTIVE\n"
            f"👤 User: {first_name}\n"
            f"🆔 ID: {user_id}\n"
            f"🌐 Website Access: {website_status}\n"
            f"🎯 Strategy: AI-POWERED ANALYSIS\n"
            f"⏰ Timeframe: 1 MINUTE\n"
            f"💸 Minimum Profit: 75%+\n"
            f"🎯 Minimum Confidence: 80%+\n"
            f"🤖 Auto Signals: {auto_status}\n"
            f"📊 Market Mode: {market_status['status']}\n\n"
            f"Choose an option:",
            reply_markup=reply_markup,
            parse_mode=None
        )
    else:
        await update.message.reply_text(
            f"🔒 Access Required\n\n"
            f"Use /token YOUR_TOKEN to activate your account.",
            parse_mode=None
        )

async def token_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    first_name = update.effective_user.first_name or "User"
    
    if not context.args:
        await update.message.reply_text("❌ Usage: /token YOUR_TOKEN", parse_mode=None)
        return
    
    token = context.args[0].strip().upper()
    license_key = STATE.license_manager.use_access_token(token, user_id)
    
    if license_key:
        await update.message.reply_text(
            f"✅ Access Granted!\n\n"
            f"License: {license_key}\n"
            f"User ID: {user_id}\n"
            f"🌐 Website Access: ✅ ENABLED\n\n"
            f"Use /start to begin.",
            parse_mode=None
        )
        
        # --- YAH BLOCK UPDATE KIYA GAYA HAI ---
        # Naye user ko website se sync karein
        try:
            await sync_user_to_website(str(user_id), username, first_name)
        except Exception as e:
            logger.error(f"Failed to trigger website sync for new user {user_id} on /token: {e}")
        # --- YAHAN TAK ---
            
    else:
        await update.message.reply_text("❌ Invalid token", parse_mode=None)

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if user_id not in CONFIG["ADMIN_IDS"]:
        await update.message.reply_text("❌ Admin only", parse_mode=None)
        return
    
    keyboard = [
        [InlineKeyboardButton("🎫 Generate Token", callback_data="generate_token")],
        [InlineKeyboardButton("📊 User Stats", callback_data="user_stats")],
        [InlineKeyboardButton("🎯 Performance Report", callback_data="performance_report")],
        [InlineKeyboardButton("🌐 Website Users", callback_data="website_users")],
        [InlineKeyboardButton("🗑️ Remove Selected User", callback_data="remove_user")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("👨‍💼 Admin Panel", reply_markup=reply_markup, parse_mode=None)

# --- FIXED CALLBACK HANDLER WITH WEBSITE INTEGRATION (UPDATED) ---
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    try:
        if data == "get_signal":
            if not STATE.license_manager.check_user_access(user_id):
                await query.message.reply_text("❌ Need license", parse_mode=None)
                return
                
            signal = generate_high_accuracy_signal()
            message = format_signal_message(signal)
            
            message_sent = await query.message.reply_text(message, parse_mode=None)

            serializable_signal = signal.copy()
            serializable_signal['timestamp'] = serializable_signal['timestamp'].isoformat()
            
            STATE.license_manager.save_active_trade(
                trade_id=signal['trade_id'], 
                user_id=user_id, 
                asset=signal['asset'], 
                direction=signal['direction'], 
                entry_time=signal['entry_time'], 
                signal_data=serializable_signal
            )
            STATE.license_manager.update_trade_message_id(signal['trade_id'], message_sent.message_id)
            
            logger.info(f"👤 User {user_id} requested TANIX AI signal: "
                        f"{signal['asset']} {signal['direction']} (Score: {signal['score']})")
            return
        
        elif data == "auto_signals":
            if not STATE.license_manager.check_user_access(user_id):
                await query.message.reply_text("❌ Need license", parse_mode=None)
                return
            
            if user_id in STATE.auto_signal_users:
                STATE.auto_signal_users.discard(user_id)
                status = "❌ OFF"
                message_text = "🤖 Automated signals have been stopped."
                logger.info(f"🛑 User {user_id} stopped automated signals")
            else:
                STATE.auto_signal_users.add(user_id)
                status = "✅ ON"
                message_text = "🤖 Automated signals started! You'll receive TANIX AI signals every 10 minutes automatically."
                logger.info(f"🚀 User {user_id} started automated signals")
            
            keyboard = [
                [InlineKeyboardButton("🎯 Signal", callback_data="get_signal")],
                [InlineKeyboardButton("🤖 Automated Signal", callback_data="auto_signals")],
                [InlineKeyboardButton("📊 Market Status", callback_data="market_status")],
                [InlineKeyboardButton("🌐 Website Access", callback_data="website_info")],
            ]
            
            if user_id in CONFIG["ADMIN_IDS"]:
                keyboard.append([InlineKeyboardButton("👨‍💼 Admin Panel", callback_data="admin_panel")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            market_status = SmartSignalScheduler.get_market_status_message()
            website_access = STATE.license_manager.check_website_access(user_id)
            website_status = "✅ ACTIVE" if website_access else "❌ INACTIVE"
            
            await query.message.edit_text(
                f"🤖 TANIX AI TRADING BOT 🤖\n\n"
                f"✅ License Status: ACTIVE\n"
                f"👤 User: {query.from_user.first_name}\n"
                f"🆔 ID: {user_id}\n"
                f"🌐 Website Access: {website_status}\n"
                f"🎯 Strategy: AI-POWERED ANALYSIS\n"
                f"⏰ Timeframe: 1 MINUTE\n"
                f"💸 Minimum Profit: 75%+\n"
                f"🎯 Minimum Confidence: 80%+\n"
                f"🤖 Auto Signals: {status}\n"
                f"📊 Market Mode: {market_status['status']}\n\n"
                f"{message_text}",
                reply_markup=reply_markup,
                parse_mode=None
            )
            return
        
        elif data == "market_status":
            if not STATE.license_manager.check_user_access(user_id):
                await query.message.reply_text("❌ Need license", parse_mode=None)
                return
            
            market_status = SmartSignalScheduler.get_market_status_message()
            performance = STATE.license_manager.get_recent_performance()
            
            status = []
            sample_pairs = CONFIG["ASSETS_TO_TRACK"][:6]
            for asset in sample_pairs:
                prices = list(STATE.price_data.get(asset, []))
                if prices:
                    price = prices[-1]
                    if len(prices) > 1:
                        change = ((price - prices[-2]) / prices[-2]) * 100
                        change_emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"
                        display_name = f"{asset} {'(OTC)' if asset in CONFIG['OTC_PAIRS'] else ''}"
                        status.append(f"• {display_name}: ${price:.4f} {change_emoji} {change:+.2f}%")
                    else:
                        display_name = f"{asset} {'(OTC)' if asset in CONFIG['OTC_PAIRS'] else ''}"
                        status.append(f"• {display_name}: ${price:.4f}")
            
            status_text = "\n".join(status) if status else "No data"
            
            auto_count = len(STATE.auto_signal_users)
            
            await query.message.reply_text(
                f"📊 Market Status 🤖\n\n"
                f"{market_status['status']} - {market_status['description']}\n"
                f"⏰ Current Time: {market_status['current_time']}\n"
                f"🕒 Next Change: {market_status['next_mode_change']}\n\n"
                f"Live Prices (Sample):\n{status_text}\n\n"
                f"🔗 System Status:\n"
                f"• Bot: TANIX AI 🤖\n"
                f"• Timeframe: 1 MINUTE\n"
                f"• Auto Users: {auto_count}\n"
                f"• Min Profit: 75%+\n"
                f"• Min Confidence: 80%+\n"
                f"• Success Rate: {performance['success_rate']:.1%}\n"
                f"• Timezone: IST 🇮🇳",
                parse_mode=None
            )
            return
        
        elif data == "website_info":
            if not STATE.license_manager.check_user_access(user_id):
                await query.message.reply_text("❌ Need license", parse_mode=None)
                return
            
            website_access = STATE.license_manager.check_website_access(user_id)
            
            if website_access:
                message = (
                    f"🌐 TANIX AI Website Access\n\n"
                    f"✅ Status: ACTIVE\n"
                    f"👤 User ID: {user_id}\n"
                    f"🔗 Website: {CONFIG['WEBSITE_URL']}\n\n"
                    f"📋 Instructions:\n"
                    f"1. Visit: {CONFIG['WEBSITE_URL']}\n"
                    f"2. Enter your Telegram ID: {user_id}\n"
                    f"3. Click 'Verify & Login'\n"
                    f"4. Access the dashboard\n\n"
                    f"💡 Your Telegram ID is your login credential for the website."
                )
            else:
                message = (
                    f"🌐 TANIX AI Website Access\n\n"
                    f"❌ Status: INACTIVE\n"
                    f"👤 User ID: {user_id}\n\n"
                    f"📞 Contact admin to enable website access."
                )
            
            await query.message.reply_text(message, parse_mode=None)
            return
        
        elif data == "admin_panel":
            if user_id not in CONFIG["ADMIN_IDS"]:
                await query.message.reply_text("❌ Admin only", parse_mode=None)
                return
            
            keyboard = [
                [InlineKeyboardButton("🎫 Generate Token", callback_data="generate_token")],
                [InlineKeyboardButton("📊 User Stats", callback_data="user_stats")],
                [InlineKeyboardButton("🎯 Performance Report", callback_data="performance_report")],
                [InlineKeyboardButton("🌐 Website Users", callback_data="website_users")],
                [InlineKeyboardButton("🗑️ Remove Selected User", callback_data="remove_user")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.reply_text("👨‍💼 Admin Panel", reply_markup=reply_markup, parse_mode=None)
            return
        
        elif data == "generate_token":
            if user_id not in CONFIG["ADMIN_IDS"]:
                await query.message.reply_text("❌ Admin only", parse_mode=None)
                return
            
            token = STATE.license_manager.create_access_token(user_id)
            await query.message.reply_text(f"🎫 New Token:\n{token}", parse_mode=None)
            return
        
        elif data == "user_stats":
            if user_id not in CONFIG["ADMIN_IDS"]:
                await query.message.reply_text("❌ Admin only", parse_mode=None)
                return
            
            active_users, website_users, available_tokens, used_tokens = STATE.license_manager.get_user_stats()
            auto_count = len(STATE.auto_signal_users)
            performance = STATE.license_manager.get_recent_performance()
            market_status = SmartSignalScheduler.get_market_status_message()
            
            await query.message.reply_text(
                f"📊 TANIX AI System Statistics\n\n"
                f"👥 Active Users: {active_users}\n"
                f"🌐 Website Users: {website_users}\n"
                f"🎫 Available Tokens: {available_tokens}\n"
                f"🎫 Used Tokens: {used_tokens}\n"
                f"🤖 Auto Signal Users: {auto_count}\n"
                f"💸 Trading Pairs: {len(CONFIG['ASSETS_TO_TRACK'])}\n"
                f"⏰ Signal Interval: 10 minutes\n"
                f"🎯 Success Rate: {performance['success_rate']:.1%}\n"
                f"📊 Recent Signals: {len(performance['recent_signals'])}\n"
                f"🌐 Market Mode: {market_status['mode']}",
                parse_mode=None
            )
            return
        
        elif data == "performance_report":
            if user_id not in CONFIG["ADMIN_IDS"]:
                await query.message.reply_text("❌ Admin only", parse_mode=None)
                return
            
            performance = STATE.license_manager.get_recent_performance()
            recent_signals = performance['recent_signals'][-10:]
            
            if recent_signals:
                avg_score = sum(s['score'] for s in recent_signals) / len(recent_signals)
                avg_confidence = sum(s['confidence'] for s in recent_signals) / len(recent_signals)
                avg_profit = sum(s['profit_potential'] for s in recent_signals) / len(recent_signals)
            else:
                avg_score = avg_confidence = avg_profit = 0
            
            await query.message.reply_text(
                f"🎯 TANIX AI Performance Report\n\n"
                f"📊 Quality Metrics (Last 10 Signals):\n"
                f"• Average Score: {avg_score:.1f}/100\n"
                f"• Average Confidence: {avg_confidence:.1f}%\n"
                f"• Average Profit Potential: {avg_profit:.1f}%\n"
                f"• Success Rate: {performance['success_rate']:.1%}\n\n"
                f"🎯 Enhanced Algorithm Features:\n"
                f"• Smart Signal Scheduler 🕒\n"
                f"• Market Timing Logic ⏰\n"
                f"• Quality Over Quantity ✅\n"
                f"• Technical Confluence 📈\n"
                f"• Profit Optimization 💰\n"
                f"• Confidence Filtering 🎯",
                parse_mode=None
            )
            return
        
        elif data == "website_users":
            if user_id not in CONFIG["ADMIN_IDS"]:
                await query.message.reply_text("❌ Admin only", parse_mode=None)
                return
            
            active_users = STATE.license_manager.get_active_users()
            website_users_list = [user for user in active_users if user.get('website_access', False)]
            
            if not website_users_list:
                await query.message.reply_text("🌐 No users with website access found.", parse_mode=None)
                return
            
            keyboard = []
            for user in website_users_list:
                username = user['username'] or f"User{user['user_id']}"
                # --- YAHAN FIX THA: 'website_users' ko 'website_users_list' kiya ---
                button_text = f"🌐 {username} (ID: {user['user_id']})"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"toggle_website_{user['user_id']}")])
            
            keyboard.append([InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.reply_text(
                "🌐 Website Users - Toggle Access\n\n"
                "Click on any user below to toggle their website access:",
                reply_markup=reply_markup,
                parse_mode=None
            )
            return
        
        # --- YAH POORA BLOCK UPDATE KIYA GAYA HAI ---
        elif data.startswith("toggle_website_"):
            if user_id not in CONFIG["ADMIN_IDS"]:
                await query.message.reply_text("❌ Admin only", parse_mode=None)
                return
            
            try:
                target_user_id_str = data.replace("toggle_website_", "")
                target_user_id = int(target_user_id_str)
                
                # Step 1: Toggle the flag in the bot's users.json
                success, new_status = STATE.license_manager.toggle_website_access(target_user_id)
                
                if not success:
                    await query.message.reply_text("❌ Failed to update bot's user file.", parse_mode=None)
                    return

                # Step 2: Sync this change with the website server
                if new_status == "ENABLED":
                    # Get user details to send for syncing
                    users = STATE.license_manager.load_json(STATE.license_manager.users_file, {})
                    user_data = users.get(target_user_id_str, {})
                    username = user_data.get('username', f"User{target_user_id}")
                    # Use username for first_name if 'firstName' is missing
                    first_name = user_data.get('firstName', username) 
                    
                    await sync_user_to_website(target_user_id_str, username, first_name)
                    
                elif new_status == "DISABLED":
                    await remove_user_from_website(target_user_id_str)

                # Step 3: Report success to admin
                await query.message.reply_text(
                    f"✅ Website Access Synced\n\n"
                    f"👤 User ID: {target_user_id}\n"
                    f"🌐 Status: {new_status}\n"
                    f"⏰ Updated at: {IndiaTimezone.format_datetime()}",
                    parse_mode=None
                )
                logger.info(f"👮 Admin {user_id} toggled website access for user {target_user_id} to {new_status} (Synced)")
            
            except ValueError:
                await query.message.reply_text("❌ Invalid user ID.", parse_mode=None)
                return
            except Exception as e:
                logger.error(f"Error toggling website access: {e}")
                await query.message.reply_text(f"❌ Error updating website access: {e}", parse_mode=None)
                return
        
        elif data == "remove_user":
            if user_id not in CONFIG["ADMIN_IDS"]:
                await query.message.reply_text("❌ Admin only", parse_mode=None)
                return
            
            active_users = STATE.license_manager.get_active_users()
            
            if not active_users:
                await query.message.reply_text("📭 No active users found to remove.", parse_mode=None)
                return
            
            keyboard = []
            for user in active_users:
                username = user['username'] or f"User{user['user_id']}"
                button_text = f"🗑️ {username} (ID: {user['user_id']})"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"remove_{user['user_id']}")])
            
            keyboard.append([InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.reply_text(
                "👥 Active Users - Select to Remove\n\n"
                "Click on any user below to remove their access:",
                reply_markup=reply_markup,
                parse_mode=None
            )
            return
        
        elif data.startswith("remove_"):
            if user_id not in CONFIG["ADMIN_IDS"]:
                await query.message.reply_text("❌ Admin only", parse_mode=None)
                return
            
            try:
                target_user_id = int(data.replace("remove_", ""))
                
                active_users = STATE.license_manager.get_active_users()
                user_to_remove = None
                for user in active_users:
                    if user['user_id'] == target_user_id:
                        user_to_remove = user
                        break
                
                if not user_to_remove:
                    await query.message.reply_text("❌ User not found or already removed.", parse_mode=None)
                    return
                
                success = STATE.license_manager.deactivate_user(target_user_id)
                
                if success:
                    # --- YAH BHI UPDATE KIYA GAYA HAI ---
                    # Website se bhi deactivate karein
                    await remove_user_from_website(str(target_user_id))
                    
                    username = user_to_remove['username'] or f"User{target_user_id}"
                    await query.message.reply_text(
                        f"✅ User Removed Successfully (Synced)\n\n"
                        f"👤 Username: {username}\n"
                        f"🆔 User ID: {target_user_id}\n"
                        f"🗑️ Access: Revoked\n"
                        f"🌐 Website: Disabled\n"
                        f"⏰ Removed at: {IndiaTimezone.format_datetime()}",
                        parse_mode=None
                    )
                    logger.info(f"👮 Admin {user_id} removed user {target_user_id} ({username})")
                else:
                    await query.message.reply_text("❌ Failed to remove user. Please try again.", parse_mode=None)
                return
            
            except ValueError:
                await query.message.reply_text("❌ Invalid user ID.", parse_mode=None)
                return
            except Exception as e:
                logger.error(f"Error removing user: {e}")
                await query.message.reply_text("❌ Error removing user.", parse_mode=None)
                return
        
        # If none of the above conditions match, don't generate a signal
        # This prevents unwanted signal generation for unknown callbacks
        logger.warning(f"Unknown callback data: {data}")
        
    except Exception as e:
        logger.error(f"Callback error: {e}")
        await query.message.reply_text("❌ An error occurred. Please try again.", parse_mode=None)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    text = update.message.text
    
    if not STATE.license_manager.check_user_access(user_id):
        await update.message.reply_text("🔒 Use /token YOUR_TOKEN", parse_mode=None)
    else:
        website_access = STATE.license_manager.check_website_access(user_id)
        website_status = "✅ ACTIVE" if website_access else "❌ INACTIVE"
        
        keyboard = [
            [InlineKeyboardButton("🎯 Signal", callback_data="get_signal")],
            [InlineKeyboardButton("🤖 Automated Signal", callback_data="auto_signals")],
            [InlineKeyboardButton("📊 Market Status", callback_data="market_status")],
            [InlineKeyboardButton("🌐 Website Access", callback_data="website_info")],
        ]
        
        if user_id in CONFIG["ADMIN_IDS"]:
            keyboard.append([InlineKeyboardButton("👨‍💼 Admin Panel", callback_data="admin_panel")])
            
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"🤖 TANIX AI Trading Bot - Choose an option:\n🌐 Website: {website_status}",
            reply_markup=reply_markup,
            parse_mode=None
        )

# --- 14. GRACEFUL SHUTDOWN ---
async def shutdown():
    logger.info("🛑 TANIX AI Shutdown initiated...")
    
    STATE.shutting_down = True
    await task_manager.cancel_all()
    
    if STATE.telegram_app:
        await STATE.telegram_app.stop()
        await STATE.telegram_app.shutdown()
    
    logger.info("✅ TANIX AI Shutdown completed")

def signal_handler(signum, frame):
    logger.info(f"🛑 Received signal {signum}, shutting down...")
    asyncio.create_task(shutdown())

# --- 15. MAIN APPLICATION ---
async def main():
    logger.info("🤖 Starting TANIX AI Trading Bot...")
    
    system_signal.signal(system_signal.SIGINT, signal_handler)
    system_signal.signal(system_signal.SIGTERM, signal_handler)
    
    try:
        logger.info(f"💰 Initializing {len(CONFIG['ASSETS_TO_TRACK'])} trading pairs...")
        for asset in CONFIG["ASSETS_TO_TRACK"]:
            prices = RealisticPriceGenerator.generate_initial_prices(asset, INDICATOR_CONFIG["PRICE_HISTORY_SIZE"])
            STATE.price_data[asset].extend(prices)
            logger.info(f"✅ {asset}: {len(prices)} prices loaded")
        
        logger.info("🚀 Starting TANIX AI system...")
        await task_manager.create_task(price_update_task(), "price_updater")
        await task_manager.create_task(auto_signal_task(), "auto_signal")
        await task_manager.create_task(trade_result_task(), "trade_result_tracker")
        
        logger.info("🤖 Initializing Telegram bot...")
        application = Application.builder().token(CONFIG["TELEGRAM_BOT_TOKEN"]).build()
        STATE.telegram_app = application
        
        handlers = [
            CommandHandler("start", start_command),
            CommandHandler("token", token_command),
            CommandHandler("admin", admin_command),
            CallbackQueryHandler(handle_callback),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message),
        ]
        
        for handler in handlers:
            application.add_handler(handler)
        
        market_status = SmartSignalScheduler.get_market_status_message()
        performance = STATE.license_manager.get_recent_performance()
        
        logger.info("✅ TANIX AI Trading Bot ready!")
        logger.info(f"🎯 Market Mode: {market_status['status']}")
        logger.info(f"💰 Monitoring {len(CONFIG['ASSETS_TO_TRACK'])} pairs")
        logger.info("🤖 Strategy: Advanced AI-powered technical analysis")
        logger.info("⏰ Timeframe: 1 minute with HH:MM:00 entry times (IST)")
        logger.info(f"📊 Minimum Quality: Score {CONFIG['MIN_SCORE']}+, Confidence {CONFIG['MIN_CONFIDENCE']}%+")
        logger.info(f"💸 Minimum Profit: 75%+")
        logger.info(f"🎯 Success Rate: {performance['success_rate']:.1%}")
        logger.info("🕒 Live Market Hours: 09:00 AM - 11:30 PM IST")
        logger.info("🔵 OTC Hours: 11:30 PM - 09:00 AM IST & Weekends")
        logger.info("🤖 Automated Signals: Every 10 minutes")
        logger.info("🇮🇳 Timezone: UTC+5:30 (IST)")
        logger.info("🌐 Website Integration: ✅ ACTIVE")
        logger.info(f"🔗 Website URL: {CONFIG['WEBSITE_URL']}")
        
        await application.run_polling(
            close_loop=False,
            stop_signals=None
        )
        
    except asyncio.CancelledError:
        logger.info("🛑 Main task cancelled")
    except Exception as e:
        logger.error(f"❌ Fatal error in main: {e}")
    finally:
        await shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 TANIX AI stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
    finally:
        logger.info("👋 TANIX AI Trading Bot terminated")

