"""Telegram Circuit Breaker - Fault Isolation for Notifications"""

import os
import logging
import time
from enum import Enum
from typing import Optional

try:
    import telegram

    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logging.warning("python-telegram-bot not installed - Telegram will be disabled")


class CircuitState(Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Rejecting requests
    HALF_OPEN = "half_open"  # Testing recovery
    DISABLED = "disabled"  # Permanently disabled


class TelegramCircuitBreaker:
    """
    Circuit breaker pattern for Telegram operations.
    Prevents cascading failures from Telegram errors.
    """

    def __init__(self, failure_threshold=3, cooldown_seconds=300):
        self.logger = logging.getLogger("telegram")
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.last_failure_time = None

        if not TELEGRAM_AVAILABLE:
            self.logger.warning("Telegram library not available - disabling")
            self.state = CircuitState.DISABLED
            self.bot = None
            return

        # Load credentials from environment
        self.token = os.getenv("FREQTRADE__TELEGRAM__TOKEN")
        self.chat_id = os.getenv("FREQTRADE__TELEGRAM__CHAT_ID")

        if not self.token or not self.chat_id:
            self.logger.warning("Telegram credentials not found - disabling")
            self.state = CircuitState.DISABLED
            self.bot = None
        else:
            try:
                self.bot = telegram.Bot(token=self.token)
            except Exception as e:
                self.logger.error(f"Failed to initialize Telegram bot: {e}")
                self.state = CircuitState.DISABLED
                self.bot = None

    def test_connection(self) -> bool:
        """Test if Telegram is reachable."""
        if self.state == CircuitState.DISABLED or not self.bot:
            return False

        try:
            me = self.bot.get_me()
            self.logger.info(f"Connected to bot: {me.username}")
            return True
        except Exception as e:
            if TELEGRAM_AVAILABLE and hasattr(telegram.error, "Conflict"):
                if isinstance(e, telegram.error.Conflict):
                    self.logger.error("Telegram Conflict - another instance is running")
                    self.state = CircuitState.DISABLED
                    return False
            self.logger.warning(f"Telegram connection test failed: {e}")
            return False

    def send_message(self, text: str, parse_mode: Optional[str] = None) -> bool:
        """
        Send message through circuit breaker.
        Returns True if sent, False if blocked/failed.
        """
        if self.state == CircuitState.DISABLED or not self.bot:
            self.logger.debug("Telegram disabled - message not sent")
            return False

        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.logger.info("Attempting to recover Telegram connection")
                self.state = CircuitState.HALF_OPEN
            else:
                # Still cooling down
                return False

        try:
            self.bot.send_message(
                chat_id=self.chat_id, text=text, parse_mode=parse_mode
            )
            self._on_success()
            return True

        except Exception as e:
            # Handle different error types
            error_type = type(e).__name__

            if TELEGRAM_AVAILABLE and hasattr(telegram.error, "Conflict"):
                if isinstance(e, telegram.error.Conflict):
                    self.logger.error(f"Telegram Conflict: {e}")
                    self.logger.error(
                        "Another bot instance detected - permanently disabling"
                    )
                    self.state = CircuitState.DISABLED
                    return False

                if isinstance(e, telegram.error.NetworkError):
                    self.logger.warning(f"Telegram Network Error: {e}")
                    self._on_failure("Network error")
                    return False

            # Generic error handling (includes parsing errors)
            self.logger.warning(f"Telegram error ({error_type}): {e}")
            self._on_failure(str(e))
            return False

    def _on_success(self):
        """Reset circuit breaker on successful call."""
        if self.state == CircuitState.HALF_OPEN:
            self.logger.info("✅ Telegram recovered")

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None

    def _on_failure(self, error_msg: str):
        """Handle failure."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        self.logger.warning(
            f"Telegram failure {self.failure_count}/{self.failure_threshold}: {error_msg}"
        )

        if self.failure_count >= self.failure_threshold:
            self.logger.error("Failure threshold reached - opening circuit")
            self.state = CircuitState.OPEN
        elif self.state == CircuitState.HALF_OPEN:
            # Failed during recovery attempt
            self.logger.warning("Recovery failed - reopening circuit")
            self.state = CircuitState.OPEN

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if not self.last_failure_time:
            return True

        elapsed = time.time() - self.last_failure_time
        return elapsed >= self.cooldown_seconds

    def get_status(self) -> dict:
        """Get current circuit breaker status."""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "operational": self.state == CircuitState.CLOSED,
        }
