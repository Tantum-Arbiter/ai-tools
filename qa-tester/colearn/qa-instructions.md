# QA Instructions — colearn

You are a senior QA engineer reviewing this Spring Boot API application. Perform a thorough quality review and report all findings.

## 1. Build & Tests
- Run `./gradlew build` (or `./mvnw verify`). Report any compilation or dependency errors.
- Run the full test suite. Report pass/fail counts with failure root cause analysis.
- Check test coverage. Flag any controllers, services, or repositories with zero coverage.
- Verify integration tests use proper test containers or mocks, not external dependencies.

## 2. API Endpoints
- Review all REST controllers. Check that every endpoint has proper input validation (@Valid, custom validators).
- Verify all endpoints return appropriate HTTP status codes (not just 200 for everything).
- Check that error responses follow a consistent structure (problem detail / error envelope).
- Verify pagination is implemented on all list endpoints that could return unbounded results.
- Check for missing or inconsistent path/query parameter validation.

## 3. Authentication & Authorisation
- Review security configuration. Verify no endpoints are accidentally public.
- Check that role-based access control is applied consistently.
- Verify JWT/session token validation covers expiry, signature, and claims.
- Check for IDOR vulnerabilities (user A accessing user B's resources by changing IDs).
- Verify CORS configuration is not overly permissive (no wildcard origins in production).

## 4. Data Layer
- Review repository queries for SQL/JPQL injection risks (verify parameterised queries).
- Check for N+1 query problems in entity relationships (missing @BatchSize, join fetch).
- Verify database migrations are idempotent and have rollback scripts.
- Check that sensitive data (passwords, PII) is encrypted at rest and not logged.
- Verify connection pool settings are configured (not using defaults).

## 5. Error Handling & Resilience
- Check that all external service calls have timeouts configured.
- Verify circuit breaker or retry patterns on critical dependencies.
- Check that exceptions are caught at appropriate levels (not swallowed silently).
- Verify that stack traces are not leaked to API consumers.
- Check for proper transaction management (@Transactional boundaries).

## 6. Security
- Search for hardcoded secrets, API keys, or credentials in source code and config files.
- Verify application.yml/properties does not contain production secrets (should use env vars or vault).
- Check for mass assignment vulnerabilities (DTOs accepting fields they shouldn't).
- Verify Content-Type validation on request bodies.
- Check for missing rate limiting on public or auth endpoints.

## 7. Spring Boot Specifics
- Verify actuator endpoints are secured (not publicly exposing /env, /configprops, /heapdump).
- Check that profiles are used correctly (no dev/test config leaking to prod).
- Verify health checks cover all critical dependencies (DB, message broker, cache).
- Check for proper use of @Async and thread pool configuration.

## 8. Output Format
Write all findings to windsurf-output.txt in this format:
```
[TIMESTAMP] CATEGORY: SEVERITY (critical/high/medium/low) — Finding description
  File: <path>
  Line: <number>
  Recommendation: <fix>
```
End with a summary: total findings by severity, overall quality assessment, and top 3 priorities.
