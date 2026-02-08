import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator
import asyncio
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

from app.core.config import settings
from app.services.kdv_calculator import KDVCalculator

logger = logging.getLogger(__name__)


class InvoiceLineItem(BaseModel):
    description: str = Field(..., description="Ürün/hizmet açıklaması")
    quantity: Decimal = Field(..., ge=0, description="Miktar")
    unit_price: Decimal = Field(..., ge=0, description="Birim fiyat")
    kdv_rate: Decimal = Field(..., ge=0, le=100, description="KDV oranı (%)")
    total: Decimal = Field(..., ge=0, description="Satır toplamı (KDV hariç)")
    
    @field_validator('quantity', 'unit_price', 'kdv_rate', 'total', mode='before')
    @classmethod
    def convert_to_decimal(cls, v):
        if isinstance(v, (int, float, str)):
            return Decimal(str(v))
        return v


class ExtractedInvoiceData(BaseModel):
    invoice_number: Optional[str] = Field(None, description="Fatura numarası")
    invoice_date: Optional[date] = Field(None, description="Fatura tarihi")
    supplier_name: Optional[str] = Field(None, description="Tedarikçi/Satıcı adı")
    supplier_tax_number: Optional[str] = Field(None, description="Tedarikçi vergi numarası")
    supplier_address: Optional[str] = Field(None, description="Tedarikçi adresi")
    customer_name: Optional[str] = Field(None, description="Müşteri adı")
    customer_tax_number: Optional[str] = Field(None, description="Müşteri vergi numarası")
    customer_address: Optional[str] = Field(None, description="Müşteri adresi")
    currency: str = Field(default="TRY", description="Para birimi")
    subtotal: Decimal = Field(default=Decimal("0"), ge=0, description="KDV hariç toplam")
    total_kdv: Decimal = Field(default=Decimal("0"), ge=0, description="Toplam KDV tutarı")
    total_amount: Decimal = Field(default=Decimal("0"), ge=0, description="KDV dahil toplam")
    line_items: List[InvoiceLineItem] = Field(default_factory=list, description="Kalemler")
    payment_terms: Optional[str] = Field(None, description="Ödeme koşulları")
    notes: Optional[str] = Field(None, description="Notlar/Açıklamalar")
    
    @field_validator('invoice_date', mode='before')
    @classmethod
    def parse_date(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d"):
                try:
                    return datetime.strptime(v, fmt).date()
                except ValueError:
                    continue
            return None
        return v
    
    @field_validator('subtotal', 'total_kdv', 'total_amount', mode='before')
    @classmethod
    def convert_to_decimal(cls, v):
        if isinstance(v, (int, float, str)):
            return Decimal(str(v))
        return v


class AIExtractionService:
    def __init__(self):
        self._client: Optional[AsyncOpenAI] = None
        self._kdv_calculator = KDVCalculator()
        logger.info("AIExtractionService initialized (lazy client)")
    
    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            if not settings.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY not configured")
            self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            logger.info("OpenAI client initialized successfully")
        return self._client
    
    def _build_system_prompt(self) -> str:
        return """Sen Türk fatura formatlarını analiz eden bir yapay zeka asistanısın.

Görevin: OCR ile çıkarılmış fatura metninden yapılandırılmış JSON verisi oluşturmak.

TÜRK FATURA FORMATI BİLGİLERİ:
- Fatura numarası genellikle "Fatura No:", "Invoice No:", "Seri No:" etiketleriyle başlar
- Tarih formatları: DD.MM.YYYY veya DD/MM/YYYY
- Vergi numaraları 10 haneli sayıdır
- KDV oranları Türkiye'de genellikle: %1, %8, %10, %18, %20
- Para birimi genellikle TRY (Türk Lirası), ancak EUR, USD de olabilir
- Tutarlar virgül (,) veya nokta (.) ile ondalık ayracı kullanabilir

ÇÖZÜMLENECEK BİLGİLER:
1. Temel Fatura Bilgileri:
   - invoice_number: Fatura numarası
   - invoice_date: Fatura tarihi (YYYY-MM-DD formatında)
   - currency: Para birimi (TRY, EUR, USD vb.)

2. Tedarikçi (Satıcı) Bilgileri:
   - supplier_name: Firma adı
   - supplier_tax_number: Vergi numarası (10 haneli)
   - supplier_address: Tam adres

3. Müşteri (Alıcı) Bilgileri:
   - customer_name: Firma/kişi adı
   - customer_tax_number: Vergi numarası
   - customer_address: Tam adres

4. Kalemler (line_items array):
   Her kalem için:
   - description: Ürün/hizmet açıklaması
   - quantity: Miktar (sayısal)
   - unit_price: Birim fiyat (KDV hariç)
   - kdv_rate: KDV oranı (%)
   - total: Satır toplamı (KDV hariç, quantity * unit_price)

5. Mali Toplamlar:
   - subtotal: Tüm kalemlerin KDV hariç toplamı
   - total_kdv: Toplam KDV tutarı
   - total_amount: KDV dahil genel toplam

6. Diğer:
   - payment_terms: Ödeme koşulları/vade
   - notes: Notlar, açıklamalar

ÇIKTI FORMATI:
Sadece geçerli JSON döndür, başka metin ekleme.
Bulamadığın alanlar için null kullan.
Tüm sayısal değerleri string olarak formatla (örn: "123.45").
Tarihi YYYY-MM-DD formatında ver.

Örnek çıktı:
{
  "invoice_number": "FTR2024001234",
  "invoice_date": "2024-01-15",
  "supplier_name": "ABC Ticaret Ltd. Şti.",
  "supplier_tax_number": "1234567890",
  "supplier_address": "Atatürk Cad. No:123 Şişli/İstanbul",
  "customer_name": "XYZ A.Ş.",
  "customer_tax_number": "9876543210",
  "customer_address": "Cumhuriyet Mah. İzmir Cad. No:45 Ankara",
  "currency": "TRY",
  "subtotal": "10000.00",
  "total_kdv": "2000.00",
  "total_amount": "12000.00",
  "line_items": [
    {
      "description": "Yazılım Lisansı",
      "quantity": "1",
      "unit_price": "10000.00",
      "kdv_rate": "20",
      "total": "10000.00"
    }
  ],
  "payment_terms": "30 gün vadeli",
  "notes": null
}"""
    
    def _build_user_prompt(self, ocr_text: str) -> str:
        return f"""Aşağıdaki OCR metni bir Türk faturasından çıkarılmıştır. Lütfen bu metni analiz et ve yapılandırılmış JSON formatında fatura bilgilerini çıkar:

--- OCR METNİ BAŞLANGIÇ ---
{ocr_text}
--- OCR METNİ BİTİŞ ---

Not: Metin OCR hatası içerebilir, bağlamdan en doğru değerleri çıkarmaya çalış."""
    
    async def extract_invoice_data(
        self,
        ocr_text: str,
        max_retries: int = 2,
        initial_temperature: float = 0.1
    ) -> ExtractedInvoiceData:
        if not ocr_text or not ocr_text.strip():
            raise ValueError("OCR text is empty")
        
        logger.info(f"Starting AI extraction, text length: {len(ocr_text)}")
        
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(ocr_text)
        
        for attempt in range(max_retries + 1):
            temperature = initial_temperature + (attempt * 0.2)
            temperature = min(temperature, 1.0)
            
            try:
                logger.info(f"AI extraction attempt {attempt + 1}/{max_retries + 1}, temperature: {temperature}")
                
                response: ChatCompletion = await self.client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=temperature,
                    max_tokens=2000,
                    response_format={"type": "json_object"}
                )
                
                content = response.choices[0].message.content
                if not content:
                    raise ValueError("Empty response from OpenAI")
                
                logger.debug(f"Raw AI response: {content[:500]}...")
                
                parsed_data = json.loads(content)
                
                extracted_data = ExtractedInvoiceData(**parsed_data)
                
                extracted_data = self._validate_and_recalculate(extracted_data)
                
                logger.info(f"AI extraction successful: invoice_number={extracted_data.invoice_number}, total={extracted_data.total_amount}")
                return extracted_data
                
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error on attempt {attempt + 1}: {e}")
                if attempt == max_retries:
                    raise ValueError(f"Failed to parse AI response as JSON after {max_retries + 1} attempts")
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"AI extraction error on attempt {attempt + 1}: {e}")
                if attempt == max_retries:
                    raise ValueError(f"Failed to extract invoice data after {max_retries + 1} attempts: {str(e)}")
                await asyncio.sleep(1)
        
        raise ValueError("AI extraction failed after all retries")
    
    def _validate_and_recalculate(self, data: ExtractedInvoiceData) -> ExtractedInvoiceData:
        logger.info("Validating and recalculating invoice totals")
        
        if not data.line_items:
            logger.warning("No line items found, keeping original totals")
            return data
        
        calculated_subtotal = Decimal("0")
        calculated_total_kdv = Decimal("0")
        
        for idx, item in enumerate(data.line_items):
            try:
                line_subtotal = item.quantity * item.unit_price
                line_kdv = self._kdv_calculator.calculate_kdv(line_subtotal, item.kdv_rate)
                
                if abs(item.total - line_subtotal) > Decimal("0.01"):
                    logger.warning(f"Line item {idx} total mismatch: {item.total} vs calculated {line_subtotal}, using calculated")
                    item.total = line_subtotal
                
                calculated_subtotal += line_subtotal
                calculated_total_kdv += line_kdv
                
            except Exception as e:
                logger.error(f"Error calculating line item {idx}: {e}")
        
        calculated_total = calculated_subtotal + calculated_total_kdv
        
        if abs(data.subtotal - calculated_subtotal) > Decimal("1.00"):
            logger.warning(f"Subtotal mismatch: original={data.subtotal}, calculated={calculated_subtotal}, using calculated")
            data.subtotal = calculated_subtotal
        
        if abs(data.total_kdv - calculated_total_kdv) > Decimal("1.00"):
            logger.warning(f"Total KDV mismatch: original={data.total_kdv}, calculated={calculated_total_kdv}, using calculated")
            data.total_kdv = calculated_total_kdv
        
        if abs(data.total_amount - calculated_total) > Decimal("1.00"):
            logger.warning(f"Total amount mismatch: original={data.total_amount}, calculated={calculated_total}, using calculated")
            data.total_amount = calculated_total
        
        logger.info(f"Validation complete: subtotal={data.subtotal}, kdv={data.total_kdv}, total={data.total_amount}")
        return data
    
    async def extract_with_fallback(self, ocr_text: str, confidence_threshold: float = 0.7) -> Dict[str, Any]:
        try:
            extracted_data = await self.extract_invoice_data(ocr_text)
            
            return {
                "success": True,
                "data": extracted_data.model_dump(mode='json'),
                "confidence": "high",
                "requires_review": False
            }
            
        except Exception as e:
            logger.error(f"AI extraction failed, returning partial data: {e}")
            
            return {
                "success": False,
                "data": {
                    "invoice_number": None,
                    "invoice_date": None,
                    "supplier_name": None,
                    "supplier_tax_number": None,
                    "supplier_address": None,
                    "customer_name": None,
                    "customer_tax_number": None,
                    "customer_address": None,
                    "currency": "TRY",
                    "subtotal": "0",
                    "total_kdv": "0",
                    "total_amount": "0",
                    "line_items": [],
                    "payment_terms": None,
                    "notes": None
                },
                "confidence": "low",
                "requires_review": True,
                "error":