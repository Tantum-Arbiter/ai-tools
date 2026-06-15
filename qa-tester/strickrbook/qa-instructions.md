# QA Instructions — strickrbook

You are a senior QA engineer reviewing this mobile application. Perform a thorough quality review and report all findings.

## 1. Build & Tests
- Identify the build system (Gradle/Xcode/React Native/Flutter) and run a full build. Report errors.
- Run the full test suite (unit + integration). Report pass/fail counts with failure details.
- Check test coverage. Flag any screens, components, or services with zero test coverage.

## 2. UI & Navigation
- Review all screen components for consistent styling and layout.
- Check that all navigation flows have proper back handling (no dead ends).
- Verify loading states exist for all async operations.
- Check that empty states are handled (no data, first-time user, search with no results).
- Verify error states display user-friendly messages, not raw exceptions.

## 3. Data & State Management
- Review how app state is managed. Check for state that could become stale or inconsistent.
- Verify all API calls have proper error handling (network failure, timeout, 4xx, 5xx).
- Check that offline scenarios are handled gracefully (cached data, queue for retry, clear messaging).
- Verify pagination is implemented correctly where lists could grow large.
- Check for race conditions in concurrent data fetching.

## 4. Accessibility
- Check that all interactive elements have accessibility labels.
- Verify touch targets meet minimum size (44x44 points iOS, 48x48dp Android).
- Check colour contrast ratios on text elements.
- Verify screen reader navigation order is logical.

## 5. Performance
- Identify any components that re-render unnecessarily.
- Check for large images loaded without lazy loading or caching.
- Verify lists use virtualisation for long scrollable content.
- Check for memory leaks in subscriptions, listeners, or timers not cleaned up on unmount.

## 6. Security
- Search for hardcoded API keys, tokens, or secrets.
- Verify sensitive data (auth tokens, user data) is stored in secure storage, not plain preferences.
- Check that API calls use HTTPS exclusively.
- Verify deep links and URL schemes validate input before acting on it.

## 7. Output Format
Write all findings to windsurf-output.txt in this format:
```
[TIMESTAMP] CATEGORY: SEVERITY (critical/high/medium/low) — Finding description
  File: <path>
  Line: <number>
  Recommendation: <fix>
```
End with a summary: total findings by severity, overall quality assessment, and top 3 priorities.
