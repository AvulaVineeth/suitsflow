from uuid import UUID

from suitsflow.schemas.scan_job import ScanJobResponse


class ExtractionJobResponse(ScanJobResponse):
    extractor: str
    result_id: UUID | None
