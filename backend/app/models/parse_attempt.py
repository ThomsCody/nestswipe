from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func

from app.database import Base


class ParseAttempt(Base):
    __tablename__ = "parse_attempts"

    id = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey("households.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    source = Column(String, nullable=False)
    email_id = Column(String, nullable=True)   # Gmail message ID (NULL for manual imports)
    url = Column(String, nullable=True)         # NULL = email-level failure (no URLs extracted)
    status = Column(String, nullable=False)     # "success" | "failed"
    fail_reason = Column(String, nullable=True) # no_urls | no_resolved_url | no_page_text | llm_no_listing | no_photos
    result = Column(String, nullable=True)      # "new" | "updated" (only set on success)
    llm_input_tokens = Column(Integer, nullable=True)
    llm_output_tokens = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
