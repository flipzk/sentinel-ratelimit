# Sentinel — Adaptive Rate Limiting Service

Sentinel is a high-performance, distributed rate limiting service designed for financial APIs where precision and reliability are critical. Unlike standard fixed-window limiters, Sentinel implements **adaptive quotas** based on user tiers and utilizes **Redis Lua scripts** to ensure atomicity in distributed environments, preventing race conditions.

## Key Features

* **Distributed & Atomic:** Uses Redis as a centralized state store with Lua scripting to guarantee atomic operations (check-and-decrement), eliminating race conditions common in high-concurrency scenarios.
* **Adaptive Throttling:** Dynamic rate limits based on client identity (API Key tiers) rather than a global fixed limit.
* **Pluggable Strategies:** Support for multiple algorithms, configurable at runtime:
    * **Token Bucket:** Efficient, low memory footprint, ideal for bursty traffic.
    * **Sliding Window Log:** High precision, eliminates "boundary hopping" attacks, ideal for strict financial quotas.
* **Observability:** Structured JSON logging (via `structlog`) enabling integration with APM tools like Datadog or ELK.
* **Fail-Open Design:** Middleware architecture designed to handle strategy failures gracefully (configurable).

## Technical Stack

* **Language:** Python 3.11 (Strict Typing)
* **Framework:** FastAPI / Starlette
* **Storage:** Redis 7 (AsyncIO)
* **Containerization:** Docker & Docker Compose
* **Testing:** Pytest (Async), Mocking

## Architecture Overview

The system follows a Hexagonal / Ports & Adapters architecture to decouple the core algorithm from the HTTP framework.

1.  **Middleware Layer:** Intercepts requests, extracts client identity, and retrieves the assigned quota via `QuotaManager`.
2.  **Strategy Pattern:** The middleware delegates the calculation to a concrete strategy (`TokenBucket` or `SlidingWindow`).
3.  **Storage Layer:** Executes atomic Lua scripts against Redis to calculate remaining tokens/slots.

## Quick Start

### Prerequisites
* Docker and Docker Compose

### Running the Service
The entire stack is containerized. To build and start the service:

```bash
docker compose up --build

The API will be available at http://localhost:8000.Usage & TestingYou can test the adaptive limits using curl. The service identifies users via the X-API-Key header.1. Free Tier (Anonymous)Limit: 5 requests / 60sBashcurl -i http://localhost:8000/test
Response Headers: X-RateLimit-Limit: 52. Premium TierLimit: 50 requests / 60sBashcurl -i -H "X-API-Key: prem_user1" http://localhost:8000/test
Response Headers: X-RateLimit-Limit: 503. VIP TierLimit: 500 requests / 60sBashcurl -i -H "X-API-Key: vip_boss" http://localhost:8000/test
Response Headers: X-RateLimit-Limit: 500ConfigurationConfiguration is managed via environment variables (or .env file).VariableDefaultDescriptionREDIS_URLredis://redis:6379/0Connection string for the Redis backend.RATE_LIMIT_STRATEGYtoken_bucketAlgorithm to use: token_bucket or sliding_window.RATE_LIMIT_DEFAULT100Fallback limit if no quota is found.RATE_LIMIT_WINDOW60Time window in seconds.To switch algorithms, change RATE_LIMIT_STRATEGY to sliding_window in docker-compose.yml and restart the service.Project StructurePlaintextsrc/sentinel
├── api/             # HTTP Layer (Middleware, Routes, Dependencies)
├── core/
│   ├── strategies/  # Rate Limiting Logic (Token Bucket, Sliding Window)
│   ├── storage/     # Redis Backend & Lua Scripts
│   ├── quota.py     # Business Logic for User Tiers
│   └── logging.py   # Structured Logging Configuration
└── config.py        # Settings Management