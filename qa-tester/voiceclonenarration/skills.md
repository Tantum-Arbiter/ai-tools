# Skills — voiceclonenarration

## Domain Knowledge

### Voice Cloning
- Understand TTS (Text-to-Speech) and voice conversion architectures
- Familiar with speaker embedding extraction and voice similarity metrics
- Know common voice cloning models: Tortoise-TTS, XTTS, Bark, Coqui TTS, OpenVoice
- Understand mel spectrogram generation and vocoder pipelines (HiFi-GAN, WaveGlow)

### Audio Processing
- PCM audio formats: sample rate, bit depth, channels, endianness
- Audio codec handling: WAV (uncompressed), MP3 (lossy), FLAC (lossless), OGG/Vorbis
- Resampling algorithms and quality trade-offs (linear, sinc, polyphase)
- Audio normalisation: peak normalisation, LUFS loudness normalisation
- Silence detection and trimming
- Audio concatenation with crossfade blending

### ML Inference
- PyTorch model loading, state_dict management, device placement (CPU/GPU)
- ONNX Runtime inference for production deployment
- Batch inference strategies and memory management
- Mixed precision (FP16/BF16) inference for GPU acceleration
- Model quantisation (INT8, INT4) for reduced memory footprint

## QA Patterns to Check

### Common Bugs in Voice Cloning Tools
- Sample rate mismatch between input audio and model expectation
- Channel count mismatch (mono vs stereo) causing shape errors
- Memory accumulation when processing long audio sequences
- GPU OOM on large batch sizes without fallback
- Temp files accumulating when processing fails mid-pipeline
- Race conditions when multiple requests share the same model instance

### Performance Bottlenecks
- Model loading on every request instead of caching
- Unnecessary audio format conversions in the pipeline
- Blocking I/O on the inference thread
- Large audio files loaded entirely into memory instead of streaming

### Security Vulnerabilities
- Arbitrary file read via path traversal in audio file parameters
- SSRF via URL-based audio input without validation
- Denial of service via extremely large or infinite-length audio input
- Model poisoning via unchecked model file uploads
