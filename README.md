# RateGuard

RateGuard is a distributed rate limiting library for Python APIs using Redis.

## Features

- Sliding Window Rate Limiting
- Redis Sorted Sets
- FastAPI Middleware
- Distributed API protection
- Works across multiple servers

## How it works

RateGuard uses a **Sliding Window Rate Limiting algorithm** with Redis Sorted Sets.

1. Each request is stored with a timestamp
2. Old requests outside the window are removed
3. Remaining requests are counted
4. If the count exceeds the limit, the request is rejected

This design works across multiple API servers because Redis is shared.

Client → FastAPI → RateGuard → Redis → Decision

## Run Example

```bash
uvicorn examples.fastapi_example:app --reload



## Installation

```bash
pip install -r requirements.txt
