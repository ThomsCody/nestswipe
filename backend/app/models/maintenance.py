from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MaintenancePresence(Base):
    __tablename__ = "maintenance_presence"
    __table_args__ = (CheckConstraint("id = 1"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    last_activity: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reboot_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
