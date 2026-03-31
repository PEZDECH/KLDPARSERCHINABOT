"""
SQLAlchemy models for Marketplace Monitor Bot.
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.database import Base


class Platform(str, enum.Enum):
    """Supported marketplace platforms."""

    AVITO = "avito"
    GRAILED = "grailed"
    MERCARI = "mercari"


class User(Base):
    """Telegram user model."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    first_name: Mapped[str] = mapped_column(String(64), nullable=False)
    last_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    subscriptions: Mapped[list["Subscription"]] = relationship(
        "Subscription",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, username={self.username})>"


class Subscription(Base):
    """User subscription for monitoring specific items."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "platform", "query", "min_price", "max_price",
            name="unique_subscription"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[Platform] = mapped_column(Enum(Platform), nullable=False)
    query: Mapped[str] = mapped_column(String(255), nullable=False)
    min_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="subscriptions")
    items: Mapped[list["Item"]] = relationship(
        "Item",
        back_populates="subscription",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<Subscription(id={self.id}, platform={self.platform.value}, "
            f"query='{self.query}')>"
        )

    @property
    def price_range_str(self) -> str:
        """Return formatted price range string."""
        if self.min_price and self.max_price:
            return f"{self.min_price:,.0f} - {self.max_price:,.0f} ₽"
        elif self.min_price:
            return f"от {self.min_price:,.0f} ₽"
        elif self.max_price:
            return f"до {self.max_price:,.0f} ₽"
        return "любая цена"


class Item(Base):
    """Item that has been found and sent to user."""

    __tablename__ = "items"
    __table_args__ = (
        UniqueConstraint(
            "subscription_id", "platform_item_id",
            name="unique_item_per_subscription"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscription_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    platform_item_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    image_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    seller_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    subscription: Mapped["Subscription"] = relationship(
        "Subscription", back_populates="items"
    )

    def __repr__(self) -> str:
        return f"<Item(id={self.id}, title='{self.title[:30]}...', price={self.price})>"

    def to_message_text(self) -> str:
        """Format item as Telegram message text."""
        lines = [
            f"🛍 <b>{self.title[:100]}{'...' if len(self.title) > 100 else ''}</b>",
            f"💰 <b>{self.price:,.0f} {self.currency}</b>",
        ]
        if self.location:
            lines.append(f"📍 {self.location}")
        if self.seller_name:
            lines.append(f"👤 Продавец: {self.seller_name}")
        lines.append(f"🔗 <a href='{self.url}'>Открыть на {self.subscription.platform.value.title()}</a>")
        return "\n".join(lines)
