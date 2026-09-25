"""ذخیره‌ی وضعیت فرم‌ها در SQLite تا با ری‌استارت وب‌اپ از بین نرود."""
import json
import sqlite3
from typing import Any, Dict, Optional

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey


class SQLiteStorage(BaseStorage):
    def __init__(self, path: str):
        self.path = path
        with sqlite3.connect(self.path) as c:
            c.execute("CREATE TABLE IF NOT EXISTS fsm (k TEXT PRIMARY KEY, state TEXT, data TEXT)")

    @staticmethod
    def _k(key: StorageKey) -> str:
        return f"{key.bot_id}:{key.chat_id}:{key.user_id}:{key.thread_id}:{key.business_connection_id}:{key.destiny}"

    def _row(self, key: StorageKey):
        with sqlite3.connect(self.path) as c:
            return c.execute("SELECT state, data FROM fsm WHERE k=?", (self._k(key),)).fetchone()

    async def set_state(self, key: StorageKey, state=None) -> None:
        st = state.state if isinstance(state, State) else state
        k = self._k(key)
        with sqlite3.connect(self.path) as c:
            c.execute("INSERT OR IGNORE INTO fsm (k, state, data) VALUES (?, NULL, '{}')", (k,))
            c.execute("UPDATE fsm SET state=? WHERE k=?", (st, k))

    async def get_state(self, key: StorageKey) -> Optional[str]:
        row = self._row(key)
        return row[0] if row else None

    async def set_data(self, key: StorageKey, data: Dict[str, Any]) -> None:
        k = self._k(key)
        with sqlite3.connect(self.path) as c:
            c.execute("INSERT OR IGNORE INTO fsm (k, state, data) VALUES (?, NULL, '{}')", (k,))
            c.execute("UPDATE fsm SET data=? WHERE k=?", (json.dumps(data, ensure_ascii=False), k))

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        row = self._row(key)
        return json.loads(row[1]) if row and row[1] else {}

    async def close(self) -> None:
        pass
