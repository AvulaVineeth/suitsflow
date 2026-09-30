"""Private worker protocol: bounded stdin PDF, stdout UTF-8, fixed exit codes."""

import platform
import sys


def main() -> int:
    if platform.system() != "Linux":
        return 5
    import resource

    try:
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    except (ValueError, OSError):
        return 5
    try:
        from io import BytesIO

        from pypdf import PdfReader

        content = sys.stdin.buffer.read(2 * 1024 * 1024 + 1)
        if len(content) > 2 * 1024 * 1024:
            return 3
        reader = PdfReader(BytesIO(content), strict=True)
        if reader.is_encrypted:
            return 4
        if len(reader.pages) > 100:
            return 3
        parts: list[str] = []
        characters = stream_bytes = 0
        for page in reader.pages:
            stream = page.get_contents()
            if stream is not None:
                stream_bytes += len(stream.get_data())
                if stream_bytes > 8 * 1024 * 1024:
                    return 3
            text = page.extract_text()
            characters += len(text) + (1 if parts else 0)
            if characters > 1_000_000:
                return 3
            parts.append(text)
        text = "\n".join(parts)
        if not text.strip():
            return 4  # No OCR fallback or false claim of successful empty extraction.
        sys.stdout.buffer.write(text.encode("utf-8"))
        return 0
    except (MemoryError, RecursionError):
        return 3
    except Exception:
        return 4  # Never expose parser diagnostics or source content to clients/logs.


if __name__ == "__main__":
    raise SystemExit(main())
