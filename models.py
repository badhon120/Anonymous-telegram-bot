from sqlalchemy import Column, Integer, BigInteger, String, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.orm import DeclarativeBase, relationship
from datetime import datetime
import uuid
import enum

class Base(DeclarativeBase):
    pass

class Gender(enum.Enum):
    MALE = "male"
    FEMALE = "female"
    UNKNOWN = "unknown"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    tg_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String, nullable=True) # Removed unique=True to prevent crashes
    full_name = Column(String, nullable=True)
    nickname = Column(String, nullable=True)
    bio = Column(String, nullable=True)
    gender = Column(Enum(Gender), default=Gender.UNKNOWN)
    link_token = Column(String, unique=True, default=lambda: str(uuid.uuid4())[:8])
    is_admin = Column(Boolean, default=False)
    is_blocked = Column(Boolean, default=False)
    display_id = Column(String, unique=True, nullable=True) # Random ID e.g U2834
    age = Column(Integer, nullable=True) # [NEW] Age field
    referred_by_id = Column(Integer, ForeignKey("users.id"), nullable=True) # Referral system
    referral_confirmed = Column(Boolean, default=False) # [NEW] Only count if joined channel
    referral_bonus_until = Column(DateTime, nullable=True) # 1 hour bypass reward
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    sent_messages = relationship("MessageLog", foreign_keys="MessageLog.sender_id", back_populates="sender")
    received_messages = relationship("MessageLog", foreign_keys="MessageLog.receiver_id", back_populates="receiver")
    blocked_users = relationship("Block", foreign_keys="Block.blocker_id", back_populates="blocker")

class Settings(Base):
    __tablename__ = "settings"
    
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, nullable=False)
    value = Column(String, nullable=True)

class Block(Base):
    __tablename__ = "blocks"
    
    id = Column(Integer, primary_key=True)
    blocker_id = Column(Integer, ForeignKey("users.id"))
    blocked_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    blocker = relationship("User", foreign_keys=[blocker_id], back_populates="blocked_users")
    blocked = relationship("User", foreign_keys=[blocked_id])

class MessageLog(Base):
    __tablename__ = "message_logs"
    
    id = Column(Integer, primary_key=True)
    sender_id = Column(Integer, ForeignKey("users.id"))
    receiver_id = Column(Integer, ForeignKey("users.id"))
    content = Column(String, nullable=True) # Added content column
    content_type = Column(String)  # text, photo, voice, etc.
    context = Column(String) # 'link' or 'match'
    created_at = Column(DateTime, default=datetime.utcnow) # Renamed from timestamp
    
    sender = relationship("User", foreign_keys=[sender_id], back_populates="sent_messages")
    receiver = relationship("User", foreign_keys=[receiver_id], back_populates="received_messages")

class MatchQueue(Base):
    __tablename__ = "match_queue"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    preferred_gender = Column(Enum(Gender))
    created_at = Column(DateTime, default=datetime.utcnow)

class MatchSession(Base):
    __tablename__ = "match_sessions"
    
    id = Column(Integer, primary_key=True)
    user1_id = Column(Integer, ForeignKey("users.id"))
    user2_id = Column(Integer, ForeignKey("users.id"))
    is_active = Column(Boolean, default=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
