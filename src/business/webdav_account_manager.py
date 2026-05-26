import base64
import uuid
from typing import List, Optional

from src.core.database_service import DatabaseService
from src.infrastructure.webdav_client import WebDAVClient
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class WebDAVAccountManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._db = DatabaseService()
        self._initialized = True

    def add_account(self, data: dict) -> str:
        account_id = data.get("id") or uuid.uuid4().hex[:12]
        name = data.get("name", "WebDAV")
        server_url = data.get("server_url", "").rstrip("/")
        username = data.get("username", "")
        password = self._encode_password(data.get("password", ""))
        root_path = data.get("root_path", "/")
        is_ssl = 1 if data.get("is_ssl", True) else 0
        verify_ssl = 1 if data.get("verify_ssl", False) else 0
        timeout = int(data.get("timeout", 30))
        cache_ttl = int(data.get("cache_ttl", 600))
        preset = data.get("preset", "")

        max_order = self._db.fetchone(
            "SELECT MAX(sort_order) as mo FROM webdav_accounts", ()
        )
        sort_order = (max_order["mo"] or 0) + 1 if max_order and max_order["mo"] is not None else 1

        self._db.insert("webdav_accounts", {
            "id": account_id,
            "name": name,
            "server_url": server_url,
            "username": username,
            "password": password,
            "root_path": root_path,
            "is_ssl": is_ssl,
            "verify_ssl": verify_ssl,
            "timeout": timeout,
            "cache_ttl": cache_ttl,
            "preset": preset,
            "sort_order": sort_order,
        })

        logger.info(f"Added WebDAV account: {name} ({account_id})")
        return account_id

    def update_account(self, account_id: str, data: dict) -> bool:
        existing = self._db.fetchone(
            "SELECT * FROM webdav_accounts WHERE id = ?",
            (account_id,)
        )
        if not existing:
            return False

        updates = {}
        for key in ("name", "server_url", "username", "root_path", "preset"):
            if key in data:
                updates[key] = data[key]

        if "server_url" in updates:
            updates["server_url"] = updates["server_url"].rstrip("/")

        if "password" in data:
            updates["password"] = self._encode_password(data["password"])

        for key in ("is_ssl", "verify_ssl"):
            if key in data:
                updates[key] = 1 if data[key] else 0

        for key in ("timeout", "cache_ttl"):
            if key in data:
                updates[key] = int(data[key])

        if updates:
            self._db.update("webdav_accounts", updates, "id = ?", (account_id,))
            logger.info(f"Updated WebDAV account: {account_id}")

        return True

    def delete_account(self, account_id: str) -> bool:
        existing = self._db.fetchone(
            "SELECT * FROM webdav_accounts WHERE id = ?",
            (account_id,)
        )
        if not existing:
            return False
        self._db.delete("webdav_accounts", "id = ?", (account_id,))
        logger.info(f"Deleted WebDAV account: {account_id}")
        return True

    def get_all_accounts(self) -> List[dict]:
        rows = self._db.fetchall(
            "SELECT * FROM webdav_accounts ORDER BY sort_order, created_at",
            ()
        )
        result = []
        for row in rows:
            account = dict(row)
            account["password"] = self._decode_password(account.get("password", ""))
            result.append(account)
        return result

    def get_account(self, account_id: str) -> Optional[dict]:
        row = self._db.fetchone(
            "SELECT * FROM webdav_accounts WHERE id = ?",
            (account_id,)
        )
        if not row:
            return None
        account = dict(row)
        account["password"] = self._decode_password(account.get("password", ""))
        return account

    def test_connection(self, account_id: str) -> tuple:
        account = self.get_account(account_id)
        if not account:
            return False, "账户不存在"
        return WebDAVClient.test_connection(
            server_url=account["server_url"],
            username=account["username"],
            password=account["password"],
            timeout=account.get("timeout", 30),
            verify_ssl=bool(account.get("verify_ssl", 0)),
        )

    def reorder_accounts(self, ordered_ids: List[str]) -> bool:
        try:
            for idx, aid in enumerate(ordered_ids):
                self._db.update("webdav_accounts", {"sort_order": idx}, "id = ?", (aid,))
            return True
        except Exception as e:
            logger.error(f"Failed to reorder WebDAV accounts: {e}")
            return False

    @staticmethod
    def _encode_password(password: str) -> str:
        return base64.b64encode(password.encode()).decode()

    @staticmethod
    def _decode_password(encoded: str) -> str:
        try:
            return base64.b64decode(encoded).decode()
        except Exception:
            return encoded
