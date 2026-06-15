# Skills — colearn

## Domain Knowledge

### Spring Boot
- Spring Boot 3.x auto-configuration and starter dependencies
- Spring Security filter chain, authentication providers, and method security
- Spring Data JPA repository patterns, specifications, and projections
- Spring profiles and externalised configuration hierarchy
- Spring Actuator endpoints, health indicators, and custom metrics
- Spring WebMVC exception handling with `@ControllerAdvice`

### Java Backend Patterns
- DTO mapping (MapStruct, record-based DTOs)
- Service layer transaction management and boundary design
- Repository pattern with custom query methods
- Builder and factory patterns for test data
- Pagination and sorting with Spring Data `Pageable`

### Data & Persistence
- JPA/Hibernate entity mapping, relationships, and fetch strategies
- HikariCP connection pool configuration and monitoring
- Flyway/Liquibase migration versioning and rollback strategies
- Query performance: N+1 detection, join fetch, batch size tuning
- Database indexing strategies for common query patterns

## QA Patterns to Check

### Common Spring Boot Bugs
- `@Transactional` on private methods (silently ignored by proxy)
- `LazyInitializationException` from accessing lazy relations outside session
- `@Async` methods called from within the same class (proxy bypass)
- Missing `@Valid` on nested objects in request DTOs
- `@RequestBody` without `@Valid` — accepts any input without validation
- Circular dependency between beans causing startup failure
- Profile-specific properties overriding security settings

### Security Vulnerabilities
- Actuator endpoints exposed without authentication
- IDOR: endpoint returns data for any ID without ownership check
- Mass assignment: entity fields settable via API that shouldn't be (role, isAdmin)
- JWT not validated for expiry or signature (only decoded)
- SQL injection via native queries with string concatenation
- CORS wildcard (`*`) in production configuration
- Sensitive data in logs (passwords, tokens, PII)

### Performance Issues
- N+1 queries in list endpoints with entity relationships
- Missing database indexes on frequently queried columns
- No connection pool limits — defaults allow unbounded connections
- Synchronous external API calls blocking request threads
- Large result sets without pagination limits
