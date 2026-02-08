import logging
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload

from app.models.invoice import (
    Invoice,
    InvoiceCreate,
    InvoiceUpdate,
    InvoiceResponse,
    InvoiceListResponse,
    User,
    InvoiceStatus
)
from app.services.ocr_service import ocr_service
from app.services.ai_extraction_service import ai_extraction_service
from app.services.kdv_calculator import KDVCalculator
from app.services.parasut_integration import parasut_client, ParasutAPIError
from app.api.v1.auth import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.tasks.celery_app import process_invoice_task
from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/upload", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def upload_invoice(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        if not file.content_type or not file.content_type.startswith(('image/', 'application/pdf')):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sadece resim veya PDF dosyaları kabul edilir"
            )
        
        max_size = 10 * 1024 * 1024
        file_content = await file.read()
        if len(file_content) > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Dosya boyutu 10MB'dan büyük olamaz"
            )
        
        file_extension = file.filename.split('.')[-1].lower() if '.' in file.filename else 'unknown'
        file_path = f"invoices/{current_user.id}/{datetime.utcnow().strftime('%Y/%m')}/{UUID.uuid4()}.{file_extension}"
        
        file_url = await storage_service.upload_file(
            file_content=file_content,
            file_path=file_path,
            content_type=file.content_type
        )
        
        new_invoice = Invoice(
            user_id=current_user.id,
            original_filename=file.filename,
            file_url=file_url,
            file_size=len(file_content),
            mime_type=file.content_type,
            status=InvoiceStatus.UPLOADED,
            uploaded_at=datetime.utcnow()
        )
        
        db.add(new_invoice)
        await db.commit()
        await db.refresh(new_invoice)
        
        try:
            task = process_invoice_task.delay(str(new_invoice.id))
            logger.info(f"Celery task {task.id} started for invoice {new_invoice.id}")
        except Exception as task_error:
            logger.error(f"Failed to start Celery task for invoice {new_invoice.id}: {task_error}")
            new_invoice.status = InvoiceStatus.FAILED
            new_invoice.error_message = "İşleme görevi başlatılamadı"
            await db.commit()
            await db.refresh(new_invoice)
        
        return InvoiceResponse.model_validate(new_invoice)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Dosya yüklenirken bir hata oluştu"
        )


@router.get("", response_model=InvoiceListResponse)
async def list_invoices(
    status_filter: Optional[InvoiceStatus] = Query(None, description="Duruma göre filtrele"),
    start_date: Optional[datetime] = Query(None, description="Başlangıç tarihi (ISO 8601)"),
    end_date: Optional[datetime] = Query(None, description="Bitiş tarihi (ISO 8601)"),
    cursor: Optional[str] = Query(None, description="Pagination cursor (invoice ID)"),
    limit: int = Query(20, ge=1, le=100, description="Sayfa başına kayıt sayısı"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        query = select(Invoice).where(Invoice.user_id == current_user.id)
        
        if status_filter:
            query = query.where(Invoice.status == status_filter)
        
        if start_date:
            query = query.where(Invoice.uploaded_at >= start_date)
        
        if end_date:
            query = query.where(Invoice.uploaded_at <= end_date)
        
        if cursor:
            try:
                cursor_uuid = UUID(cursor)
                cursor_invoice = await db.get(Invoice, cursor_uuid)
                if cursor_invoice and cursor_invoice.user_id == current_user.id:
                    query = query.where(Invoice.uploaded_at < cursor_invoice.uploaded_at)
            except (ValueError, AttributeError):
                pass
        
        query = query.order_by(Invoice.uploaded_at.desc()).limit(limit + 1)
        
        result = await db.execute(query)
        invoices = result.scalars().all()
        
        has_next = len(invoices) > limit
        items = invoices[:limit]
        
        next_cursor = str(items[-1].id) if has_next and items else None
        
        count_query = select(func.count(Invoice.id)).where(Invoice.user_id == current_user.id)
        if status_filter:
            count_query = count_query.where(Invoice.status == status_filter)
        if start_date:
            count_query = count_query.where(Invoice.uploaded_at >= start_date)
        if end_date:
            count_query = count_query.where(Invoice.uploaded_at <= end_date)
        
        total_result = await db.execute(count_query)
        total_count = total_result.scalar() or 0
        
        return InvoiceListResponse(
            items=[InvoiceResponse.model_validate(inv) for inv in items],
            total=total_count,
            next_cursor=next_cursor,
            has_next=has_next
        )
        
    except Exception as e:
        logger.error(f"List invoices error for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fatura listesi alınırken hata oluştu"
        )


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        query = select(Invoice).where(
            and_(
                Invoice.id == invoice_id,
                Invoice.user_id == current_user.id
            )
        )
        result = await db.execute(query)
        invoice = result.scalar_one_or_none()
        
        if not invoice:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Fatura bulunamadı"
            )
        
        return InvoiceResponse.model_validate(invoice)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get invoice {invoice_id} error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fatura detayı alınırken hata oluştu"
        )


@router.put("/{invoice_id}", response_model=InvoiceResponse)
async def update_invoice(
    invoice_id: UUID,
    invoice_update: InvoiceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        query = select(Invoice).where(
            and_(
                Invoice.id == invoice_id,
                Invoice.user_id == current_user.id
            )
        )
        result = await db.execute(query)
        invoice = result.scalar_one_or_none()
        
        if not invoice:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Fatura bulunamadı"
            )
        
        if invoice.status == InvoiceStatus.EXPORTED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Dışa aktarılmış faturalar düzenlenemez"
            )
        
        update_data = invoice_update.model_dump(exclude_unset=True)
        
        if "extracted_data" in update_data and update_data["extracted_data"]:
            extracted = update_data["extracted_data"]
            
            if extracted.get("subtotal") and extracted.get("kdv_rate"):
                calculator = KDVCalculator()
                kdv_result = calculator.calculate_kdv(
                    subtotal=Decimal(str(extracted["subtotal"])),
                    kdv_rate=Decimal(str(extracted["kdv_rate"]))
                )
                
                if not kdv_result.is_valid:
                    logger.warning(f"KDV validation failed for invoice {invoice_id}: {kdv_result.error_message}")
                    if kdv_result.suggested_values:
                        extracted.update({
                            "kdv_amount": float(kdv_result.suggested_values["kdv_amount"]),
                            "total": float(kdv_result.suggested_values["total"])
                        })
            
            current_extracted = invoice.extracted_data or {}
            current_extracted.update(extracted)
            invoice.extracted_data = current_extracted
            invoice.is_manually_corrected = True
        
        for key, value in update_data.items():
            if key != "extracted_data" and hasattr(invoice, key):
                setattr(invoice, key, value)
        
        invoice.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(invoice)
        
        return InvoiceResponse.model_validate(invoice)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update invoice {invoice_id} error: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fatura güncellenirken hata oluştu"
        )


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invoice(
    invoice_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        query = select(Invoice).where(
            and_(
                Invoice.id == invoice_id,
                Invoice.user_id == current_user.id
            )
        )
        result = await db.execute(query)
        invoice = result.scalar_one_or_none()
        
        if not invoice:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Fatura bulunamadı"
            )
        
        try:
            if invoice.file_url:
                await storage_service.delete_file(invoice.file_url)
        except Exception as storage_error:
            logger.error(f"Failed to delete file for invoice {invoice_id}: {storage_error}")
        
        await db.delete(invoice)
        await db.commit()
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete invoice {invoice_id} error: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fatura silinirken hata oluştu"
        )


@router.post("/{invoice_id}/export", response_model=Dict[str, Any])
async def export_to_parasut(
    invoice_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        query = select(Invoice).where(
            and_(
                Invoice.id == invoice_id,
                Invoice.user_id == current_user.id
            )
        )
        result = await db.execute(query)
        invoice = result.scalar_one_or_none()
        
        if not invoice:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Fatura bulunamadı"
            )
        
        if invoice.status != InvoiceStatus.COMPLETED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sadece tamamlanmış faturalar dışa aktarılabilir"
            )
        
        if invoice.status == InvoiceStatus.EXPORTED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bu fatura zaten dışa aktarıldı"
            )
        
        if not invoice.extracted_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Fatura verisi eksik, dışa aktarılamaz"
            )
        
        try:
            result = await parasut_client.export_invoice(invoice)
            
            invoice.status = InvoiceStatus.EXPORTED
            invoice.parasut_invoice_id = result.get("parasut_id")
            invoice.exported_at = datetime.utcnow()
            invoice.updated_at = datetime.utcnow()
            
            await db.commit()
            await db.refresh(invoice)
            
            return {
                "success": True,
                "message": "Fatura başarıyla Paraşüt'e aktarıldı",
                "parasut_id": result.get("parasut_id"),
                "parasut_url": result.get("parasut_url"),
                "exported_at": invoice.exported_at.isoformat()
            }
            
        except ParasutAPIError as parasut_error:
            logger.error(f"Parasut export error for invoice {invoice_id}: {parasut_error.message}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Paraşüt API hatası: {parasut_error.message}"
            )
        
    except HTTPException