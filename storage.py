import logging
import os
import threading
import time
import uuid
from typing import Dict, List, Optional

from sqlalchemy import or_

from database import AlertEvent, session_scope

LOGGER = logging.getLogger(__name__)

def _serialize_event(event: AlertEvent) -> Dict[str, object]:
    return {
        "event_id": event.event_id,
        "behavior_key": event.behavior_key,
        "behavior_name": event.behavior_name,
        "duration_seconds": round(event.duration_seconds, 1),
        "timestamp": event.event_timestamp,
        "count": event.count,
        "snapshot_path": event.snapshot_path,
        "user_id": event.user_id,
        "job_id": event.job_id,
    }


def _build_summary_from_events(
    events: List[Dict[str, object]],
    recent_limit: int = 10,
    timeline_limit: int = 8,
) -> Dict[str, object]:
    total_events = len(events)
    behavior_totals: Dict[str, Dict[str, object]] = {}
    recent_events = events[:recent_limit]
    recent_distribution: Dict[str, int] = {}
    latest_event = events[0] if events else None

    for event in events:
        key = event["behavior_key"]
        item = behavior_totals.setdefault(
            key,
            {
                "behavior_key": key,
                "behavior_name": event["behavior_name"],
                "count": 0,
            },
        )
        item["count"] += 1

    for event in recent_events:
        key = event["behavior_key"]
        recent_distribution[key] = recent_distribution.get(key, 0) + 1

    trend_items = []
    denominator = len(recent_events) or 1
    for item in sorted(
        behavior_totals.values(), key=lambda value: value["count"], reverse=True
    ):
        recent_count = recent_distribution.get(item["behavior_key"], 0)
        trend_items.append(
            {
                "behavior_key": item["behavior_key"],
                "behavior_name": item["behavior_name"],
                "total_count": item["count"],
                "recent_count": recent_count,
                "recent_ratio": round(recent_count / denominator, 2),
            }
        )

    recent_timeline = [
        {
            "behavior_key": event["behavior_key"],
            "behavior_name": event["behavior_name"],
            "timestamp": event["timestamp"],
            "duration_seconds": event["duration_seconds"],
            "count": event["count"],
        }
        for event in events[:timeline_limit]
    ]

    trend_chart = [
        {
            "behavior_key": event["behavior_key"],
            "behavior_name": event["behavior_name"],
            "time_label": time.strftime("%H:%M:%S", time.localtime(event["timestamp"])),
            "count": event["count"],
            "duration_seconds": event["duration_seconds"],
            "bar_value": min(
                100,
                max(
                    12,
                    int(event["count"] * 18 + event["duration_seconds"] * 10),
                ),
            ),
        }
        for event in reversed(events[:timeline_limit])
    ]

    return {
        "recent_alert_count": len(recent_events),
        "total_alert_count": total_events,
        "behavior_totals": sorted(
            behavior_totals.values(),
            key=lambda value: value["count"],
            reverse=True,
        ),
        "trend_items": trend_items,
        "recent_timeline": recent_timeline,
        "trend_chart": trend_chart,
        "latest_event": latest_event,
    }


class EventStorage:
    def __init__(
        self,
        session_factory,
        snapshot_dir: str = "data/alerts",
        max_events: int = 1000,
    ):
        self.session_factory = session_factory
        self.snapshot_dir = snapshot_dir
        self.max_events = max_events
        self._lock = threading.Lock()
        self._ensure_storage()

    def _ensure_storage(self) -> None:
        os.makedirs(self.snapshot_dir, exist_ok=True)

    def _snapshot_file_path(self, snapshot_path: Optional[str]) -> Optional[str]:
        if not snapshot_path:
            return None
        filename = os.path.basename(snapshot_path)
        if not filename:
            return None
        return os.path.join(self.snapshot_dir, filename)

    def _delete_snapshot_file(self, snapshot_path: Optional[str]) -> None:
        file_path = self._snapshot_file_path(snapshot_path)
        if not file_path:
            return
        try:
            os.remove(file_path)
        except FileNotFoundError:
            return
        except OSError:
            LOGGER.debug("Failed to delete snapshot file %s", file_path, exc_info=True)

    def _apply_scope(
        self,
        query,
        user_id: Optional[int] = None,
        include_public: bool = False,
        job_id: Optional[str] = None,
        only_public: bool = False,
    ):
        if job_id is not None:
            return query.filter(AlertEvent.job_id == job_id)
        if only_public:
            return query.filter(AlertEvent.user_id.is_(None))
        if user_id is None:
            return query
        if include_public:
            return query.filter(
                or_(AlertEvent.user_id == user_id, AlertEvent.user_id.is_(None))
            )
        return query.filter(AlertEvent.user_id == user_id)

    def _retention_scope_query(
        self,
        session,
        user_id: Optional[int] = None,
        job_id: Optional[str] = None,
    ):
        query = session.query(AlertEvent)
        if job_id is not None:
            query = query.filter(AlertEvent.job_id == job_id)
            if user_id is None:
                return query.filter(AlertEvent.user_id.is_(None))
            return query.filter(AlertEvent.user_id == user_id)

        query = query.filter(AlertEvent.job_id.is_(None))
        if user_id is None:
            return query.filter(AlertEvent.user_id.is_(None))
        return query.filter(AlertEvent.user_id == user_id)

    def build_snapshot_filename(
        self,
        behavior_key: str,
        timestamp: float,
        prefix: Optional[str] = None,
    ) -> str:
        time_label = time.strftime("%Y%m%d_%H%M%S", time.localtime(timestamp))
        stem = f"{behavior_key}_{time_label}"
        if prefix:
            stem = f"{prefix}_{stem}"
        return f"{stem}.jpg"

    def record_event(
        self,
        behavior_key: str,
        behavior_name: str,
        duration_seconds: float,
        timestamp: float,
        count: int,
        snapshot_path: Optional[str] = None,
        user_id: Optional[int] = None,
        job_id: Optional[str] = None,
    ) -> Dict[str, object]:
        unique_suffix = uuid.uuid4().hex[:8]
        event_id = f"{job_id or 'public'}-{behavior_key}-{int(timestamp * 1000)}-{unique_suffix}"
        with self._lock:
            with session_scope(self.session_factory) as session:
                event = AlertEvent(
                    event_id=event_id,
                    behavior_key=behavior_key,
                    behavior_name=behavior_name,
                    duration_seconds=round(duration_seconds, 1),
                    event_timestamp=timestamp,
                    count=count,
                    snapshot_path=snapshot_path,
                    user_id=user_id,
                    job_id=job_id,
                )
                session.add(event)
                session.flush()

                scoped_events = self._retention_scope_query(
                    session,
                    user_id=user_id,
                    job_id=job_id,
                )
                total_count = scoped_events.count()
                if total_count > self.max_events:
                    removable_events = (
                        scoped_events
                        .order_by(AlertEvent.event_timestamp.asc(), AlertEvent.id.asc())
                        .limit(total_count - self.max_events)
                        .all()
                    )
                    for removable_event in removable_events:
                        self._delete_snapshot_file(removable_event.snapshot_path)
                        session.delete(removable_event)

                payload = _serialize_event(event)
        return payload

    def list_events(
        self,
        limit: int = 20,
        user_id: Optional[int] = None,
        include_public: bool = False,
        job_id: Optional[str] = None,
        only_public: bool = False,
    ) -> List[Dict[str, object]]:
        with session_scope(self.session_factory) as session:
            query = session.query(AlertEvent)
            query = self._apply_scope(
                query,
                user_id=user_id,
                include_public=include_public,
                job_id=job_id,
                only_public=only_public,
            )
            events = (
                query.order_by(AlertEvent.event_timestamp.desc(), AlertEvent.id.desc())
                .limit(limit)
                .all()
            )
            return [_serialize_event(event) for event in events]

    def get_latest_snapshot(
        self,
        user_id: Optional[int] = None,
        include_public: bool = False,
        job_id: Optional[str] = None,
        only_public: bool = False,
    ) -> Optional[Dict[str, object]]:
        with session_scope(self.session_factory) as session:
            query = session.query(AlertEvent).filter(AlertEvent.snapshot_path.isnot(None))
            query = self._apply_scope(
                query,
                user_id=user_id,
                include_public=include_public,
                job_id=job_id,
                only_public=only_public,
            )
            event = query.order_by(AlertEvent.event_timestamp.desc(), AlertEvent.id.desc()).first()
            if event is None:
                return None
            return {
                "behavior_key": event.behavior_key,
                "behavior_name": event.behavior_name,
                "timestamp": event.event_timestamp,
                "count": event.count,
                "snapshot_path": event.snapshot_path,
                "job_id": event.job_id,
                "user_id": event.user_id,
            }

    def list_events_by_range(
        self,
        start_timestamp: float,
        end_timestamp: float,
        limit: Optional[int] = None,
        user_id: Optional[int] = None,
        include_public: bool = False,
        job_id: Optional[str] = None,
        only_public: bool = False,
    ) -> List[Dict[str, object]]:
        with session_scope(self.session_factory) as session:
            query = (
                session.query(AlertEvent)
                .filter(AlertEvent.event_timestamp >= start_timestamp)
                .filter(AlertEvent.event_timestamp <= end_timestamp)
            )
            query = self._apply_scope(
                query,
                user_id=user_id,
                include_public=include_public,
                job_id=job_id,
                only_public=only_public,
            )
            query = query.order_by(AlertEvent.event_timestamp.desc(), AlertEvent.id.desc())
            if limit is not None:
                query = query.limit(limit)
            events = query.all()
            return [_serialize_event(event) for event in events]

    def build_history_summary(
        self,
        recent_limit: int = 10,
        timeline_limit: int = 8,
        user_id: Optional[int] = None,
        include_public: bool = False,
        job_id: Optional[str] = None,
        only_public: bool = False,
    ) -> Dict[str, object]:
        events = self.list_events(
            limit=self.max_events,
            user_id=user_id,
            include_public=include_public,
            job_id=job_id,
            only_public=only_public,
        )
        return _build_summary_from_events(
            events,
            recent_limit=recent_limit,
            timeline_limit=timeline_limit,
        )

    def build_history_summary_for_range(
        self,
        start_timestamp: float,
        end_timestamp: float,
        recent_limit: int = 10,
        timeline_limit: int = 8,
        user_id: Optional[int] = None,
        include_public: bool = False,
        job_id: Optional[str] = None,
        only_public: bool = False,
    ) -> Dict[str, object]:
        events = self.list_events_by_range(
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            limit=self.max_events,
            user_id=user_id,
            include_public=include_public,
            job_id=job_id,
            only_public=only_public,
        )
        return _build_summary_from_events(
            events,
            recent_limit=recent_limit,
            timeline_limit=timeline_limit,
        )
