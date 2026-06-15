# Rules — photoshop-ai

## Language & Framework
- Identify the plugin framework (UXP, CEP/ExtendScript, C++ SDK) from project config
- Follow Adobe's plugin development guidelines and API versioning
- Use the project's established patterns — do not introduce new paradigms

## Image Processing
- All image operations must preserve alpha channel and transparency
- Colour profile handling must be explicit (sRGB, Adobe RGB, ProPhoto RGB)
- Support common colour spaces: RGB, CMYK, Grayscale, LAB
- Support bit depths: 8-bit, 16-bit, 32-bit per channel
- Large images (>50MP) must be processed in tiles/chunks to prevent OOM
- Intermediate buffers must be released explicitly after use
- All temp files must be cleaned up on success and failure
- Output must be validated before applying to the Photoshop document

## AI Model Standards
- Models must be loaded lazily (not at plugin startup)
- Model loading must have a configurable timeout (default: 120s)
- GPU inference must fall back to CPU with a user-visible warning
- Model output must be bounds-checked (no NaN, no out-of-range values)
- Inference must run on a worker thread — never block the UI thread
- Batch processing must handle partial failures gracefully

## Plugin Integration
- All edits must be non-destructive (new layer or smart object)
- Undo history must record AI operations as a single undoable step
- Plugin must handle document close mid-operation gracefully
- Plugin must respect active selection and mask boundaries
- API version compatibility must be checked at startup

## Error Handling
- Never swallow exceptions silently
- User-facing errors must be clear and actionable (no stack traces)
- Progress indicators must be shown for any operation >1 second
- Cancellation must be supported and must clean up all state
- Invalid parameter combinations must be caught before processing starts

## Security & Privacy
- No hardcoded API keys, tokens, or credentials
- User images must never be sent to external services without explicit consent
- All network calls must use HTTPS with certificate validation
- Plugin permissions must be minimal (no unnecessary FS or network access)
- No telemetry or analytics without user opt-in

## Testing
- Unit tests for all image transformation functions
- Integration tests for the full pipeline (input → model → Photoshop output)
- Edge case tests: zero-dimension, max-size, corrupt, unsupported format
- Memory tests: verify no leaks after processing sequences of images
- Mock Photoshop API in tests (do not require live Photoshop)
