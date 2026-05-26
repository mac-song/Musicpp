import threading
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class EventBus:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._subscribers: Dict[str, List[Dict]] = defaultdict(list)
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="eventbus")
        self._initialized = True

    def subscribe(
        self,
        event_type: str,
        callback: Callable,
        priority: int = 0
    ) -> str:
        subscribe_id = str(uuid.uuid4())
        with self._lock:
            self._subscribers[event_type].append({
                "id": subscribe_id,
                "callback": callback,
                "priority": priority
            })
            self._subscribers[event_type].sort(
                key=lambda x: x["priority"],
                reverse=True
            )
        logger.debug(f"Subscribed to {event_type}, id={subscribe_id}")
        return subscribe_id

    def unsubscribe(self, subscribe_id: str) -> bool:
        with self._lock:
            for event_type, subs in self._subscribers.items():
                for i, sub in enumerate(subs):
                    if sub["id"] == subscribe_id:
                        subs.pop(i)
                        logger.debug(f"Unsubscribed {subscribe_id} from {event_type}")
                        return True
        return False

    def publish(
        self,
        event_type: str,
        data: Optional[Dict[str, Any]] = None,
        sync: bool = True
    ) -> None:
        data = data or {}
        subscribers = []
        with self._lock:
            subscribers = list(self._subscribers.get(event_type, []))

        if not subscribers:
            return

        if sync:
            self._notify_subscribers(event_type, subscribers, data)
        else:
            self._executor.submit(
                self._notify_subscribers, event_type, subscribers, data
            )

    def _notify_subscribers(
        self,
        event_type: str,
        subscribers: List[Dict],
        data: Dict[str, Any]
    ) -> None:
        for sub in subscribers:
            try:
                sub["callback"](data)
            except Exception as e:
                logger.error(
                    f"Error notifying subscriber {sub['id']} for {event_type}: {e}"
                )

