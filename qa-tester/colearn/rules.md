# Rules — colearn

## Language & Framework
- Java 21+ with Spring Boot 3.x
- Use Gradle as the build tool
- Follow Spring Boot conventions and project structure

## API Design
- All endpoints must have explicit request/response DTOs (no entity exposure)
- All input must be validated with `@Valid` and Bean Validation annotations
- All endpoints must return appropriate HTTP status codes (201 for create, 204 for delete, etc.)
- Error responses must follow RFC 7807 Problem Detail format
- All list endpoints must support pagination (default page size, max cap)
- API versioning must be consistent (path-based or header-based, not mixed)

## Authentication & Authorisation
- No endpoint is public by default — explicitly configure permitted paths
- Use method-level security (`@PreAuthorize`) for role-based access
- JWT validation must check: expiry, signature, issuer, and audience
- All resource access must verify ownership (prevent IDOR)
- CORS origins must be explicitly listed — no wildcards in production profiles

## Data Layer
- All database queries must use parameterised statements (no string concatenation)
- Entity relationships must use `FetchType.LAZY` by default
- Add `@BatchSize` or join fetch to prevent N+1 queries
- Database migrations must be idempotent and versioned (Flyway or Liquibase)
- Sensitive fields (passwords, PII) must be encrypted and excluded from logs
- Connection pool must be configured explicitly (HikariCP settings)

## Error Handling
- Use `@ControllerAdvice` for global exception handling
- Never expose stack traces in API responses
- All external service calls must have timeouts (connect + read)
- Use circuit breaker on critical downstream dependencies
- `@Transactional` boundaries must be explicit — do not rely on defaults

## Security
- No secrets in source code or config files — use environment variables or vault
- Actuator endpoints must be secured (`/env`, `/configprops`, `/heapdump` restricted)
- Spring profiles must not leak dev/test configuration to production
- Rate limiting must be applied on authentication and public endpoints
- Content-Type must be validated on all request bodies

## Testing
- Use JUnit 5 with AssertJ for assertions
- Use Mockito for mocking dependencies
- Use Testcontainers for integration tests (database, message broker)
- Controller tests must verify status codes, response structure, and error cases
- Service tests must cover happy path, edge cases, and failure scenarios
- Repository tests must verify custom queries against a real database
