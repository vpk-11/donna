from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_
from models.orm import Session as SessionModel, SessionArchive


class SessionStore:
    def __init__(self, db: Session):
        self.db = db

    def get(self, session_id: int) -> SessionModel | None:
        return self.db.query(SessionModel).filter(SessionModel.id == session_id).first()

    def get_conflict(
        self,
        provider_id: int,
        requested_at: datetime,
        duration_mins: int,
        buffer_mins: int,
    ) -> SessionModel | None:
        window_start = requested_at - timedelta(minutes=buffer_mins)
        window_end = requested_at + timedelta(minutes=duration_mins + buffer_mins)
        return (
            self.db.query(SessionModel)
            .filter(
                SessionModel.provider_id == provider_id,
                SessionModel.status == "scheduled",
                SessionModel.scheduled_at < window_end,
                SessionModel.scheduled_at + timedelta(minutes=duration_mins) > window_start,
            )
            .first()
        )

    def get_free_slots(
        self,
        provider_id: int,
        target_date: date,
        duration_mins: int,
        provider,
        exclude_client_id: int | None = None,
    ) -> list[datetime]:
        day_name = target_date.strftime("%a").lower()
        hours = provider.working_hours.get(day_name)
        if not hours:
            return []

        start_str, end_str = hours[0], hours[1]
        start_dt = datetime.combine(target_date, datetime.strptime(start_str, "%H:%M").time())
        end_dt = datetime.combine(target_date, datetime.strptime(end_str, "%H:%M").time())

        step = timedelta(minutes=duration_mins + provider.buffer_mins)
        slots = []
        current = start_dt
        while current + timedelta(minutes=duration_mins) <= end_dt:
            conflict = self.get_conflict(provider_id, current, duration_mins, provider.buffer_mins)
            if not conflict or (exclude_client_id and conflict.client_id == exclude_client_id):
                slots.append(current)
            current += step

        return slots

    def get_sessions_for_date(self, provider_id: int, target_date: date) -> list[SessionModel]:
        day_start = datetime.combine(target_date, datetime.min.time())
        day_end = datetime.combine(target_date, datetime.max.time())
        return (
            self.db.query(SessionModel)
            .filter(
                SessionModel.provider_id == provider_id,
                SessionModel.status == "scheduled",
                SessionModel.scheduled_at >= day_start,
                SessionModel.scheduled_at <= day_end,
            )
            .all()
        )

    def get_upcoming_for_client(self, client_id: int) -> list[SessionModel]:
        now = datetime.utcnow()
        return (
            self.db.query(SessionModel)
            .filter(
                SessionModel.client_id == client_id,
                SessionModel.status == "scheduled",
                SessionModel.scheduled_at >= now,
            )
            .order_by(SessionModel.scheduled_at)
            .limit(5)
            .all()
        )

    def create(self, data: dict) -> SessionModel:
        session = SessionModel(**data)
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def cancel(self, session_id: int) -> None:
        session = self.get(session_id)
        if session:
            session.status = "cancelled"
            self.db.commit()

    def reschedule(self, session_id: int, new_time: datetime) -> None:
        session = self.get(session_id)
        if session:
            session.scheduled_at = new_time
            session.status = "rescheduled"
            self.db.commit()

    def archive(self, session_id: int, reason: str) -> None:
        session = self.get(session_id)
        if not session:
            return
        archive = SessionArchive(
            original_session_id=session.id,
            provider_id=session.provider_id,
            client_id=session.client_id,
            scheduled_at=session.scheduled_at,
            duration_mins=session.duration_mins,
            location=session.location,
            status=session.status,
            is_recurring=session.is_recurring,
            recurrence_type=session.recurrence_type,
            archive_reason=reason,
        )
        self.db.add(archive)
        self.db.commit()
