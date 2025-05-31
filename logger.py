import logging
import sys
from datetime import datetime
from typing import Optional, Any
from colorama import Fore, Back, Style, init
import os

# Initialize colorama
init(autoreset=True)

class BetBogLogger:
    """Advanced colored logger for BetBog monitoring system"""
    
    def __init__(self, category: str = "SYSTEM", log_file: Optional[str] = None):
        self.category = category
        self.log_file = log_file or "betbog.log"
        
        # Setup file logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.file_logger = logging.getLogger(f"BetBog.{category}")
        
        # Color mappings
        self.colors = {
            'header': Fore.CYAN + Style.BRIGHT,
            'success': Fore.GREEN + Style.BRIGHT,
            'warning': Fore.YELLOW + Style.BRIGHT,
            'error': Fore.RED + Style.BRIGHT,
            'info': Fore.WHITE,
            'debug': Fore.LIGHTBLACK_EX,
            'strategy': Fore.MAGENTA + Style.BRIGHT,
            'api': Fore.BLUE + Style.BRIGHT,
            'ml': Fore.LIGHTGREEN_EX + Style.BRIGHT,
            'bot': Fore.LIGHTYELLOW_EX + Style.BRIGHT
        }
        
        self.box_chars = {
            'top_left': '╭',
            'top_right': '╮',
            'bottom_left': '╰',
            'bottom_right': '╯',
            'horizontal': '─',
            'vertical': '│',
            'cross': '┼'
        }
    
    def _create_box(self, message: str, color: str, width: int = 80) -> str:
        """Create a colored box around message"""
        lines = message.split('\n')
        max_line_length = max(len(line) for line in lines) if lines else 0
        box_width = min(max(max_line_length + 4, 40), width)
        
        # Top border
        top_border = (self.box_chars['top_left'] + 
                     self.box_chars['horizontal'] * (box_width - 2) + 
                     self.box_chars['top_right'])
        
        # Bottom border
        bottom_border = (self.box_chars['bottom_left'] + 
                        self.box_chars['horizontal'] * (box_width - 2) + 
                        self.box_chars['bottom_right'])
        
        # Content lines
        content_lines = []
        for line in lines:
            padded_line = line.ljust(box_width - 4)
            content_lines.append(f"{self.box_chars['vertical']} {padded_line} {self.box_chars['vertical']}")
        
        # Combine all parts with color
        box_content = [
            color + top_border,
            *[color + line for line in content_lines],
            color + bottom_border + Style.RESET_ALL
        ]
        
        return '\n'.join(box_content)
    
    def _log_to_file(self, level: str, message: str):
        """Log message to file without colors"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        clean_message = f"[{self.category}] {message}"
        
        if level == "INFO":
            self.file_logger.info(clean_message)
        elif level == "WARNING":
            self.file_logger.warning(clean_message)
        elif level == "ERROR":
            self.file_logger.error(clean_message)
        elif level == "DEBUG":
            self.file_logger.debug(clean_message)
    
    def header(self, message: str):
        """Log header message with prominent styling"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"🏆 [{timestamp}] [{self.category}] {message}"
        box = self._create_box(formatted_message, self.colors['header'])
        print(box)
        self._log_to_file("INFO", message)
    
    def success(self, message: str):
        """Log success message"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"✅ [{timestamp}] [{self.category}] {message}"
        print(self.colors['success'] + formatted_message + Style.RESET_ALL)
        self._log_to_file("INFO", message)
    
    def info(self, message: str):
        """Log info message"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"ℹ️  [{timestamp}] [{self.category}] {message}"
        print(self.colors['info'] + formatted_message + Style.RESET_ALL)
        self._log_to_file("INFO", message)
    
    def warning(self, message: str):
        """Log warning message"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"⚠️  [{timestamp}] [{self.category}] {message}"
        print(self.colors['warning'] + formatted_message + Style.RESET_ALL)
        self._log_to_file("WARNING", message)
    
    def error(self, message: str):
        """Log error message"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"❌ [{timestamp}] [{self.category}] {message}"
        box = self._create_box(formatted_message, self.colors['error'])
        print(box)
        self._log_to_file("ERROR", message)
    
    def debug(self, message: str):
        """Log debug message"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"🔍 [{timestamp}] [{self.category}] {message}"
        print(self.colors['debug'] + formatted_message + Style.RESET_ALL)
        self._log_to_file("DEBUG", message)
    
    def strategy_signal(self, strategy: str, signal_type: str, confidence: float, details: str = ""):
        """Log strategy signal with special formatting"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        signal_message = f"🎯 SIGNAL DETECTED!\n"
        signal_message += f"Strategy: {strategy}\n"
        signal_message += f"Type: {signal_type}\n"
        signal_message += f"Confidence: {confidence:.1%}\n"
        if details:
            signal_message += f"Details: {details}"
        
        box = self._create_box(signal_message, self.colors['strategy'])
        print(box)
        self._log_to_file("INFO", f"SIGNAL: {strategy} - {signal_type} - {confidence:.1%}")
    
    def api_request(self, endpoint: str, status: str, details: str = ""):
        """Log API request with special formatting"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        status_icon = "✅" if status == "success" else "❌"
        color = self.colors['success'] if status == "success" else self.colors['error']
        
        message = f"{status_icon} [{timestamp}] [API] {endpoint} - {status.upper()}"
        if details:
            message += f" - {details}"
        
        print(color + message + Style.RESET_ALL)
        self._log_to_file("INFO", f"API: {endpoint} - {status}")
    
    def ml_update(self, strategy: str, performance: dict, details: str = ""):
        """Log ML model update"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        ml_message = f"🤖 ML MODEL UPDATE\n"
        ml_message += f"Strategy: {strategy}\n"
        ml_message += f"Accuracy: {performance.get('accuracy', 0):.1%}\n"
        ml_message += f"F1 Score: {performance.get('f1', 0):.1%}\n"
        if details:
            ml_message += f"Details: {details}"
        
        box = self._create_box(ml_message, self.colors['ml'])
        print(box)
        self._log_to_file("INFO", f"ML UPDATE: {strategy} - Acc: {performance.get('accuracy', 0):.1%}")
    
    def bot_notification(self, chat_id: str, message_type: str, success: bool):
        """Log bot notification"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        status_icon = "✅" if success else "❌"
        color = self.colors['success'] if success else self.colors['error']
        
        formatted_message = f"{status_icon} [{timestamp}] [BOT] Notification to {chat_id}: {message_type}"
        print(color + formatted_message + Style.RESET_ALL)
        self._log_to_file("INFO", f"BOT: {message_type} to {chat_id} - {'Success' if success else 'Failed'}")
    
    def match_update(self, match_id: str, home_team: str, away_team: str, minute: int, score: str):
        """Log match update"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        message = f"⚽ [{timestamp}] MATCH UPDATE: {home_team} vs {away_team} | {score} | {minute}'"
        print(self.colors['info'] + message + Style.RESET_ALL)
        self._log_to_file("INFO", f"MATCH: {match_id} - {score} - {minute}'")
    
    def profit_loss_update(self, strategy: str, profit: float, total_signals: int, win_rate: float):
        """Log profit/loss update"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        profit_color = self.colors['success'] if profit >= 0 else self.colors['error']
        profit_icon = "💰" if profit >= 0 else "📉"
        
        pl_message = f"{profit_icon} P&L UPDATE\n"
        pl_message += f"Strategy: {strategy}\n"
        pl_message += f"Profit: {profit:+.2f} units\n"
        pl_message += f"Signals: {total_signals}\n"
        pl_message += f"Win Rate: {win_rate:.1%}"
        
        box = self._create_box(pl_message, profit_color)
        print(box)
        self._log_to_file("INFO", f"P&L: {strategy} - {profit:+.2f} units - {win_rate:.1%}")
    
    def system_startup(self, components: list):
        """Log system startup"""
        startup_message = "🚀 BETBOG SYSTEM STARTUP\n"
        startup_message += f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        startup_message += "Components:\n"
        for component in components:
            startup_message += f"  ✓ {component}\n"
        startup_message += "System ready for monitoring!"
        
        box = self._create_box(startup_message, self.colors['header'])
        print(box)
        self._log_to_file("INFO", "SYSTEM STARTUP COMPLETE")
    
    def system_shutdown(self, reason: str = "Normal shutdown"):
        """Log system shutdown"""
        shutdown_message = f"🛑 BETBOG SYSTEM SHUTDOWN\n"
        shutdown_message += f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        shutdown_message += f"Reason: {reason}"
        
        box = self._create_box(shutdown_message, self.colors['warning'])
        print(box)
        self._log_to_file("INFO", f"SYSTEM SHUTDOWN: {reason}")

# Global logger instance
main_logger = BetBogLogger("MAIN")
