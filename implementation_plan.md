# EVAP Backend Implementation Plan

## Status: PENDING APPROVAL

## Directory Structure to Create
```
evap/
└── backend/
    ├── requirements.txt                          [NEW]
    └── app/
        ├── __init__.py                           [NEW]
        ├── main.py                               [NEW]
        ├── core/
        │   ├── __init__.py                       [NEW]
        │   ├── config.py                         [NEW]
        │   ├── database.py                       [NEW]
        │   ├── security.py                       [NEW]
        │   ├── redis_client.py                   [NEW]
        │   ├── rabbitmq.py                       [NEW]
        │   └── dependencies.py                   [NEW]
        ├── models/
        │   └── __init__.py                       [NEW]  (SQLAlchemy ORM models)
        └── api/
            └── v1/
                ├── __init__.py                   [NEW]
                ├── router.py                     [NEW]
                ├── auth.py                       [NEW]
                ├── sites.py                      [NEW]
                ├── cameras.py                    [NEW]
                ├── employees.py                  [NEW]
                ├── visitors.py                   [NEW]
                ├── vehicles.py                   [NEW]
                ├── attendance.py                 [NEW]
                ├── alerts.py                     [NEW]
                ├── analytics.py                  [NEW]
                ├── maps.py                       [NEW]
                ├── reports.py                    [NEW]
                ├── notifications.py              [NEW]
                ├── erp.py                        [NEW]
                └── dashboard.py                  [NEW]
```

## File List (23 files + __init__.py stubs)

1. [NEW] evap/backend/requirements.txt
2. [NEW] evap/backend/app/core/config.py
3. [NEW] evap/backend/app/core/database.py
4. [NEW] evap/backend/app/core/security.py
5. [NEW] evap/backend/app/core/redis_client.py
6. [NEW] evap/backend/app/core/rabbitmq.py
7. [NEW] evap/backend/app/core/dependencies.py
8. [NEW] evap/backend/app/main.py
9. [NEW] evap/backend/app/models/__init__.py   (all ORM models inline)
10. [NEW] evap/backend/app/api/v1/router.py
11. [NEW] evap/backend/app/api/v1/auth.py
12. [NEW] evap/backend/app/api/v1/sites.py
13. [NEW] evap/backend/app/api/v1/cameras.py
14. [NEW] evap/backend/app/api/v1/employees.py
15. [NEW] evap/backend/app/api/v1/visitors.py
16. [NEW] evap/backend/app/api/v1/vehicles.py
17. [NEW] evap/backend/app/api/v1/attendance.py
18. [NEW] evap/backend/app/api/v1/alerts.py
19. [NEW] evap/backend/app/api/v1/analytics.py
20. [NEW] evap/backend/app/api/v1/maps.py
21. [NEW] evap/backend/app/api/v1/reports.py
22. [NEW] evap/backend/app/api/v1/notifications.py
23. [NEW] evap/backend/app/api/v1/erp.py
24. [NEW] evap/backend/app/api/v1/dashboard.py

## Key Architectural Decisions

- SQLAlchemy models defined in app/models/__init__.py (single file for cohesion)
- AsyncEngine with asyncpg driver; sync engine for Alembic migrations
- JWT RS256 tokens via python-jose
- Fernet symmetric encryption for RTSP URLs
- TOTP via pyotp for MFA
- aio-pika for async RabbitMQ
- redis.asyncio for async Redis
- Prometheus metrics via prometheus-client middleware
- All API routes protected by get_current_active_user dependency
- Pagination via skip/limit returning {"items": [...], "total": N}
