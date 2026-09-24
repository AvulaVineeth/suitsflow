from collections.abc import Iterator

from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from suitsflow.services.downloads import Download


class DownloadResponse(StreamingResponse):
    """Own the temporary file through response completion, including client disconnects."""

    def __init__(self, download: Download) -> None:
        self.file = download.body

        def chunks() -> Iterator[bytes]:
            while chunk := self.file.read(65536):
                yield chunk

        super().__init__(
            chunks(),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{download.filename}"',
                "Content-Length": str(download.size),
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.file.close()
