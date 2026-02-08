import io
import logging
from typing import Optional, Dict, Any, Tuple
from google.cloud import vision
from google.cloud.vision_v1 import types
from google.api_core import retry
import asyncio
from concurrent.futures import ThreadPoolExecutor

from app.core.config import settings

logger = logging.getLogger(__name__)


class OCRService:
    def __init__(self):
        self._client: Optional[vision.ImageAnnotatorClient] = None
        self._executor = ThreadPoolExecutor(max_workers=4)
        logger.info("OCRService initialized (lazy client)")

    @property
    def client(self) -> vision.ImageAnnotatorClient:
        if self._client is None:
            try:
                if settings.GOOGLE_APPLICATION_CREDENTIALS:
                    self._client = vision.ImageAnnotatorClient()
                    logger.info("Google Vision client initialized successfully")
                else:
                    raise ValueError("GOOGLE_APPLICATION_CREDENTIALS not configured")
            except Exception as e:
                logger.error(f"Failed to initialize Google Vision client: {e}")
                raise
        return self._client

    async def process_image(
        self,
        file_bytes: bytes,
        mime_type: str,
        filename: str = "document"
    ) -> Tuple[str, Dict[str, Any]]:
        try:
            if mime_type == "application/pdf":
                return await self._process_pdf(file_bytes, filename)
            else:
                return await self._process_image_file(file_bytes, mime_type)
        except Exception as e:
            logger.error(f"OCR processing failed for {filename}: {e}")
            raise

    async def _process_image_file(
        self,
        file_bytes: bytes,
        mime_type: str
    ) -> Tuple[str, Dict[str, Any]]:
        loop = asyncio.get_event_loop()
        
        def _sync_detect():
            image = types.Image(content=file_bytes)
            
            response = self.client.document_text_detection(
                image=image,
                retry=retry.Retry(deadline=60.0)
            )
            
            if response.error.message:
                raise Exception(f"Vision API error: {response.error.message}")
            
            text = response.full_text_annotation.text if response.full_text_annotation else ""
            
            confidence_scores = []
            if response.full_text_annotation and response.full_text_annotation.pages:
                for page in response.full_text_annotation.pages:
                    if page.confidence:
                        confidence_scores.append(page.confidence)
            
            avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
            
            metadata = {
                "confidence": avg_confidence,
                "page_count": len(response.full_text_annotation.pages) if response.full_text_annotation else 1,
                "language_hints": self._extract_languages(response),
                "mime_type": mime_type,
                "ocr_method": "document_text_detection"
            }
            
            return text, metadata
        
        return await loop.run_in_executor(self._executor, _sync_detect)

    async def _process_pdf(
        self,
        file_bytes: bytes,
        filename: str
    ) -> Tuple[str, Dict[str, Any]]:
        loop = asyncio.get_event_loop()
        
        def _sync_detect_pdf():
            input_config = types.InputConfig(
                mime_type="application/pdf",
                content=file_bytes
            )
            
            feature = types.Feature(type_=types.Feature.Type.DOCUMENT_TEXT_DETECTION)
            
            request = types.AnnotateFileRequest(
                input_config=input_config,
                features=[feature]
            )
            
            response = self.client.batch_annotate_files(
                requests=[request],
                retry=retry.Retry(deadline=120.0)
            )
            
            if not response.responses:
                raise Exception("No response from Vision API for PDF")
            
            file_response = response.responses[0]
            
            if file_response.error.message:
                raise Exception(f"Vision API PDF error: {file_response.error.message}")
            
            all_text = []
            confidence_scores = []
            total_pages = len(file_response.responses)
            
            for page_response in file_response.responses:
                if page_response.error.message:
                    logger.warning(f"Page error: {page_response.error.message}")
                    continue
                
                if page_response.full_text_annotation:
                    all_text.append(page_response.full_text_annotation.text)
                    
                    if page_response.full_text_annotation.pages:
                        for page in page_response.full_text_annotation.pages:
                            if page.confidence:
                                confidence_scores.append(page.confidence)
            
            combined_text = "\n\n--- PAGE BREAK ---\n\n".join(all_text)
            avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
            
            metadata = {
                "confidence": avg_confidence,
                "page_count": total_pages,
                "mime_type": "application/pdf",
                "ocr_method": "batch_annotate_files",
                "filename": filename
            }
            
            return combined_text, metadata
        
        return await loop.run_in_executor(self._executor, _sync_detect_pdf)

    def _extract_languages(self, response) -> list[str]:
        languages = set()
        
        if response.full_text_annotation and response.full_text_annotation.pages:
            for page in response.full_text_annotation.pages:
                if hasattr(page, 'property') and page.property:
                    if hasattr(page.property, 'detected_languages'):
                        for lang in page.property.detected_languages:
                            if lang.language_code:
                                languages.add(lang.language_code)
        
        return list(languages)

    async def health_check(self) -> bool:
        try:
            test_image = types.Image(content=b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82')
            
            loop = asyncio.get_event_loop()
            
            def _sync_health():
                self.client.text_detection(image=test_image)
                return True
            
            return await loop.run_in_executor(self._executor, _sync_health)
        except Exception as e:
            logger.error(f"OCR health check failed: {e}")
            return False


ocr_service = OCRService()