# Rules — strickrbook

## Language & Framework
- Identify the framework (React Native / Flutter / Swift / Kotlin) from project config
- Follow the framework's official style guide and best practices
- Use the project's established patterns — do not introduce new paradigms

## UI & Components
- Every screen must have a loading state, error state, and empty state
- All interactive elements must have accessibility labels
- Touch targets must meet minimum size: 44x44pt (iOS) / 48x48dp (Android)
- Colour contrast must meet WCAG AA (4.5:1 for normal text, 3:1 for large text)
- No hardcoded pixel values — use responsive units or design tokens
- Animations must respect reduced-motion accessibility settings

## Navigation
- Every screen must be reachable and have a way back (no dead ends)
- Deep links must validate parameters before navigating
- Navigation state must survive app backgrounding and foregrounding
- Back button / swipe-back must work correctly on all screens

## State Management
- State must have a single source of truth — no duplicated state
- API calls must handle: success, loading, error, empty, and timeout states
- Offline mode must be handled gracefully (cached data or clear messaging)
- Subscriptions, listeners, and timers must be cleaned up on component unmount
- Pagination must handle end-of-list, refresh, and concurrent load correctly

## Performance
- Lists must use virtualisation (FlatList, RecyclerView, ListView.builder)
- Images must use lazy loading and caching (no raw URL loading)
- Avoid unnecessary re-renders — memoize expensive computations
- No synchronous blocking on the main/UI thread
- Bundle size must be monitored — flag large unused dependencies

## Security
- No hardcoded API keys, tokens, or secrets in source code
- Auth tokens must be stored in secure storage (Keychain / Keystore), not AsyncStorage/SharedPreferences
- All API calls must use HTTPS — no HTTP fallback
- Deep link and URL scheme handlers must validate and sanitise input
- Biometric auth must have a fallback mechanism

## Testing
- Unit tests for all business logic and utility functions
- Component tests for all reusable UI components
- Integration tests for critical user flows (auth, main feature, payment)
- Snapshot tests for visual regression on key screens
- Mock all network calls in tests
