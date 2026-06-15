# Skills — photoshop-ai

## Domain Knowledge

### Photoshop Plugin Development
- UXP (Unified Extensibility Platform) plugin architecture and lifecycle
- CEP (Common Extensibility Platform) and ExtendScript for legacy support
- Photoshop DOM API: Document, Layer, Selection, History, Color models
- BatchPlay commands for high-performance Photoshop operations
- Plugin manifest configuration and permission declarations

### Image Processing
- Raster image formats: PSD, TIFF, PNG, JPEG, WebP, EXR, HDR
- Colour models: RGB, CMYK, LAB, HSB/HSL, Grayscale
- ICC colour profiles and colour management workflows
- Image compositing: blending modes, opacity, masks, alpha channels
- Spatial transformations: resize, rotate, warp, perspective
- Tiled processing for large images (chunk-based memory management)

### AI/ML for Image Processing
- Image generation models: Stable Diffusion, DALL-E, Midjourney architectures
- Image-to-image models: inpainting, outpainting, super-resolution, style transfer
- Segmentation models: SAM, U-Net for mask generation
- ONNX Runtime and CoreML for cross-platform inference
- Quantisation (INT8/INT4) and pruning for reduced model size
- ControlNet and similar guided generation techniques

## QA Patterns to Check

### Common Plugin Bugs
- Plugin crash when no document is open
- Layer operations fail on locked or grouped layers
- Colour space conversion loses precision (8-bit truncation from 16-bit source)
- Alpha channel dropped during AI processing
- Undo doesn't restore original state (partial undo)
- Plugin UI freezes during inference (blocking main thread)
- Memory not freed after closing document with active AI processing

### Image Processing Issues
- Edge artifacts from tiled processing (seam lines between tiles)
- Colour banding from bit depth reduction
- EXIF/metadata stripped from output without user consent
- Colour profile mismatch between input and output
- Transparent regions filled with black/white during processing
- Very large images cause OOM without useful error message

### Security & Privacy Vulnerabilities
- User images uploaded to cloud API without consent dialog
- API keys embedded in plugin bundle (extractable by users)
- Network requests to analytics services without opt-in
- Temp files containing user images not cleaned up
- Plugin requests broader filesystem access than needed
- Model weights downloaded over HTTP (not HTTPS)
