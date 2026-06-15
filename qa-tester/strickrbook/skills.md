# Skills — strickrbook

## Domain Knowledge

### Mobile App Architecture
- Component-based UI architecture (React components, Flutter widgets, SwiftUI views)
- Unidirectional data flow patterns (Redux, Bloc, MVI, TCA)
- Platform-specific lifecycle management (foreground, background, terminated)
- Deep linking and universal links configuration
- Push notification handling and routing

### Accessibility
- WCAG 2.1 AA compliance requirements for mobile
- Screen reader compatibility (VoiceOver for iOS, TalkBack for Android)
- Dynamic type / font scaling support
- Semantic markup and accessibility tree structure
- Focus management and keyboard navigation

### Mobile Performance
- Frame rate analysis (60fps target, jank detection)
- Memory profiling and leak detection patterns
- Network request optimisation (batching, caching, prefetching)
- Image optimisation (WebP, progressive loading, CDN sizing)
- App startup time and cold/warm launch optimisation

## QA Patterns to Check

### Common Mobile Bugs
- State not restored after app kill and restart
- Keyboard covering input fields without scroll adjustment
- Pull-to-refresh not clearing error states
- Race condition between navigation and async data loading
- Memory leak from uncleared event listeners or subscriptions
- Crash on rapid back-button presses during transitions
- Data loss when network drops mid-submission

### Platform-Specific Issues
- iOS: safe area insets not respected on notched devices
- iOS: large title navigation bar collapsing incorrectly
- Android: back button behaviour inconsistent with system expectations
- Android: permission dialogs not handled for "Don't ask again" state
- Both: landscape orientation breaking layouts

### Security Vulnerabilities
- API tokens stored in plain text preferences
- Sensitive data visible in app screenshots (task switcher)
- Debug logs containing user data in release builds
- Certificate pinning not implemented for critical API calls
- Clipboard containing sensitive data not cleared on background
