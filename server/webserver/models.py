from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, func
from sqlalchemy.orm import relationship
from db import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")


class UserSession(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_token = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="sessions")

class Device(Base):
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True, autoincrement=True)
    mac_address = Column(String(32), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())

    readings = relationship("Reading", back_populates="device")

class Reading(Base):
    __tablename__ = "readings"
    id = Column(Integer, primary_key=True, autoincrement=True)

    mac_address = Column(String(32), nullable=False, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True)

    thermistor_temp = Column(Float, nullable=False)
    prediction = Column(String(16), nullable=False)
    confidence = Column(Float, nullable=False)

    pixels = Column(JSON, nullable=False)  # list of 64 floats
    created_at = Column(DateTime, server_default=func.now())

    device = relationship("Device", back_populates="readings")