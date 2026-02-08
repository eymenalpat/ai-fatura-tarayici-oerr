from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)


class KDVResult(BaseModel):
    is_valid: bool = Field(..., description="KDV hesaplaması doğru mu")
    subtotal: Decimal = Field(..., description="KDV hariç tutar")
    kdv_amount: Decimal = Field(..., description="KDV tutarı")
    total: Decimal = Field(..., description="KDV dahil toplam")
    kdv_rate: Decimal = Field(..., description="Uygulanan KDV oranı (%)")
    suggested_values: Optional[Dict[str, Decimal]] = Field(
        default=None,
        description="Önerilen düzeltilmiş değerler (eğer is_valid=False ise)"
    )
    error_message: Optional[str] = Field(default=None, description="Hata mesajı")


class KDVCalculator:
    # Türkiye'de geçerli KDV oranları ve kategorileri
    KDV_RATES: Dict[Decimal, List[str]] = {
        Decimal("1"): [
            "Gazete, dergi, kitap ve benzeri yayınlar",
            "Eğitim ve öğretim hizmetleri",
        ],
        Decimal("10"): [
            "Konut kiraları",
            "Gıda maddeleri (temel)",
            "İlaç ve medikal malzemeler",
            "Kitap, gazete, dergi",
            "Konut teslimleri",
        ],
        Decimal("20"): [
            "Genel mal ve hizmetler",
            "Elektronik eşya",
            "Giyim",
            "Mobilya",
            "Danışmanlık hizmetleri",
            "Yazılım hizmetleri",
        ],
    }

    TOLERANCE: Decimal = Decimal("0.01")  # ±0.01 TRY yuvarlama toleransı

    @classmethod
    def get_valid_rates(cls) -> List[Decimal]:
        """Geçerli KDV oranlarını döndürür"""
        return list(cls.KDV_RATES.keys())

    @classmethod
    def get_categories_for_rate(cls, rate: Decimal) -> List[str]:
        """Belirli bir KDV oranı için ürün kategorilerini döndürür"""
        return cls.KDV_RATES.get(rate, [])

    @classmethod
    def calculate(cls, subtotal: Decimal, rate: Decimal) -> KDVResult:
        """
        KDV hariç tutara göre KDV ve toplam hesaplar
        
        Args:
            subtotal: KDV hariç tutar
            rate: KDV oranı (%)
            
        Returns:
            KDVResult: Hesaplama sonucu
        """
        try:
            subtotal = Decimal(str(subtotal))
            rate = Decimal(str(rate))

            if subtotal < 0:
                return KDVResult(
                    is_valid=False,
                    subtotal=subtotal,
                    kdv_amount=Decimal("0"),
                    total=subtotal,
                    kdv_rate=rate,
                    error_message="KDV hariç tutar negatif olamaz"
                )

            if rate not in cls.get_valid_rates():
                logger.warning(f"Geçersiz KDV oranı: {rate}%. Geçerli oranlar: {cls.get_valid_rates()}")

            kdv_amount = (subtotal * rate / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            total = subtotal + kdv_amount

            return KDVResult(
                is_valid=True,
                subtotal=subtotal,
                kdv_amount=kdv_amount,
                total=total,
                kdv_rate=rate
            )

        except Exception as e:
            logger.error(f"KDV hesaplama hatası: {e}")
            return KDVResult(
                is_valid=False,
                subtotal=Decimal("0"),
                kdv_amount=Decimal("0"),
                total=Decimal("0"),
                kdv_rate=rate,
                error_message=f"Hesaplama hatası: {str(e)}"
            )

    @classmethod
    def validate(
        cls,
        subtotal: Decimal,
        kdv_amount: Decimal,
        total: Decimal,
        rate: Optional[Decimal] = None
    ) -> KDVResult:
        """
        Verilen KDV tutarlarının doğruluğunu kontrol eder
        
        Args:
            subtotal: KDV hariç tutar
            kdv_amount: KDV tutarı
            total: KDV dahil toplam
            rate: KDV oranı (opsiyonel, verilmezse kdv_amount'tan hesaplanır)
            
        Returns:
            KDVResult: Doğrulama sonucu ve önerilen değerler
        """
        try:
            subtotal = Decimal(str(subtotal))
            kdv_amount = Decimal(str(kdv_amount))
            total = Decimal(str(total))

            if subtotal < 0 or kdv_amount < 0 or total < 0:
                return KDVResult(
                    is_valid=False,
                    subtotal=subtotal,
                    kdv_amount=kdv_amount,
                    total=total,
                    kdv_rate=rate or Decimal("0"),
                    error_message="Tutarlar negatif olamaz"
                )

            # KDV oranını hesapla veya doğrula
            if rate is None:
                if subtotal > 0:
                    calculated_rate = ((kdv_amount / subtotal) * Decimal("100")).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                    # En yakın geçerli orana yuvarla
                    rate = cls._find_closest_valid_rate(calculated_rate)
                else:
                    rate = Decimal("20")  # Default rate
            else:
                rate = Decimal(str(rate))

            # Beklenen değerleri hesapla
            expected_kdv = (subtotal * rate / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            expected_total = subtotal + expected_kdv

            # Toplam kontrolü (subtotal + kdv_amount = total)
            calculated_total = subtotal + kdv_amount
            total_diff = abs(total - calculated_total)

            # KDV tutarı kontrolü
            kdv_diff = abs(kdv_amount - expected_kdv)

            # Toplam tutar kontrolü
            expected_total_diff = abs(total - expected_total)

            # Tolerans dahilinde mi kontrol et
            is_total_valid = total_diff <= cls.TOLERANCE
            is_kdv_valid = kdv_diff <= cls.TOLERANCE
            is_expected_total_valid = expected_total_diff <= cls.TOLERANCE

            is_valid = is_total_valid and is_kdv_valid and is_expected_total_valid

            if not is_valid:
                error_parts = []
                if not is_total_valid:
                    error_parts.append(
                        f"Toplam uyuşmazlığı: {subtotal} + {kdv_amount} = {calculated_total}, "
                        f"fakat faturada {total} (fark: {total_diff})"
                    )
                if not is_kdv_valid:
                    error_parts.append(
                        f"KDV tutarı uyuşmazlığı: Beklenen {expected_kdv}, "
                        f"faturada {kdv_amount} (fark: {kdv_diff})"
                    )
                if not is_expected_total_valid:
                    error_parts.append(
                        f"Beklenen toplam uyuşmazlığı: {expected_total}, "
                        f"faturada {total} (fark: {expected_total_diff})"
                    )

                return KDVResult(
                    is_valid=False,
                    subtotal=subtotal,
                    kdv_amount=kdv_amount,
                    total=total,
                    kdv_rate=rate,
                    suggested_values={
                        "kdv_amount": expected_kdv,
                        "total": expected_total,
                        "subtotal": subtotal,
                        "kdv_rate": rate
                    },
                    error_message="; ".join(error_parts)
                )

            return KDVResult(
                is_valid=True,
                subtotal=subtotal,
                kdv_amount=kdv_amount,
                total=total,
                kdv_rate=rate
            )

        except Exception as e:
            logger.error(f"KDV doğrulama hatası: {e}")
            return KDVResult(
                is_valid=False,
                subtotal=subtotal,
                kdv_amount=kdv_amount,
                total=total,
                kdv_rate=rate or Decimal("0"),
                error_message=f"Doğrulama hatası: {str(e)}"
            )

    @classmethod
    def _find_closest_valid_rate(cls, calculated_rate: Decimal) -> Decimal:
        """Hesaplanan orana en yakın geçerli KDV oranını bulur"""
        valid_rates = cls.get_valid_rates()
        
        closest_rate = valid_rates[0]
        min_diff = abs(calculated_rate - closest_rate)
        
        for rate in valid_rates[1:]:
            diff = abs(calculated_rate - rate)
            if diff < min_diff:
                min_diff = diff
                closest_rate = rate
        
        return closest_rate

    @classmethod
    def calculate_from_total(cls, total: Decimal, rate: Decimal) -> KDVResult:
        """
        KDV dahil tutardan geriye doğru hesaplama yapar
        
        Args:
            total: KDV dahil toplam tutar
            rate: KDV oranı (%)
            
        Returns:
            KDVResult: Hesaplama sonucu
        """
        try:
            total = Decimal(str(total))
            rate = Decimal(str(rate))

            if total < 0:
                return KDVResult(
                    is_valid=False,
                    subtotal=Decimal("0"),
                    kdv_amount=Decimal("0"),
                    total=total,
                    kdv_rate=rate,
                    error_message="Toplam tutar negatif olamaz"
                )

            # subtotal = total / (1 + rate/100)
            divisor = Decimal("1") + (rate / Decimal("100"))
            subtotal = (total / divisor).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            kdv_amount = total - subtotal

            return KDVResult(
                is_valid=True,
                subtotal=subtotal,
                kdv_amount=kdv_amount,
                total=total,
                kdv_rate=rate
            )

        except Exception as e:
            logger.error(f"KDV geriye hesaplama hatası: {e}")
            return KDVResult(
                is_valid=False,
                subtotal=Decimal("0"),
                kdv_amount=Decimal("0"),
                total=total,
                kdv_rate=rate,
                error_message=f"Hesaplama hatası: {str(e)}"
            )