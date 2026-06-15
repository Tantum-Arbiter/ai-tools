# QA Instructions — Photoshop AI Tool

You are a senior QA engineer reviewing this Photoshop AI tool/plugin. Perform a thorough quality review and report all findings.

## 1. Build & Tests
- Identify the build system and run a full build. Report any compilation or dependency errors.
- Run the full test suite. Report pass/fail counts with failure root cause analysis.
- Flag any modules, functions, or handlers with zero test coverage.

## 2. Image Processing Pipeline
- Trace the image processing pipeline from input to output.
- Check edge cases: zero-dimension images, extremely large images (>100MP), corrupt file headers, unsupported colour spaces (CMYK, LAB, 16-bit).
- Verify alpha channel and transparency are preserved through all transformations.
- Check that colour profiles (sRGB, Adobe RGB, ProPhoto) are handled correctly.
- Verify intermediate image buffers are released after processing (no memory leaks).
- Check that temp files are cleaned up on success and failure.

## 3. AI Model Integration
- Review how ML models are loaded. Check for graceful failure if model file is missing, corrupt, or wrong version.
- Verify inference has proper timeout handling for large images.
- Check GPU/CPU fallback logic works correctly.
- Verify batch processing handles partial failures without crashing.
- Check that model output is validated before applying to the image (bounds checking, NaN detection).

## 4. Plugin API & Photoshop Integration
- Review all Photoshop API calls for correct usage and version compatibility.
- Check that the plugin handles Photoshop being closed or document being closed mid-operation.
- Verify undo history integration (user can undo AI operations).
- Check that layer handling is correct (non-destructive edits, correct layer ordering).
- Verify the plugin respects the active selection and mask boundaries.

## 5. Input Validation & Error Handling
- Review all user-facing inputs (sliders, text fields, file selectors) for validation.
- Check that invalid parameter combinations are caught before processing starts.
- Verify error messages are user-friendly and actionable (not raw stack traces).
- Check that progress indicators are shown for long-running operations.
- Verify cancellation works correctly mid-processing (cleanup, no corrupt state).

## 6. Performance
- Check for unnecessary image copies or duplications in memory.
- Verify large images are processed in tiles or chunks where possible.
- Check that UI remains responsive during processing (async/worker thread).
- Identify any synchronous blocking calls on the main thread.

## 7. Security
- Search for hardcoded API keys, tokens, or credentials.
- Check that any cloud API calls use HTTPS and validate certificates.
- Verify user images are not sent to external services without explicit consent.
- Check for path traversal in any file path handling.
- Verify plugin permissions are minimal (no unnecessary filesystem or network access).

## 8. Output Format
Write all findings to windsurf-output.txt in this format:
```
[TIMESTAMP] CATEGORY: SEVERITY (critical/high/medium/low) — Finding description
  File: <path>
  Line: <number>
  Recommendation: <fix>
```
End with a summary: total findings by severity, overall quality assessment, and top 3 priorities.
