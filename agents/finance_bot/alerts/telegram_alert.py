import requests
from utils.logger import setup_logger

logger = setup_logger("telegram")


class TelegramAlert:
    def __init__(self, token: str, chat_id: str):
        self.chat_id = chat_id
        self._url = f"https://api.telegram.org/bot{token}/sendMessage"

    def send(self, message: str) -> bool:
        try:
            resp = requests.post(
                self._url,
                json={"chat_id": self.chat_id, "text": message, "parse_mode": "Markdown"},
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"发送失败: {e}")
            return False
