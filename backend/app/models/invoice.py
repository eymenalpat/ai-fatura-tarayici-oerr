from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from uuid import UUID, uuid4
from sqlalchemy import String, Boolean, Text, TIMESTAMP, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from pydantic import BaseModel, EmailStr, Field, field_validator, computed_field
import enum

from app.core.config import settings


class Base(DeclarativeBase):
    pass


class SubscriptionPlan(str, enum.Enum):
    FREE = "free"
    BASIC = "basic"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"


class InvoiceStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPORTED = "exported"


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    company_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    subscription_plan: Mapped[str] = mapped_column(
        String(50), 
        default=SubscriptionPlan.FREE.value,
        nullable=False
    )
    subscription_expires_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), 
        nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    kvkk_consent_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), 
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    invoices: Mapped[List["Invoice"]] = relationship(
        "Invoice",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan"
    )


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    
    status: Mapped[str] = mapped_column(
        String(50),
        default=InvoiceStatus.UPLOADED.value,
        nullable=False,
        index=True
    )
    
    ocr_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extracted_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    
    confidence_score: Mapped[Optional[float]] = mapped_column(nullable=True)
    processing_time_seconds: Mapped[Optional[float]] = mapped_column(nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    exported_to_parasut: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    parasut_invoice_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    exported_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True
    )
    
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="invoices")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    token: Mapped[str] = mapped_column(String(500), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        index=True
    )
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")


# Pydantic Schemas

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None
    company_name: Optional[str] = None
    kvkk_consent: bool = Field(..., description="KVKK onayı zorunlu")

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError('Şifre en az 8 karakter olmalıdır')
        if not any(c.isupper() for c in v):
            raise ValueError('Şifre en az bir büyük harf içermelidir')
        if not any(c.islower() for c in v):
            raise ValueError('Şifre en az bir küçük harf içermelidir')
        if not any(c.isdigit() for c in v):
            raise ValueError('Şifre en az bir rakam içermelidir')
        return v

    @field_validator('kvkk_consent')
    @classmethod
    def validate_kvkk(cls, v: bool) -> bool:
        if not v:
            raise ValueError('KVKK onayı zorunludur')
        return v


class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    full_name: Optional[str] = None
    company_name: Optional[str] = None
    subscription_plan: str
    subscription_expires_at: Optional[datetime] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InvoiceCreate(BaseModel):
    original_filename: str
    file_size: int
    mime_type: str


class InvoiceUpdate(BaseModel):
    extracted_data: Optional[Dict[str, Any]] = None
    status: Optional[str] = None

    @field_validator('status')
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in [s.value for s in InvoiceStatus]:
            raise ValueError(f'Geçersiz status. İzin verilenler: {[s.value for s in InvoiceStatus]}')
        return v


class InvoiceResponse(BaseModel):
    id: UUID
    user_id: UUID
    original_filename: str
    file_path: str
    file_size: int
    mime_type: str
    status: str
    ocr_text: Optional[str] = None
    extracted_data: Optional[Dict[str, Any]] = None
    confidence_score: Optional[float] = None
    processing_time_seconds: Optional[float] = None
    error_message: Optional[str] = None
    exported_to_parasut: bool
    parasut_invoice_id: Optional[str] = None
    exported_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def kdv_validated(self) -> bool:
        if not self.extracted_data:
            return False
        
        try:
            total = self.extracted_data.get('total_amount', 0)
            subtotal = self.extracted_data.get('subtotal', 0)
            kdv = self.extracted_data.get('tax_amount', 0)
            
            if total <= 0 or subtotal <= 0:
                return False
            
            calculated_total = subtotal + kdv
            tolerance = 0.02
            
            return abs(total - calculated_total) <= tolerance
        except (TypeError, KeyError, ValueError):
            return False

    model_config = {"from_attributes": True}


class InvoiceListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    invoices: List[InvoiceResponse]

    model_config = {"from_attributes": True}