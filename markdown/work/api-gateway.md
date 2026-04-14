---
title: Building a Self-Serve API Gateway to Decompose a Monolith
subtitle: Designed and built a high-performance API gateway enabling incremental migration from a legacy monolith to 150+ independently owned services, handling ~2000 RPS with ~50ms p99 overhead and 99.99999% availability.
---

## Context

This project focused on evolving a legacy Ruby on Rails monolith that powered a cloud provider control plane
into a service-oriented architecture. The monolith handled all user-facing and API traffic and had become
increasingly difficult to scale, deploy, and evolve across teams.

The system operated at high scale, serving all requests to customer-facing web and API endpoints. Reliability
and latency were critical, as the gateway sat directly in the request path for all control plane operations.

I worked as a staff engineer leading the design and implementation of a new API gateway that would enable
teams to extract and own services independently without disrupting existing traffic.

## Problem

The monolith had become a bottleneck for both scalability and team velocity. Deployments were high-risk,
ownership boundaries were unclear, and scaling specific functionality required scaling the entire application.

A key requirement was to incrementally migrate functionality out of the monolith without breaking existing
clients or introducing downtime. Existing solutions like traditional reverse proxies and load balancers did
not provide sufficient flexibility for dynamic routing, request/response transformation, and service-specific
logic.

At the same time, the gateway needed to operate in the critical path with strict requirements for latency,
availability, and correctness. It also had to support cross-cutting concerns such as authentication, rate
limiting, logging, and distributed tracing, all while remaining extensible for future use cases.

## Goals

- Enable incremental decomposition of the monolith
- Support self-serve onboarding of services
- Maintain low latency in the critical path
- Provide consistent auth, rate limiting, tracing
- Prevent cascading failures

## System Architecture

```diagram
direction: down

clients: {
  web: "Web App (cloud UI)"
  api: "API Clients"
}

gateway: {
  label: "API Gateway\n(Critical Path)\n~2000 RPS | ~50ms p99 | 99.99999% availability"

  routing: "Routing Layer"
  filters: "Filter Pipeline"
  observability: "Logging / Metrics / Tracing"
}

services: {
  label: "Backend Services (150+)"
  s1: "Service A"
  s2: "Service B"
  s3: "Service C"
}

auth: "Auth Service"
meta: "User Metadata Service"

clients.web -> gateway
clients.api -> gateway

gateway -> services.s1
gateway -> services.s2
gateway -> services.s3

gateway -> auth
gateway -> meta

gateway.routing -> gateway.filters
gateway.filters -> gateway.observability
```

## Approach

Instead of relying on existing proxy solutions, I designed a custom API gateway tailored to the system's
needs. The core idea was to create a flexible request processing pipeline that allowed dynamic routing and
composable request/response transformations.

The gateway introduced a filter-based architecture, where "before" and "after" filters could be applied to
requests and responses. This enabled teams to define service-specific behavior while still leveraging shared
infrastructure for common concerns like authentication and observability.

A strong emphasis was placed on making the system self-serve, allowing teams to onboard new services without
requiring changes to the gateway core.

## Request Processing Pipeline

```diagram
<!-- pipeline diagram -->
```

## Key Challenges

### Avoiding Authentication Bottlenecks

Problem: Authentication and user metadata lookups were required for most requests, creating a risk of
overwhelming backing data stores during traffic spikes.

Solution: Introduced request coalescing using Go's singleflight pattern combined with aggressive caching.
Identical concurrent requests for the same authentication data were deduplicated, ensuring only one upstream
call was made.

Why it works: This significantly reduced duplicate work under bursty traffic patterns, smoothing load on
downstream systems and improving latency.

Trade-off: Slight increase in complexity and potential for stale cache data, mitigated through careful TTL
tuning.

### Connection Management & TIME_WAIT

Problem: High request volume led to rapid connection churn, causing large numbers of TCP connections to
enter TIME_WAIT, eventually exhausting the ephemeral port range.

Solution: Optimized connection reuse through persistent connections and tuned idle connection pools. Reduced
unnecessary connection teardown and ensured efficient reuse of existing connections.

Why it works: Minimizing connection churn reduces pressure on the OS networking stack and avoids port
exhaustion, improving overall system stability.

Trade-off: Required careful tuning of idle timeouts and connection limits to avoid resource leaks.

### Resilience & Failover

Problem: Failures in downstream services or regions could propagate and degrade the entire system.

Solution: Implemented circuit breakers, retries with exponential backoff and jitter, and regional failover
mechanisms.

Why it works: These mechanisms isolate failures and reduce amplification effects, maintaining overall system
availability.

## Results & Impact

- **~2000 RPS** sustained throughput
- **~50ms p99** latency overhead
- **99.99999%** availability
- **150+ services** onboarded

## Observability

![Gateway latency remained stable at ~50ms p99 under load.](/images/grafana-latency.png)

![Sustained throughput of ~2000 requests per second.](/images/grafana-rps.png)

## My Contributions

- Led end-to-end architecture and design
- Built routing and filter pipeline
- Designed self-serve service onboarding
- Implemented caching and request coalescing
- Resolved connection-level scaling issues
- Introduced resilience patterns

## Lessons Learned

Balancing flexibility with guardrails was critical. The filter-based architecture gave teams tremendous power
to customize behavior, but without clear conventions it risked becoming a source of hidden complexity. Early
investment in documentation and opinionated defaults paid dividends as the number of onboarded services grew.
