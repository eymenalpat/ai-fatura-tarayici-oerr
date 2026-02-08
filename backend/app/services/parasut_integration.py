import logging
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from decimal import Decimal
import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)
import json

from app.core.config import settings
from app.models.invoice import Invoice, InvoiceResponse

logger = logging.getLogger(__name__)


class ParasutAPIError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict] = None):
        self.message = message
        self.status_code = status_code
        self.response_data = response_data
        super().__init__(self.message)


class ParasutRateLimitError(ParasutAPIError):
    pass


class ParasutClient:
    def __init__(self):
        self.base_url = settings.PARASUT_API_URL
        self.client_id = settings.PARASUT_CLIENT_ID
        self.client_secret = settings.PARASUT_CLIENT_SECRET
        self.company_id = settings.PARASUT_COMPANY_ID
        self.redirect_uri = settings.PARASUT_REDIRECT_URI
        
        self._token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._client: Optional[httpx.AsyncClient] = None
        
        logger.info("ParasutClient initialized")

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("ParasutClient must be used as async context manager")
        return self._client

    async def _get_token_from_cache(self) -> Optional[str]:
        try:
            if settings.REDIS_ENABLED:
                from app.core.redis import redis_client
                token_data = await redis_client.get("parasut:access_token")
                if token_data:
                    logger.info("Parasüt token retrieved from Redis cache")
                    return token_data
        except Exception as e:
            logger.warning(f"Failed to get token from Redis: {e}")
        return None

    async def _save_token_to_cache(self, token: str, expires_in: int):
        try:
            if settings.REDIS_ENABLED:
                from app.core.redis import redis_client
                await redis_client.setex(
                    "parasut:access_token",
                    expires_in - 60,
                    token
                )
                logger.info(f"Parasüt token cached in Redis for {expires_in - 60}s")
        except Exception as e:
            logger.warning(f"Failed to save token to Redis: {e}")

    async def _is_token_valid(self) -> bool:
        if not self._token or not self._token_expires_at:
            return False
        return datetime.utcnow() < self._token_expires_at - timedelta(minutes=5)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError)
    )
    async def _authenticate(self) -> str:
        cached_token = await self._get_token_from_cache()
        if cached_token:
            self._token = cached_token
            self._token_expires_at = datetime.utcnow() + timedelta(hours=2)
            return cached_token

        if await self._is_token_valid():
            return self._token

        logger.info("Authenticating with Parasüt API (OAuth2 client_credentials)")

        token_url = f"{self.base_url}/oauth/token"
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri
        }

        try:
            response = await self.client.post(token_url, data=payload)
            response.raise_for_status()
            
            token_data = response.json()
            self._token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 7200)
            self._token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            
            await self._save_token_to_cache(self._token, expires_in)
            
            logger.info(f"Successfully authenticated with Parasüt, token expires in {expires_in}s")
            return self._token

        except httpx.HTTPStatusError as e:
            logger.error(f"Parasüt authentication failed: {e.response.status_code} - {e.response.text}")
            raise ParasutAPIError(
                f"Authentication failed: {e.response.text}",
                status_code=e.response.status_code,
                response_data=e.response.json() if e.response.text else None
            )
        except Exception as e:
            logger.error(f"Unexpected error during Parasüt authentication: {e}")
            raise ParasutAPIError(f"Authentication error: {str(e)}")

    async def _get_headers(self) -> Dict[str, str]:
        token = await self._authenticate()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=30),
        retry=retry_if_exception_type((httpx.RequestError, ParasutRateLimitError))
    )
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/{self.company_id}/{endpoint}"
        headers = await self._get_headers()

        try:
            response = await self.client.request(
                method=method,
                url=url,
                json=data,
                params=params,
                headers=headers
            )

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                logger.warning(f"Parasüt rate limit hit, retry after {retry_after}s")
                raise ParasutRateLimitError(
                    f"Rate limit exceeded, retry after {retry_after}s",
                    status_code=429
                )

            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            error_message = f"Parasüt API error: {e.response.status_code}"
            error_data = None
            
            try:
                error_data = e.response.json()
                error_message = f"{error_message} - {json.dumps(error_data)}"
            except:
                error_message = f"{error_message} - {e.response.text}"

            logger.error(error_message)
            raise ParasutAPIError(
                error_message,
                status_code=e.response.status_code,
                response_data=error_data
            )

        except httpx.RequestError as e:
            logger.error(f"Request error to Parasüt: {e}")
            raise

    def _convert_invoice_to_parasut_format(self, invoice: Invoice) -> Dict[str, Any]:
        extracted = invoice.extracted_data or {}
        
        contact_data = {
            "name": extracted.get("vendor_name", "Unknown Vendor"),
            "email": extracted.get("vendor_email"),
            "tax_number": extracted.get("vendor_tax_id"),
            "tax_office": extracted.get("vendor_tax_office")
        }

        line_items = []
        items_data = extracted.get("line_items", [])
        
        for idx, item in enumerate(items_data):
            quantity = Decimal(str(item.get("quantity", 1)))
            unit_price = Decimal(str(item.get("unit_price", 0)))
            kdv_rate = Decimal(str(item.get("kdv_rate", 20)))
            
            line_items.append({
                "product_id": None,
                "description": item.get("description", f"Item {idx + 1}"),
                "quantity": float(quantity),
                "unit_price": float(unit_price),
                "vat_rate": float(kdv_rate),
                "discount_type": "percentage",
                "discount_value": 0
            })

        invoice_date = extracted.get("invoice_date")
        if isinstance(invoice_date, str):
            try:
                invoice_date = datetime.fromisoformat(invoice_date.replace('Z', '+00:00'))
            except:
                invoice_date = datetime.utcnow()
        elif not isinstance(invoice_date, datetime):
            invoice_date = datetime.utcnow()

        due_date = extracted.get("due_date")
        if isinstance(due_date, str):
            try:
                due_date = datetime.fromisoformat(due_date.replace('Z', '+00:00'))
            except:
                due_date = invoice_date + timedelta(days=30)
        elif not isinstance(due_date, datetime):
            due_date = invoice_date + timedelta(days=30)

        parasut_invoice = {
            "data": {
                "type": "sales_invoices",
                "attributes": {
                    "item_type": "invoice",
                    "description": extracted.get("invoice_number", f"Invoice {invoice.id}"),
                    "issue_date": invoice_date.strftime("%Y-%m-%d"),
                    "due_date": due_date.strftime("%Y-%m-%d"),
                    "invoice_series": extracted.get("invoice_series"),
                    "invoice_id": extracted.get("invoice_number"),
                    "currency": extracted.get("currency", "TRY"),
                    "exchange_rate": 1.0,
                    "withholding_rate": 0,
                    "vat_withholding_rate": 0,
                    "invoice_discount_type": "percentage",
                    "invoice_discount": 0,
                    "billing_address": extracted.get("vendor_address"),
                    "billing_phone": extracted.get("vendor_phone"),
                    "billing_fax": None,
                    "tax_office": contact_data.get("tax_office"),
                    "tax_number": contact_data.get("tax_number"),
                    "city": None,
                    "district": None,
                    "is_abroad": False,
                    "order_no": None,
                    "order_date": None,
                    "shipment_addres": None,
                    "shipment_included": False
                },
                "relationships": {
                    "details": {
                        "data": [
                            {
                                "type": "sales_invoice_details",
                                "attributes": item
                            }
                            for item in line_items
                        ]
                    },
                    "contact": {
                        "data": {
                            "type": "contacts",
                            "attributes": contact_data
                        }
                    }
                }
            }
        }

        return parasut_invoice

    async def export_invoice(self, invoice: Invoice) -> Dict[str, Any]:
        if not invoice.extracted_data:
            raise ParasutAPIError("Invoice has no extracted data to export")

        logger.info(f"Exporting invoice {invoice.id} to Parasüt")

        try:
            parasut_data = self._convert_invoice_to_parasut_format(invoice)
            
            result = await self._make_request(
                method="POST",
                endpoint="sales_invoices",
                data=parasut_data
            )

            parasut_invoice_id = result.get("data", {}).get("id")
            
            logger.info(f"Successfully exported invoice {invoice.id} to Parasüt (ID: {parasut_invoice_id})")

            return {
                "success": True,
                "parasut_invoice_id": parasut_invoice_id,
                "message": "Invoice successfully exported to Parasüt",
                "data": result
            }

        except ParasutAPIError as e:
            logger.error(f"Failed to export invoice {invoice.id}: {e.message}")
            raise

        except Exception as e:
            logger.error(f"Unexpected error exporting invoice {invoice.id}: {e}")
            raise ParasutAPIError(f"Export failed: {str(e)}")

    async def get_invoice(self, parasut_invoice_id: str) -> Dict[str, Any]:
        logger.info(f"Fetching invoice {parasut_invoice_id} from Parasüt")
        
        try:
            result = await self._make_request(
                method="GET",
                endpoint=f"sales_invoices/{parasut_invoice_id}"
            )
            return result

        except ParasutAPIError as e:
            logger.error(f"Failed to fetch invoice {parasut_invoice_id}: {e.message}")
            raise

    async def list_contacts(self, search: Optional[str] = None) -> Dict[str, Any]:
        logger.info("Fetching contacts from Parasüt")
        
        params = {}
        if search:
            params["filter[name]"] = search

        try:
            result = await self._make_request(
                method="GET",
                endpoint="contacts",
                params=params
            )
            return result

        except ParasutAPIError as e:
            logger.error(f"Failed to fetch contacts: {e.message}")
            raise

    async def health_check(self) -> bool:
        try:
            await self._authenticate()
            logger.info("Parasüt health check passed")
            return True
        except Exception as e:
            logger.error(f"Parasüt health check failed: {e}")
            return False


parasut_client = ParasutClient()