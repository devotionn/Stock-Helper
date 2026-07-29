"""密钥存储抽象层：根据平台使用系统凭据管理器或环境变量/数据库"""
import os
import sys
from abc import ABC, abstractmethod


class SecretStore(ABC):
    """密钥存储抽象接口"""

    @abstractmethod
    def get_secret(self, key: str) -> str:
        pass

    @abstractmethod
    def set_secret(self, key: str, value: str) -> None:
        pass

    @abstractmethod
    def has_secret(self, key: str) -> bool:
        pass

    @abstractmethod
    def delete_secret(self, key: str) -> None:
        pass


class DevelopmentSecretStore(SecretStore):
    """开发环境：使用环境变量，fallback到数据库settings表。
    get_secret 先查环境变量 STOCK_{key.upper()}，没有则查数据库settings表。
    set_secret 写入数据库settings表（开发环境不写环境变量）。"""

    def get_secret(self, key: str) -> str:
        env_val = os.environ.get(f"STOCK_{key.upper()}")
        if env_val:
            return env_val
        return self._db_get(key)

    def set_secret(self, key: str, value: str) -> None:
        from ..database import get_db
        with get_db() as conn:
            conn.execute(
                "INSERT INTO settings (key, value, updated_at) "
                "VALUES (?, ?, datetime('now','localtime')) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                "updated_at=excluded.updated_at",
                (key, value),
            )

    def has_secret(self, key: str) -> bool:
        if os.environ.get(f"STOCK_{key.upper()}"):
            return True
        return bool(self._db_get(key))

    def delete_secret(self, key: str) -> None:
        from ..database import get_db
        with get_db() as conn:
            conn.execute("DELETE FROM settings WHERE key=?", (key,))

    @staticmethod
    def _db_get(key: str) -> str:
        from ..database import get_db
        with get_db() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key=?", (key,)
            ).fetchone()
        return row["value"] if row else ""


class _KeyringSecretStore(SecretStore):
    """基于keyring库的密钥存储基类（Windows凭据管理器 / macOS Keychain）。
    keyring不可用时回退到 DevelopmentSecretStore。"""
    SERVICE_NAME = "StockHelper"

    def __init__(self):
        self._fallback = DevelopmentSecretStore()
        try:
            import keyring
            self._keyring = keyring
        except ImportError:
            if getattr(sys, 'frozen', False):
                raise RuntimeError("Keyring 不可用，无法安全存储密钥")
            print("警告：keyring 不可用，回退到开发环境密钥存储（不安全）")
            self._keyring = None

    def get_secret(self, key: str) -> str:
        if self._keyring is None:
            return self._fallback.get_secret(key)
        val = self._keyring.get_password(self.SERVICE_NAME, key)
        return val if val else ""

    def set_secret(self, key: str, value: str) -> None:
        if self._keyring is None:
            return self._fallback.set_secret(key, value)
        self._keyring.set_password(self.SERVICE_NAME, key, value)

    def has_secret(self, key: str) -> bool:
        if self._keyring is None:
            return self._fallback.has_secret(key)
        return self._keyring.get_password(self.SERVICE_NAME, key) is not None

    def delete_secret(self, key: str) -> None:
        if self._keyring is None:
            return self._fallback.delete_secret(key)
        try:
            self._keyring.delete_password(self.SERVICE_NAME, key)
        except Exception:
            pass


class WindowsCredentialStore(_KeyringSecretStore):
    """Windows凭据管理器（使用keyring库）"""


class MacKeychainStore(_KeyringSecretStore):
    """macOS Keychain（使用keyring库）"""


def get_secret_store() -> SecretStore:
    """根据平台返回合适的SecretStore"""
    if sys.platform == "darwin":
        return MacKeychainStore()
    elif sys.platform == "win32":
        return WindowsCredentialStore()
    else:
        return DevelopmentSecretStore()
