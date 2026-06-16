# EVAP Testing Guide

**Enterprise Video Analytics Platform — Comprehensive Testing Reference**
**Stack:** Python 3.13 · FastAPI · PostgreSQL 16 · Redis · RabbitMQ · YOLOv11 · ByteTrack · InsightFace · React 18 · Docker · Kubernetes

---

## Table of Contents

1. [Testing Strategy Overview](#1-testing-strategy-overview)
2. [Test Setup](#2-test-setup)
3. [Unit Tests](#3-unit-tests)
4. [Integration Tests](#4-integration-tests)
5. [Load Testing with Locust](#5-load-testing-with-locust)
6. [Camera Simulation](#6-camera-simulation)
7. [Failover Testing](#7-failover-testing)
8. [Security Testing](#8-security-testing)
9. [CI/CD Testing Pipeline](#9-cicd-testing-pipeline)
10. [Coverage](#10-coverage)

---

## 1. Testing Strategy Overview

### Testing Pyramid

EVAP follows a three-tier testing pyramid to balance confidence, speed, and maintenance cost.

```
          /\
         /  \
        / E2E \       10% — Selenium / Playwright browser tests, full system flows
       /--------\
      /          \
     / Integration \   20% — API, DB, Redis, RabbitMQ integration tests
    /--------------\
   /                \
  /    Unit Tests    \  70% — Service logic, utilities, validators, edge cases
 /____________________\
```

### Test Categories

| Category    | Tool(s)                          | Scope                                                   |
|-------------|----------------------------------|---------------------------------------------------------|
| Unit        | pytest, pytest-asyncio           | Individual service methods, validators, helpers         |
| Integration | pytest, httpx AsyncClient        | API endpoints, DB transactions, Redis/RabbitMQ messages |
| Load        | Locust                           | Throughput, latency under concurrent user load          |
| Stress      | Locust (spike profile)           | Breaking point, recovery behavior                       |
| Failover    | docker-compose stop/start        | Service outage recovery, graceful degradation           |
| Security    | Python jwt, custom scripts       | Auth bypass, injection, rate limiting, CORS             |

### Coverage Targets

| Layer    | Target | Measurement Tool        |
|----------|--------|-------------------------|
| Backend  | 80%    | pytest-cov (line + branch) |
| Frontend | 60%    | Vitest / Istanbul       |

---

## 2. Test Setup

### Install Dependencies

```bash
pip install pytest pytest-asyncio pytest-cov httpx factory-boy faker locust \
            aio-pika pytest-mock freezegun respx
```

Frontend:

```bash
npm install --save-dev vitest @testing-library/react @testing-library/user-event \
            @vitest/coverage-v8 msw
```

### Environment Variables for Testing

Create `tests/.env.test`:

```ini
ENV=test
DATABASE_URL=postgresql+asyncpg://evap:evap_pass@localhost:5433/evap_test
REDIS_URL=redis://localhost:6380/1
RABBITMQ_URL=amqp://evap:evap_rmq_pass@localhost:5673/
SECRET_KEY=test-secret-key-not-used-in-production-32chars
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
FACE_RECOGNITION_THRESHOLD=0.6
MAX_LOGIN_ATTEMPTS=10
LOG_LEVEL=WARNING
```

### pytest.ini / pyproject.toml

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
env_files = ["tests/.env.test"]
markers = [
    "unit: pure unit tests, no I/O",
    "integration: requires running DB/Redis/RabbitMQ",
    "load: locust load tests",
    "security: security-focused tests",
    "slow: tests that take >5s",
]
filterwarnings = [
    "ignore::DeprecationWarning",
    "ignore::UserWarning:sqlalchemy",
]
```

### conftest.py

```python
# tests/conftest.py
import asyncio
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.core.security import create_access_token
from tests.factories import UserFactory, CameraFactory, EmployeeFactory

# ── Database ──────────────────────────────────────────────────────────────────

TEST_DATABASE_URL = (
    "postgresql+asyncpg://evap:evap_pass@localhost:5433/evap_test"
)

engine_test = create_async_engine(TEST_DATABASE_URL, echo=False)
async_session_factory = async_sessionmaker(
    engine_test, expire_on_commit=False, class_=AsyncSession
)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_database():
    """Create all tables once per test session. Fastest approach for schema-stable tests."""
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    """Each test gets a transaction that is rolled back on teardown."""
    async with engine_test.begin() as conn:
        async with async_session_factory(bind=conn) as session:
            yield session
            await session.rollback()


# ── App client ────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """ASGI test client with DB dependency overridden."""

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


# ── Auth helpers ──────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def test_user(db: AsyncSession):
    user = await UserFactory.create(db, role="operator")
    return user


@pytest_asyncio.fixture
async def admin_user(db: AsyncSession):
    user = await UserFactory.create(db, role="admin")
    return user


@pytest.fixture
def auth_headers(test_user) -> dict:
    token = create_access_token({"sub": str(test_user.id), "role": test_user.role})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(admin_user) -> dict:
    token = create_access_token({"sub": str(admin_user.id), "role": admin_user.role})
    return {"Authorization": f"Bearer {token}"}


# ── Redis mock ────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_redis():
    """In-memory dict-backed Redis mock for unit tests."""
    store = {}

    redis = AsyncMock()
    redis.get = AsyncMock(side_effect=lambda k: store.get(k))
    redis.set = AsyncMock(side_effect=lambda k, v, ex=None: store.update({k: v}))
    redis.delete = AsyncMock(side_effect=lambda k: store.pop(k, None))
    redis.exists = AsyncMock(side_effect=lambda k: k in store)
    redis.expire = AsyncMock(return_value=True)
    redis.incr = AsyncMock(
        side_effect=lambda k: store.update({k: store.get(k, 0) + 1}) or store[k]
    )
    return redis


# ── RabbitMQ mock ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_rabbitmq():
    """Captures published messages without a real broker."""
    published = []

    channel = AsyncMock()
    channel.default_exchange = AsyncMock()
    channel.default_exchange.publish = AsyncMock(
        side_effect=lambda msg, routing_key: published.append(
            {"routing_key": routing_key, "body": msg.body}
        )
    )
    channel.published_messages = published
    return channel


# ── Misc fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def sample_face_image_path():
    return "tests/fixtures/faces/employee_001_front.jpg"


@pytest.fixture
def sample_plate_image_path():
    return "tests/fixtures/plates/plate_ABC1234.jpg"
```

### factories.py

```python
# tests/factories.py
import uuid
from datetime import datetime, timezone

from faker import Faker
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, Employee, Camera, AttendanceLog, AlertEvent
from app.core.security import get_password_hash

fake = Faker()


class UserFactory:
    @staticmethod
    async def create(db: AsyncSession, role: str = "operator", **kwargs) -> User:
        user = User(
            id=uuid.uuid4(),
            email=kwargs.get("email", fake.email()),
            hashed_password=get_password_hash(kwargs.get("password", "Test@1234")),
            full_name=kwargs.get("full_name", fake.name()),
            role=role,
            is_active=True,
        )
        db.add(user)
        await db.flush()
        return user


class EmployeeFactory:
    @staticmethod
    async def create(db: AsyncSession, **kwargs) -> Employee:
        emp = Employee(
            id=uuid.uuid4(),
            employee_code=kwargs.get("employee_code", f"EMP{fake.numerify('###')}"),
            full_name=kwargs.get("full_name", fake.name()),
            department=kwargs.get("department", "Engineering"),
            designation=kwargs.get("designation", "Engineer"),
            shift_id=kwargs.get("shift_id", None),
            is_active=kwargs.get("is_active", True),
            face_enrolled=kwargs.get("face_enrolled", False),
        )
        db.add(emp)
        await db.flush()
        return emp


class CameraFactory:
    @staticmethod
    async def create(db: AsyncSession, **kwargs) -> Camera:
        cam = Camera(
            id=uuid.uuid4(),
            name=kwargs.get("name", f"Camera {fake.numerify('##')}"),
            rtsp_url=kwargs.get("rtsp_url", f"rtsp://192.168.1.{fake.numerify('###')}/stream"),
            location=kwargs.get("location", fake.street_address()),
            ai_enabled=kwargs.get("ai_enabled", True),
            is_active=kwargs.get("is_active", True),
        )
        db.add(cam)
        await db.flush()
        return cam
```

---

## 3. Unit Tests

### Running Unit Tests

```bash
pytest tests/unit/ -v --cov=app --cov-report=html -x -m "not integration"
```

### a. Auth Service Tests

```python
# tests/unit/test_auth_service.py
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time
from jose import jwt

from app.core.config import settings
from app.services.auth import AuthService
from app.exceptions import InvalidCredentialsError, TokenExpiredError, MFARequiredError


@pytest.fixture
def auth_service(mock_redis):
    svc = AuthService()
    svc.redis = mock_redis
    return svc


@pytest.mark.asyncio
async def test_login_success(auth_service, db):
    """Valid credentials return access + refresh tokens."""
    from tests.factories import UserFactory

    user = await UserFactory.create(db, password="Secure@9999")
    result = await auth_service.login(
        db=db, email=user.email, password="Secure@9999"
    )

    assert result["access_token"] is not None
    assert result["token_type"] == "bearer"
    payload = jwt.decode(
        result["access_token"], settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
    )
    assert payload["sub"] == str(user.id)


@pytest.mark.asyncio
async def test_login_wrong_password(auth_service, db):
    """Wrong password raises InvalidCredentialsError, not a 500."""
    from tests.factories import UserFactory

    user = await UserFactory.create(db, password="Correct@1234")

    with pytest.raises(InvalidCredentialsError):
        await auth_service.login(db=db, email=user.email, password="WrongPass")


@pytest.mark.asyncio
async def test_login_increments_failure_counter(auth_service, db, mock_redis):
    """Failed login increments Redis counter; lockout after threshold."""
    from tests.factories import UserFactory

    user = await UserFactory.create(db, password="Right@1234")

    for _ in range(settings.MAX_LOGIN_ATTEMPTS):
        with pytest.raises(InvalidCredentialsError):
            await auth_service.login(db=db, email=user.email, password="Wrong")

    assert mock_redis.incr.call_count == settings.MAX_LOGIN_ATTEMPTS


@pytest.mark.asyncio
async def test_token_refresh_returns_new_access_token(auth_service, db):
    """A valid refresh token produces a new access token."""
    from tests.factories import UserFactory

    user = await UserFactory.create(db)
    tokens = await auth_service.login(db=db, email=user.email, password="Test@1234")

    new_tokens = await auth_service.refresh_token(
        db=db, refresh_token=tokens["refresh_token"]
    )

    assert new_tokens["access_token"] != tokens["access_token"]
    payload = jwt.decode(
        new_tokens["access_token"], settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
    )
    assert payload["sub"] == str(user.id)


@pytest.mark.asyncio
async def test_token_refresh_expired_raises(auth_service, db):
    """Expired refresh token raises TokenExpiredError."""
    from tests.factories import UserFactory
    from app.core.security import create_refresh_token

    user = await UserFactory.create(db)
    with freeze_time("2026-01-01"):
        expired_token = create_refresh_token(
            {"sub": str(user.id)}, expires_delta=timedelta(seconds=1)
        )

    with pytest.raises(TokenExpiredError):
        await auth_service.refresh_token(db=db, refresh_token=expired_token)


@pytest.mark.asyncio
async def test_mfa_verify_valid_totp(auth_service, db):
    """Valid TOTP code passes MFA verification."""
    import pyotp
    from tests.factories import UserFactory

    secret = pyotp.random_base32()
    user = await UserFactory.create(db, mfa_secret=secret, mfa_enabled=True)
    totp = pyotp.TOTP(secret)

    result = await auth_service.verify_mfa(
        db=db, user_id=str(user.id), code=totp.now()
    )
    assert result is True


@pytest.mark.asyncio
async def test_mfa_verify_wrong_code(auth_service, db):
    """Invalid TOTP code returns False without raising."""
    import pyotp
    from tests.factories import UserFactory

    user = await UserFactory.create(
        db, mfa_secret=pyotp.random_base32(), mfa_enabled=True
    )
    result = await auth_service.verify_mfa(
        db=db, user_id=str(user.id), code="000000"
    )
    assert result is False
```

### b. Employee Service Tests

```python
# tests/unit/test_employee_service.py
import io
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import UploadFile

from app.services.employee import EmployeeService
from app.exceptions import FaceEnrollmentError, DuplicateEmployeeError


@pytest.fixture
def employee_service(mock_redis):
    svc = EmployeeService()
    svc.redis = mock_redis
    return svc


@pytest.mark.asyncio
async def test_face_enrollment_success(employee_service, db):
    """High-quality face image enrolls successfully and sets face_enrolled=True."""
    from tests.factories import EmployeeFactory

    emp = await EmployeeFactory.create(db, face_enrolled=False)

    # Simulate InsightFace returning a valid 512-d embedding
    mock_embedding = [0.01] * 512
    with patch(
        "app.services.employee.FaceAnalyzer.extract_embedding",
        new_callable=AsyncMock,
        return_value=mock_embedding,
    ):
        image_bytes = open("tests/fixtures/faces/employee_001_front.jpg", "rb").read()
        upload = UploadFile(filename="face.jpg", file=io.BytesIO(image_bytes))

        result = await employee_service.enroll_face(
            db=db, employee_id=emp.id, image=upload
        )

    assert result["enrolled"] is True
    await db.refresh(emp)
    assert emp.face_enrolled is True
    assert emp.face_embedding is not None


@pytest.mark.asyncio
async def test_face_enrollment_no_face_detected(employee_service, db):
    """Image with no detectable face raises FaceEnrollmentError."""
    from tests.factories import EmployeeFactory

    emp = await EmployeeFactory.create(db, face_enrolled=False)

    with patch(
        "app.services.employee.FaceAnalyzer.extract_embedding",
        new_callable=AsyncMock,
        return_value=None,  # no face found
    ):
        image_bytes = open("tests/fixtures/no_face.jpg", "rb").read()
        upload = UploadFile(filename="empty.jpg", file=io.BytesIO(image_bytes))

        with pytest.raises(FaceEnrollmentError, match="No face detected"):
            await employee_service.enroll_face(
                db=db, employee_id=emp.id, image=upload
            )


@pytest.mark.asyncio
async def test_bulk_import_csv_creates_employees(employee_service, db):
    """Valid CSV creates employee records; invalid rows are reported."""
    csv_content = (
        "employee_code,full_name,department,designation\n"
        "EMP100,Alice Smith,Engineering,SDE\n"
        "EMP101,Bob Jones,HR,Manager\n"
        ",Missing Code,Finance,Analyst\n"  # invalid: no code
    )
    upload = UploadFile(
        filename="employees.csv", file=io.BytesIO(csv_content.encode())
    )

    result = await employee_service.bulk_import_csv(db=db, file=upload)

    assert result["created"] == 2
    assert result["failed"] == 1
    assert result["errors"][0]["row"] == 3


@pytest.mark.asyncio
async def test_bulk_import_duplicate_code_skipped(employee_service, db):
    """CSV row with existing employee_code is reported as duplicate, not created."""
    from tests.factories import EmployeeFactory

    existing = await EmployeeFactory.create(db, employee_code="EMP200")
    csv_content = (
        "employee_code,full_name,department,designation\n"
        "EMP200,Duplicate Name,IT,Analyst\n"
    )
    upload = UploadFile(
        filename="dup.csv", file=io.BytesIO(csv_content.encode())
    )

    result = await employee_service.bulk_import_csv(db=db, file=upload)

    assert result["created"] == 0
    assert result["failed"] == 1
    assert "duplicate" in result["errors"][0]["reason"].lower()


@pytest.mark.asyncio
async def test_employee_deactivation_wipes_face_embedding(employee_service, db):
    """Deactivating an employee sets is_active=False and clears face embedding (GDPR)."""
    from tests.factories import EmployeeFactory

    emp = await EmployeeFactory.create(db, face_enrolled=True)
    emp.face_embedding = [0.01] * 512
    await db.flush()

    await employee_service.deactivate(db=db, employee_id=emp.id)

    await db.refresh(emp)
    assert emp.is_active is False
    assert emp.face_enrolled is False
    assert emp.face_embedding is None
```

### c. Alert Service Tests

```python
# tests/unit/test_alert_service.py
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
import uuid

import pytest
from freezegun import freeze_time

from app.services.alert import AlertService
from app.schemas.alert import OccupancyRule, AlertSuppressionWindow


@pytest.fixture
def alert_service(mock_redis, mock_rabbitmq):
    svc = AlertService()
    svc.redis = mock_redis
    svc.channel = mock_rabbitmq
    return svc


@pytest.mark.asyncio
async def test_occupancy_rule_triggers_alert(alert_service, db):
    """When occupancy exceeds the rule threshold, an alert event is published."""
    from tests.factories import CameraFactory

    cam = await CameraFactory.create(db)
    rule = OccupancyRule(camera_id=cam.id, max_persons=5, zone="lobby")

    # Simulate 6 persons detected — exceeds threshold of 5
    await alert_service.evaluate_occupancy(
        db=db, camera_id=cam.id, current_count=6, rule=rule
    )

    # Verify message was published to RabbitMQ
    assert len(alert_service.channel.published_messages) == 1
    msg = alert_service.channel.published_messages[0]
    assert msg["routing_key"] == "evap.alerts.occupancy"


@pytest.mark.asyncio
async def test_occupancy_below_threshold_no_alert(alert_service, db):
    """When occupancy is at or below threshold, no alert is fired."""
    from tests.factories import CameraFactory

    cam = await CameraFactory.create(db)
    rule = OccupancyRule(camera_id=cam.id, max_persons=10, zone="warehouse")

    await alert_service.evaluate_occupancy(
        db=db, camera_id=cam.id, current_count=10, rule=rule
    )

    assert len(alert_service.channel.published_messages) == 0


@pytest.mark.asyncio
async def test_blacklist_vehicle_fires_alert(alert_service, db):
    """A detected plate matching the blacklist produces a CRITICAL alert."""
    plate = "MH01AB1234"
    # Seed blacklist in mock Redis
    alert_service.redis.get = AsyncMock(return_value=b"blacklisted")

    result = await alert_service.check_vehicle_blacklist(plate=plate)

    assert result["is_blacklisted"] is True
    assert result["severity"] == "CRITICAL"


@pytest.mark.asyncio
async def test_suppression_window_blocks_duplicate_alert(alert_service, db):
    """Within the suppression window (5 min), the same rule does not fire twice."""
    from tests.factories import CameraFactory

    cam = await CameraFactory.create(db)
    rule = OccupancyRule(camera_id=cam.id, max_persons=3, zone="entrance")

    # First alert
    await alert_service.evaluate_occupancy(db=db, camera_id=cam.id, current_count=5, rule=rule)
    assert len(alert_service.channel.published_messages) == 1

    # Simulate suppression window cached in Redis
    suppression_key = f"alert_suppressed:{cam.id}:occupancy"
    alert_service.redis.exists = AsyncMock(return_value=True)

    # Second alert within window — should be suppressed
    await alert_service.evaluate_occupancy(db=db, camera_id=cam.id, current_count=7, rule=rule)
    assert len(alert_service.channel.published_messages) == 1  # still 1
```

### d. Attendance Service Tests

```python
# tests/unit/test_attendance_service.py
from datetime import datetime, time, timezone
from unittest.mock import AsyncMock
import uuid

import pytest
from freezegun import freeze_time

from app.services.attendance import AttendanceService


@pytest.fixture
def attendance_service(mock_redis):
    svc = AttendanceService()
    svc.redis = mock_redis
    return svc


@pytest.mark.asyncio
async def test_attendance_recorded_on_recognition(attendance_service, db):
    """A face recognition event for a known employee creates an attendance_log row."""
    from tests.factories import EmployeeFactory, CameraFactory
    from app.db.models import AttendanceLog

    emp = await EmployeeFactory.create(db, face_enrolled=True)
    cam = await CameraFactory.create(db)

    await attendance_service.record_recognition(
        db=db,
        employee_id=emp.id,
        camera_id=cam.id,
        confidence=0.92,
        event_time=datetime(2026, 6, 15, 8, 55, tzinfo=timezone.utc),
    )

    from sqlalchemy import select
    rows = (await db.execute(
        select(AttendanceLog).where(AttendanceLog.employee_id == emp.id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].confidence == pytest.approx(0.92)


@pytest.mark.asyncio
async def test_late_arrival_flagged(attendance_service, db):
    """Employee arriving after shift start time is flagged as LATE."""
    from tests.factories import EmployeeFactory, CameraFactory
    from app.db.models import Shift

    shift = Shift(
        id=uuid.uuid4(),
        name="Morning",
        start_time=time(9, 0),
        end_time=time(17, 0),
        grace_minutes=10,
    )
    db.add(shift)
    await db.flush()

    emp = await EmployeeFactory.create(db, shift_id=shift.id)
    cam = await CameraFactory.create(db)

    result = await attendance_service.record_recognition(
        db=db,
        employee_id=emp.id,
        camera_id=cam.id,
        confidence=0.88,
        event_time=datetime(2026, 6, 15, 9, 20, tzinfo=timezone.utc),  # 20 min late
    )

    assert result["status"] == "LATE"


@pytest.mark.asyncio
async def test_overnight_shift_handled_correctly(attendance_service, db):
    """Night shift spanning midnight (22:00–06:00) is calculated correctly."""
    from tests.factories import EmployeeFactory, CameraFactory
    from app.db.models import Shift

    shift = Shift(
        id=uuid.uuid4(),
        name="Night",
        start_time=time(22, 0),
        end_time=time(6, 0),
        grace_minutes=15,
    )
    db.add(shift)
    await db.flush()

    emp = await EmployeeFactory.create(db, shift_id=shift.id)
    cam = await CameraFactory.create(db)

    result = await attendance_service.record_recognition(
        db=db,
        employee_id=emp.id,
        camera_id=cam.id,
        confidence=0.95,
        event_time=datetime(2026, 6, 15, 22, 5, tzinfo=timezone.utc),  # on time
    )
    assert result["status"] == "PRESENT"


@pytest.mark.asyncio
async def test_duplicate_recognition_within_5_minutes_ignored(attendance_service, db):
    """Second recognition event within 5 minutes for same employee is deduplicated."""
    from tests.factories import EmployeeFactory, CameraFactory

    emp = await EmployeeFactory.create(db, face_enrolled=True)
    cam = await CameraFactory.create(db)
    event_time = datetime(2026, 6, 15, 9, 0, tzinfo=timezone.utc)

    # First recognition
    await attendance_service.record_recognition(
        db=db, employee_id=emp.id, camera_id=cam.id,
        confidence=0.91, event_time=event_time,
    )
    # Second recognition 3 minutes later
    result = await attendance_service.record_recognition(
        db=db, employee_id=emp.id, camera_id=cam.id,
        confidence=0.89,
        event_time=datetime(2026, 6, 15, 9, 3, tzinfo=timezone.utc),
    )
    assert result["deduplicated"] is True
```

### e. ANPR Service Tests

```python
# tests/unit/test_anpr_service.py
import pytest
from app.services.anpr import ANPRService


@pytest.fixture
def anpr_service(mock_redis):
    svc = ANPRService()
    svc.redis = mock_redis
    return svc


@pytest.mark.parametrize("raw,expected", [
    ("mh 01 ab 1234", "MH01AB1234"),
    ("MH-01-AB-1234", "MH01AB1234"),
    (" KA 05 MN 9988 ", "KA05MN9988"),
    ("DL 3C AB 0001", "DL3CAB0001"),
])
def test_plate_normalization(anpr_service, raw, expected):
    """Plates are uppercased and stripped of spaces/hyphens."""
    result = anpr_service.normalize_plate(raw)
    assert result == expected


@pytest.mark.parametrize("ocr_text,db_plate,should_match", [
    ("MH01AB1234", "MH01AB1234", True),   # exact
    ("MH01A81234", "MH01AB1234", True),   # OCR confusion: B→8
    ("MH01AB1234", "MH01AB1235", False),  # differs by 1 digit but not OCR noise
    ("KA05MN998B", "KA05MN9988", True),   # OCR confusion: 8→B
    ("DL3CAB0001", "XXYYZZZ999", False),  # completely different
])
def test_fuzzy_match(anpr_service, ocr_text, db_plate, should_match):
    """Fuzzy matching handles common OCR confusion characters."""
    result = anpr_service.fuzzy_match(ocr_text, db_plate)
    assert result == should_match


@pytest.mark.asyncio
async def test_blacklist_check_returns_true_for_known_plate(anpr_service, mock_redis):
    """A plate in the blacklist Redis set returns is_blacklisted=True."""
    from unittest.mock import AsyncMock

    anpr_service.redis.get = AsyncMock(return_value=b"STOLEN|Reported 2026-05-01")

    result = await anpr_service.check_blacklist(plate="MH01AB1234")

    assert result["is_blacklisted"] is True
    assert "STOLEN" in result["reason"]


@pytest.mark.asyncio
async def test_blacklist_check_returns_false_for_clean_plate(anpr_service, mock_redis):
    from unittest.mock import AsyncMock

    anpr_service.redis.get = AsyncMock(return_value=None)

    result = await anpr_service.check_blacklist(plate="KA05MN9988")
    assert result["is_blacklisted"] is False
```

---

## 4. Integration Tests

### Running Integration Tests

```bash
# Requires: postgres:5433, redis:6380, rabbitmq:5673 running
pytest tests/integration/ -v -m integration --timeout=30
```

### a. API Endpoint Tests

```python
# tests/integration/test_employee_api.py
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_employee_and_enroll_face(
    client: AsyncClient, auth_headers: dict, db: AsyncSession
):
    """Full employee creation and face enrollment flow via API."""
    # Step 1: create employee
    resp = await client.post(
        "/api/v1/employees",
        json={
            "employee_code": "EMP001",
            "full_name": "John Doe",
            "department": "Engineering",
            "designation": "Senior SDE",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    employee_id = resp.json()["id"]
    assert resp.json()["face_enrolled"] is False

    # Step 2: enroll face
    with open("tests/fixtures/faces/employee_001_front.jpg", "rb") as f:
        resp = await client.post(
            f"/api/v1/employees/{employee_id}/enroll-face",
            files={"image": ("face.jpg", f, "image/jpeg")},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    assert resp.json()["enrolled"] is True

    # Step 3: verify enrolled status via GET
    resp = await client.get(
        f"/api/v1/employees/{employee_id}", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["face_enrolled"] is True


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_employees_pagination(
    client: AsyncClient, auth_headers: dict, db: AsyncSession
):
    """GET /api/v1/employees returns paginated results."""
    from tests.factories import EmployeeFactory

    # Create 15 employees
    for i in range(15):
        await EmployeeFactory.create(db, employee_code=f"EMP{i:03d}")

    resp = await client.get(
        "/api/v1/employees?page=1&size=10", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 15
    assert len(data["items"]) == 10
    assert data["page"] == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_employee_duplicate_code_returns_409(
    client: AsyncClient, auth_headers: dict, db: AsyncSession
):
    """Duplicate employee_code returns 409 Conflict."""
    from tests.factories import EmployeeFactory

    await EmployeeFactory.create(db, employee_code="EMP999")

    resp = await client.post(
        "/api/v1/employees",
        json={"employee_code": "EMP999", "full_name": "Duplicate", "department": "IT"},
        headers=auth_headers,
    )
    assert resp.status_code == 409
```

### b. Database Integration Tests

```python
# tests/integration/test_db_integrity.py
import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models import AttendanceLog, Employee, Camera


@pytest.mark.asyncio
@pytest.mark.integration
async def test_attendance_log_row_created_on_recognition(db: AsyncSession):
    """attendance_log row is persisted with correct FK references."""
    from tests.factories import EmployeeFactory, CameraFactory
    from app.services.attendance import AttendanceService

    emp = await EmployeeFactory.create(db, face_enrolled=True)
    cam = await CameraFactory.create(db)

    svc = AttendanceService()
    await svc.record_recognition(
        db=db, employee_id=emp.id, camera_id=cam.id,
        confidence=0.94,
        event_time=datetime(2026, 6, 15, 9, 0, tzinfo=timezone.utc),
    )

    rows = (await db.execute(
        select(AttendanceLog).where(AttendanceLog.employee_id == emp.id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].camera_id == cam.id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_attendance_log_fk_constraint_rejects_unknown_employee(db: AsyncSession):
    """attendance_log row with non-existent employee_id raises IntegrityError."""
    cam_id = uuid.uuid4()
    log = AttendanceLog(
        id=uuid.uuid4(),
        employee_id=uuid.uuid4(),   # does not exist
        camera_id=cam_id,
        confidence=0.9,
        event_time=datetime.now(timezone.utc),
        status="PRESENT",
    )
    db.add(log)
    with pytest.raises(IntegrityError):
        await db.flush()
```

### c. Redis Cache Integration

```python
# tests/integration/test_redis_cache.py
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_summary_cache_hit(client: AsyncClient, auth_headers: dict):
    """Second GET /dashboard/summary is served from Redis cache (X-Cache: HIT)."""
    # First request — cache miss, DB query
    r1 = await client.get("/api/v1/dashboard/summary", headers=auth_headers)
    assert r1.status_code == 200
    assert r1.headers.get("X-Cache") == "MISS"

    # Second request — cache hit
    r2 = await client.get("/api/v1/dashboard/summary", headers=auth_headers)
    assert r2.status_code == 200
    assert r2.headers.get("X-Cache") == "HIT"
    assert r1.json() == r2.json()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cache_invalidated_on_employee_update(
    client: AsyncClient, admin_headers: dict, db
):
    """Updating an employee invalidates the related cache key."""
    from tests.factories import EmployeeFactory

    emp = await EmployeeFactory.create(db)

    # Warm cache
    await client.get(f"/api/v1/employees/{emp.id}", headers=admin_headers)

    # Update employee
    await client.patch(
        f"/api/v1/employees/{emp.id}",
        json={"designation": "Principal SDE"},
        headers=admin_headers,
    )

    # Next GET should be a cache miss (fresh data)
    r = await client.get(f"/api/v1/employees/{emp.id}", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["designation"] == "Principal SDE"
```

### d. RabbitMQ Integration Tests

```python
# tests/integration/test_rabbitmq_integration.py
import asyncio
import json
import pytest
import aio_pika

RABBITMQ_URL = "amqp://evap:evap_rmq_pass@localhost:5673/"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_detection_event_published_and_consumed():
    """Detection event published to exchange is received by consumer queue."""
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()

        queue = await channel.declare_queue("test_detection_events", auto_delete=True)
        await queue.bind("evap.events", routing_key="detection.person")

        # Publish a synthetic detection event
        event = {
            "camera_id": "cam-001",
            "event_type": "person_detected",
            "confidence": 0.91,
            "timestamp": "2026-06-15T09:00:00Z",
        }
        await channel.default_exchange.publish(
            aio_pika.Message(body=json.dumps(event).encode()),
            routing_key="detection.person",
        )

        # Consume and assert
        async with queue.iterator() as it:
            async for message in it:
                async with message.process():
                    received = json.loads(message.body)
                    assert received["event_type"] == "person_detected"
                    assert received["confidence"] == pytest.approx(0.91)
                    break  # one message is enough
```

---

## 5. Load Testing with Locust

### locustfile.py

```python
# tests/load/locustfile.py
import json
import random
from locust import HttpUser, task, between, events


class EVAPUser(HttpUser):
    """Simulates an EVAP dashboard operator session."""

    wait_time = between(0.1, 0.5)
    token: str = ""
    camera_ids: list = []
    employee_ids: list = []

    def on_start(self):
        """Authenticate and pre-fetch reference IDs."""
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"email": "loadtest@evap.local", "password": "LoadTest@9999"},
        )
        if resp.status_code == 200:
            self.token = resp.json()["access_token"]
        else:
            raise Exception(f"Login failed: {resp.status_code} {resp.text}")

        # Fetch a few camera/employee IDs for subsequent tasks
        headers = self._headers()
        cam_resp = self.client.get("/api/v1/cameras?size=20", headers=headers)
        if cam_resp.status_code == 200:
            self.camera_ids = [c["id"] for c in cam_resp.json().get("items", [])]

        emp_resp = self.client.get("/api/v1/employees?size=20", headers=headers)
        if emp_resp.status_code == 200:
            self.employee_ids = [e["id"] for e in emp_resp.json().get("items", [])]

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    @task(5)
    def get_dashboard_summary(self):
        """Most frequent operation: dashboard overview."""
        with self.client.get(
            "/api/v1/dashboard/summary",
            headers=self._headers(),
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Unexpected status {resp.status_code}")

    @task(3)
    def get_live_camera_stats(self):
        """Live occupancy data per camera."""
        if not self.camera_ids:
            return
        cam_id = random.choice(self.camera_ids)
        with self.client.get(
            f"/api/v1/cameras/{cam_id}/stats",
            headers=self._headers(),
            catch_response=True,
            name="/api/v1/cameras/[id]/stats",
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f"Unexpected status {resp.status_code}")

    @task(2)
    def get_attendance_list(self):
        """Paginated attendance log — heavy DB read."""
        with self.client.get(
            "/api/v1/attendance?page=1&size=25&date=2026-06-15",
            headers=self._headers(),
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Status {resp.status_code}")

    @task(1)
    def trigger_alert_search(self):
        """Search recent alert events — less frequent, more expensive."""
        with self.client.get(
            "/api/v1/alert-events?status=OPEN&page=1&size=10",
            headers=self._headers(),
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Status {resp.status_code}")

    @task(1)
    def acknowledge_alert(self):
        """Simulate an operator acknowledging an alert."""
        # We use a synthetic ID here; in a real load test seed the DB first
        with self.client.post(
            "/api/v1/alert-events/00000000-0000-0000-0000-000000000001/acknowledge",
            json={"notes": "Investigated by load test user"},
            headers=self._headers(),
            catch_response=True,
            name="/api/v1/alert-events/[id]/acknowledge",
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f"Status {resp.status_code}")


class ANPRUser(HttpUser):
    """Simulates heavier ANPR query load from a gate operator."""

    wait_time = between(0.5, 2.0)
    token: str = ""

    def on_start(self):
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"email": "gate@evap.local", "password": "GateOp@9999"},
        )
        self.token = resp.json()["access_token"]

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    @task(3)
    def search_vehicle_by_plate(self):
        plate = random.choice(["MH01AB1234", "KA05MN9988", "DL3CAB0001"])
        self.client.get(
            f"/api/v1/anpr/search?plate={plate}",
            headers=self._headers(),
            name="/api/v1/anpr/search",
        )

    @task(1)
    def get_anpr_events(self):
        self.client.get(
            "/api/v1/anpr/events?page=1&size=20",
            headers=self._headers(),
        )
```

### Running Locust

```bash
# Headless mode — 500 users, ramp at 50/s, run for 5 minutes
locust -f tests/load/locustfile.py \
  --headless \
  -u 500 \
  -r 50 \
  -t 5m \
  --host https://evap-staging.yourdomain.com \
  --html tests/load/reports/report_$(date +%Y%m%d_%H%M).html \
  --csv tests/load/reports/results_$(date +%Y%m%d_%H%M)

# Interactive web UI (dev/exploration)
locust -f tests/load/locustfile.py --host https://evap-staging.yourdomain.com
# Open http://localhost:8089
```

### Target Performance Metrics

| Endpoint | Target RPS | p50 | p95 | p99 | Error Rate |
|---|---|---|---|---|---|
| GET /api/v1/dashboard/summary | 500 | <20ms | <50ms | <100ms | <0.1% |
| GET /api/v1/cameras/[id]/stats | 300 | <15ms | <40ms | <80ms | <0.1% |
| GET /api/v1/attendance | 200 | <30ms | <80ms | <150ms | <0.1% |
| GET /api/v1/employees | 150 | <25ms | <60ms | <120ms | <0.1% |
| POST /api/v1/alert-events/[id]/acknowledge | 50 | <50ms | <100ms | <200ms | <0.5% |
| GET /api/v1/anpr/search | 100 | <40ms | <90ms | <180ms | <0.1% |
| WebSocket /ws/live-feed | 1000 concurrent | — | — | — | 0% drops |

---

## 6. Camera Simulation

### Local RTSP Server with mediamtx

```bash
# Install mediamtx
wget https://github.com/bluenviron/mediamtx/releases/latest/download/mediamtx_linux_amd64.tar.gz
tar -xzf mediamtx_linux_amd64.tar.gz

# Start mediamtx (default port 8554)
./mediamtx
```

### Stream a Test Video via FFmpeg

```bash
# Loop a sample video as an RTSP stream
ffmpeg -re \
  -stream_loop -1 \
  -i tests/fixtures/videos/sample_parking_lot.mp4 \
  -c:v libx264 -preset ultrafast -tune zerolatency \
  -c:a aac \
  -f rtsp \
  rtsp://localhost:8554/test_camera_001

# Verify the stream is accessible
ffprobe -v quiet -print_format json -show_streams \
  rtsp://localhost:8554/test_camera_001
```

### Multiple Camera Streams

```bash
# Launch 4 test streams in background
for i in 001 002 003 004; do
  ffmpeg -re -stream_loop -1 \
    -i tests/fixtures/videos/sample_parking_lot.mp4 \
    -c copy -f rtsp \
    rtsp://localhost:8554/test_camera_$i \
    > /tmp/ffmpeg_$i.log 2>&1 &
done

echo "Test streams running on rtsp://localhost:8554/test_camera_{001..004}"
```

### Synthetic Detection Event Injection (Bypass Camera)

Use this script to inject detection events directly into RabbitMQ without a real camera — useful for testing the alert and attendance pipelines in isolation.

```python
# tests/scripts/inject_detection_events.py
"""
Inject synthetic detection events into EVAP's RabbitMQ exchange.
Usage: python inject_detection_events.py --count 100 --rate 10
"""
import argparse
import asyncio
import json
import random
import uuid
from datetime import datetime, timezone

import aio_pika


RABBITMQ_URL = "amqp://evap:evap_rmq_pass@localhost:5673/"
CAMERA_IDS = [
    "3f2a1b4c-0000-0000-0000-000000000001",
    "3f2a1b4c-0000-0000-0000-000000000002",
]
EMPLOYEE_IDS = [
    "aabb1122-0000-0000-0000-000000000001",
    "aabb1122-0000-0000-0000-000000000002",
]


async def inject(count: int, rate: float):
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()
        exchange = await channel.declare_exchange(
            "evap.events", aio_pika.ExchangeType.TOPIC, durable=True
        )

        for i in range(count):
            event_type = random.choice(["face_recognized", "person_detected", "vehicle_detected"])
            payload = {
                "event_id": str(uuid.uuid4()),
                "event_type": event_type,
                "camera_id": random.choice(CAMERA_IDS),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "confidence": round(random.uniform(0.75, 0.99), 3),
            }
            if event_type == "face_recognized":
                payload["employee_id"] = random.choice(EMPLOYEE_IDS)
            elif event_type == "vehicle_detected":
                payload["plate_text"] = random.choice(["MH01AB1234", "KA05MN9988"])

            await exchange.publish(
                aio_pika.Message(
                    body=json.dumps(payload).encode(),
                    content_type="application/json",
                ),
                routing_key=f"detection.{event_type}",
            )
            print(f"[{i+1}/{count}] Injected: {event_type}")
            await asyncio.sleep(1.0 / rate)

        print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--rate", type=float, default=5.0, help="Events per second")
    args = parser.parse_args()
    asyncio.run(inject(args.count, args.rate))
```

### Test Fixture Image Requirements

| Criteria | Requirement |
|---|---|
| Resolution | Minimum 640×480; recommended 1280×720 |
| Face size | At least 80×80 pixels in the frame |
| Angle | Frontal (0–15°); side angles beyond 45° will fail enrollment |
| Lighting | Even, avoid strong backlighting or shadows across face |
| Expression | Neutral mouth, eyes open |
| Accessories | No sunglasses; hats acceptable if face fully visible |
| Format | JPEG or PNG, no compression artifacts |
| Multiple images | At least 3 images per person (different sessions) for best accuracy |

---

## 7. Failover Testing

### a. PostgreSQL Failure

```bash
# Induce failure
docker-compose stop postgres

# Expected: API returns 503 within ~5s
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/health
# → 503

# Expected: celery workers log connection retries, not crash
docker logs evap-celery-detection --tail 20
# → "sqlalchemy.exc.OperationalError: ... retrying in 5s"

# Restore and verify self-healing (no manual intervention needed)
docker-compose start postgres
sleep 10
curl -s http://localhost:8000/api/v1/health | jq .status
# → "healthy"
```

### b. Redis Failure

```bash
# Induce failure
docker-compose stop redis

# Expected: cache-miss fallback to DB — requests slower but no 500 errors
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/dashboard/summary
# → 200 (not 500)

# Expected: WebSocket presence tracking degrades (no online count), does not disconnect
# Check backend logs for graceful handling
docker logs evap-backend --tail 20 | grep -i redis
# → "Redis unavailable, falling back to DB for ..."

# Restore
docker-compose start redis
```

### c. RabbitMQ Failure

```bash
# Induce failure
docker-compose stop rabbitmq

# Expected: detection pipeline queues events in-memory (brief delay in alerts)
# New alerts will be delayed but not lost (depends on publisher confirms config)

# Verify no crash
docker-compose ps
# evap-celery-detection should be Up (reconnecting)

# Restore and verify backlog processing
docker-compose start rabbitmq
sleep 15

# Check that queued events are now being processed
curl -s -u evap:evap_rmq_pass http://localhost:15672/api/queues | \
  jq '.[] | select(.name == "evap.events.detection") | .messages'
# → should decrease toward 0
```

### d. Camera RTSP Disconnect

```bash
# Kill test stream (simulate camera power loss)
pkill -f "rtsp://localhost:8554/test_camera_001"

# Wait 30 seconds, then verify camera shows offline
sleep 30
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/cameras/CAM_ID_HERE | jq .status
# → "offline"

# Restore stream
ffmpeg -re -stream_loop -1 -i tests/fixtures/videos/sample_parking_lot.mp4 \
  -c copy -f rtsp rtsp://localhost:8554/test_camera_001 &

# Verify auto-reconnect within 60 seconds
sleep 60
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/cameras/CAM_ID_HERE | jq .status
# → "online"
```

### Expected Failover Behavior Matrix

| Component | Failure | Expected Behavior | Recovery |
|---|---|---|---|
| PostgreSQL | Stopped | API → 503, Celery retries with backoff | Auto on DB restart, <15s |
| PostgreSQL | Slow queries >5s | API → 504 on DB-dependent routes | Resolves when DB recovers |
| Redis | Stopped | API degrades to DB fallback, no 500s | Auto on Redis restart, <5s |
| Redis | Full memory | LRU eviction, cache misses increase | Increase `maxmemory` config |
| RabbitMQ | Stopped | Detection events buffered in producer memory | Backlog processed on restart |
| RabbitMQ | Queue full | Publisher blocks, detection lag increases | Scale consumers |
| Camera | RTSP disconnect | Camera status → "offline" after 30s | Auto-reconnect within 60s |
| Camera | High packet loss | Frame drops increase, detection FPS drops | Automatic adaptation |
| AI Engine | Worker crash | Tasks requeued, other workers pick up | Docker restart policy |
| Frontend | Backend unreachable | "Connection lost" banner shown | Auto-retry every 30s |

---

## 8. Security Testing

### JWT Tampering Test

```python
# tests/security/test_jwt_tampering.py
import pytest
import base64
import json
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_tampered_role_claim_rejected(client: AsyncClient, auth_headers: dict):
    """Modifying the role claim in the JWT payload is detected and rejected."""
    token = auth_headers["Authorization"].split(" ")[1]

    # Decode payload (no signature verification)
    parts = token.split(".")
    payload_bytes = base64.urlsafe_b64decode(parts[1] + "==")
    payload = json.loads(payload_bytes)

    # Escalate role to admin
    payload["role"] = "admin"
    tampered_payload = base64.urlsafe_b64encode(
        json.dumps(payload).encode()
    ).rstrip(b"=").decode()

    tampered_token = f"{parts[0]}.{tampered_payload}.{parts[2]}"

    resp = await client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {tampered_token}"},
    )
    # Signature mismatch → 401 Unauthorized
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_expired_token_rejected(client: AsyncClient, db):
    """An expired JWT is rejected with 401."""
    from datetime import timedelta
    from freezegun import freeze_time
    from app.core.security import create_access_token
    from tests.factories import UserFactory

    user = await UserFactory.create(db)
    with freeze_time("2026-01-01 00:00:00"):
        token = create_access_token(
            {"sub": str(user.id), "role": "operator"},
            expires_delta=timedelta(minutes=1),
        )

    # Token is expired (we're past 2026-01-01 00:01:00)
    resp = await client.get(
        "/api/v1/dashboard/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401
```

### SQL Injection Test

```python
# tests/security/test_sql_injection.py
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_employee_search_sql_injection_blocked(
    client: AsyncClient, auth_headers: dict
):
    """SQL injection attempt in search query is safely parameterized."""
    # Classic injection attempt
    malicious_query = "' OR '1'='1'; DROP TABLE employees; --"

    resp = await client.get(
        f"/api/v1/employees?search={malicious_query}",
        headers=auth_headers,
    )
    # Must return 200 with empty/safe results, not 500
    assert resp.status_code == 200
    # Must not return all employees (injection failed)
    data = resp.json()
    assert isinstance(data["items"], list)
    # Employees table must still exist (no DROP succeeded)
    resp2 = await client.get("/api/v1/employees?page=1&size=1", headers=auth_headers)
    assert resp2.status_code == 200
```

### Rate Limiting Test

```bash
# Test: login endpoint rate limiting
# Expected: first 10 attempts → 401, attempts 11+ → 429

for i in $(seq 1 15); do
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST https://evap.local/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"test@example.com","password":"WrongPassword"}')
  echo "Attempt $i: HTTP $HTTP_CODE"
done

# Expected output:
# Attempt 1: HTTP 401
# Attempt 2: HTTP 401
# ...
# Attempt 10: HTTP 401
# Attempt 11: HTTP 429
# Attempt 12: HTTP 429
# ...
# Attempt 15: HTTP 429
```

### CORS Policy Test

```bash
# Cross-origin request from unauthorized domain should be rejected
curl -s -I \
  -H "Origin: https://evil.example.com" \
  -H "Access-Control-Request-Method: GET" \
  -X OPTIONS \
  https://evap.local/api/v1/dashboard/summary

# Expected: NO Access-Control-Allow-Origin header for unauthorized origins
# The browser will block the request

# Authorized origin should succeed
curl -s -I \
  -H "Origin: https://evap-dashboard.yourdomain.com" \
  -X OPTIONS \
  https://evap.local/api/v1/dashboard/summary
# Expected: Access-Control-Allow-Origin: https://evap-dashboard.yourdomain.com
```

### Path Traversal Test

```bash
# Attempt path traversal on snapshot download endpoint
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer $TOKEN" \
  "https://evap.local/api/v1/snapshots/download?path=../../etc/passwd"
# Expected: 400 Bad Request (path validation rejects traversal)

curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer $TOKEN" \
  "https://evap.local/api/v1/snapshots/download?path=%2F%2F%2Fetc%2Fpasswd"
# Expected: 400 Bad Request (URL-encoded traversal also rejected)
```

---

## 9. CI/CD Testing Pipeline

```yaml
# .github/workflows/ci.yml
name: EVAP CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

env:
  PYTHON_VERSION: "3.13"
  NODE_VERSION: "20"
  POSTGRES_DB: evap_test
  POSTGRES_USER: evap
  POSTGRES_PASSWORD: evap_pass
  REDIS_URL: redis://localhost:6379/1
  RABBITMQ_URL: amqp://evap:evap_rmq_pass@localhost:5672/
  DATABASE_URL: postgresql+asyncpg://evap:evap_pass@localhost:5432/evap_test
  SECRET_KEY: ci-test-secret-key-32-characters!!
  ENV: test

jobs:
  lint:
    name: Lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: pip

      - name: Install lint dependencies
        run: pip install black ruff mypy

      - name: Black format check
        run: black --check app/ tests/

      - name: Ruff lint
        run: ruff check app/ tests/

      - name: MyPy type check
        run: mypy app/ --ignore-missing-imports

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
          cache: npm
          cache-dependency-path: frontend/package-lock.json

      - name: Install frontend dependencies
        working-directory: frontend
        run: npm ci

      - name: ESLint
        working-directory: frontend
        run: npm run lint

      - name: TypeScript check
        working-directory: frontend
        run: npm run type-check

  test-backend:
    name: Backend Tests
    runs-on: ubuntu-latest
    needs: lint

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: evap_test
          POSTGRES_USER: evap
          POSTGRES_PASSWORD: evap_pass
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10

      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 5s
          --health-retries 5

      rabbitmq:
        image: rabbitmq:3-management
        env:
          RABBITMQ_DEFAULT_USER: evap
          RABBITMQ_DEFAULT_PASS: evap_rmq_pass
        ports:
          - 5672:5672
          - 15672:15672
        options: >-
          --health-cmd "rabbitmqctl status"
          --health-interval 10s
          --health-retries 10

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: pip

      - name: Install dependencies
        run: pip install -r requirements.txt -r requirements-dev.txt

      - name: Run DB migrations
        run: alembic upgrade head

      - name: Run unit + integration tests with coverage
        run: |
          pytest tests/ \
            -v \
            --cov=app \
            --cov-report=xml \
            --cov-report=term-missing \
            --cov-fail-under=80 \
            -x \
            --timeout=60

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v4
        with:
          token: ${{ secrets.CODECOV_TOKEN }}
          files: coverage.xml
          flags: backend
          fail_ci_if_error: true

  test-frontend:
    name: Frontend Tests
    runs-on: ubuntu-latest
    needs: lint

    steps:
      - uses: actions/checkout@v4

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
          cache: npm
          cache-dependency-path: frontend/package-lock.json

      - name: Install dependencies
        working-directory: frontend
        run: npm ci

      - name: Run Vitest with coverage
        working-directory: frontend
        run: npm run test:coverage -- --reporter=verbose

      - name: Check coverage threshold (60%)
        working-directory: frontend
        run: |
          COVERAGE=$(cat coverage/coverage-summary.json | jq '.total.lines.pct')
          echo "Frontend line coverage: $COVERAGE%"
          if (( $(echo "$COVERAGE < 60" | bc -l) )); then
            echo "Coverage $COVERAGE% is below the 60% threshold"
            exit 1
          fi

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v4
        with:
          token: ${{ secrets.CODECOV_TOKEN }}
          directory: frontend/coverage
          flags: frontend

  build:
    name: Docker Build Check
    runs-on: ubuntu-latest
    needs: [test-backend, test-frontend]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build backend image
        uses: docker/build-push-action@v5
        with:
          context: .
          file: ./Dockerfile
          push: false
          cache-from: type=gha
          cache-to: type=gha,mode=max
          tags: evap-backend:ci

      - name: Build frontend image
        uses: docker/build-push-action@v5
        with:
          context: ./frontend
          file: ./frontend/Dockerfile
          push: false
          cache-from: type=gha
          cache-to: type=gha,mode=max
          tags: evap-frontend:ci
```

---

## 10. Coverage

### Generate Coverage Reports

```bash
# Full run with HTML + terminal report
pytest tests/ \
  --cov=app \
  --cov-report=html:htmlcov \
  --cov-report=term-missing \
  --cov-report=xml:coverage.xml

# Open HTML report
# Linux/Mac:
open htmlcov/index.html
# Windows:
start htmlcov/index.html
```

### .coveragerc

```ini
# .coveragerc
[run]
source = app
branch = True
omit =
    app/db/migrations/*
    app/db/alembic/*
    app/*/__init__.py
    tests/*
    **/conftest.py

[report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise NotImplementedError
    if TYPE_CHECKING:
    @abstractmethod
    pass

[html]
directory = htmlcov
title = EVAP Coverage Report
```

### Coverage Targets by Module

| Module | Target | Notes |
|---|---|---|
| `app/services/auth.py` | 90% | Critical security path |
| `app/services/attendance.py` | 85% | Core business logic |
| `app/services/employee.py` | 85% | Face enrollment, bulk import |
| `app/services/alert.py` | 85% | Alert rule evaluation |
| `app/services/anpr.py` | 80% | Plate normalization, matching |
| `app/api/v1/routes/` | 80% | Endpoint handlers |
| `app/core/security.py` | 95% | JWT, password hashing |
| `app/db/models.py` | 60% | ORM models (low logic) |
| `app/workers/` | 75% | Celery task handlers |
| `app/ai/` | 60% | AI pipeline (hard to unit test) |
| **Overall** | **80%** | Enforced in CI via `--cov-fail-under=80` |
