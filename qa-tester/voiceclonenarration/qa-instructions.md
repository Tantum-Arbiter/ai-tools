# QA Instructions — voiceclonenarration

You are a senior QA engineer reviewing this voice cloning and narration tool. Perform a thorough quality review and report all findings.

## 1. Build & Tests
- Identify the build system and run a full build. Report any compilation or dependency errors.
- Run the full test suite. Report pass/fail counts and any failures with root cause analysis.
- Identify any untested modules or functions and flag them.

## 2. Audio Pipeline Review
- Trace the audio processing pipeline from input to output.
- Check for edge cases: empty audio input, zero-length files, corrupt file headers, unsupported formats.
- Verify sample rate and bit depth conversions are handled correctly.
- Check that audio buffers are properly released after processing (no memory leaks).
- Verify temp files are cleaned up after processing completes or fails.

## 3. Model Loading & Inference
- Review how ML models are loaded. Check for graceful failure if model file is missing or corrupt.
- Verify model inference has proper timeout handling.
- Check that GPU/CPU fallback logic works correctly.
- Verify batch processing handles partial failures without crashing the full batch.

## 4. API & Input Validation
- Review all API endpoints or CLI entry points for input validation.
- Check for path traversal vulnerabilities in any file upload or file path parameters.
- Verify file size limits are enforced before processing begins.
- Check that error responses include useful messages without leaking internal details.

## 5. Security
- Search for hardcoded API keys, tokens, or credentials in the codebase.
- Check that user-uploaded audio files are stored securely and not publicly accessible.
- Verify any third-party API calls use HTTPS and validate certificates.
- Check for command injection if any shell commands are constructed from user input.

## 6. Output Format
Write all findings to windsurf-output.txt in this format:
```
[TIMESTAMP] CATEGORY: SEVERITY (critical/high/medium/low) — Finding description
  File: <path>
  Line: <number>
  Recommendation: <fix>
```
End with a summary: total findings by severity, overall quality assessment, and top 3 priorities.
