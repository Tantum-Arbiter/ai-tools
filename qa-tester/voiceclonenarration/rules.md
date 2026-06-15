# Rules — voiceclonenarration

## Language & Runtime
- Python 3.11+
- Use type hints on all function signatures
- Use `pathlib.Path` over `os.path` for file operations
- Use `with` statements for all file and resource handles
- Prefer `asyncio` for I/O-bound operations

## Audio Standards
- All audio processing must support: WAV, MP3, FLAC, OGG at minimum
- Default sample rate: 44100 Hz (configurable)
- Default bit depth: 16-bit (configurable)
- Always validate audio file headers before processing
- Never assume audio duration — always read from metadata or calculate
- Release audio buffers explicitly after processing (do not rely on GC)

## ML Model Standards
- Models must be loaded lazily (not at import time)
- Model loading must have a timeout (default: 60s)
- Always validate model version compatibility before inference
- GPU inference must fall back to CPU gracefully with a warning log
- Model outputs must be bounds-checked before applying to audio

## Error Handling
- Never swallow exceptions silently
- All exceptions must be logged with context (input file, operation, parameters)
- API errors must return structured JSON with error code, message, and request ID
- Never expose stack traces or internal paths in API responses

## Security
- No hardcoded secrets — use environment variables or secret manager
- Validate and sanitise all file paths (prevent path traversal)
- Enforce file size limits before reading into memory
- Scan uploaded files for valid audio headers (don't trust file extensions)
- All external API calls must use HTTPS with certificate validation

## Testing
- Unit tests for all audio transformation functions
- Integration tests for the full pipeline (input → model → output)
- Edge case tests: empty files, corrupt headers, maximum file size, concurrent requests
- Mock external services in tests (never call real APIs)

## File Management
- All temp files must use a context manager or try/finally for cleanup
- Temp directory must be configurable (not hardcoded to /tmp)
- Output files must be written atomically (write to temp, then rename)
