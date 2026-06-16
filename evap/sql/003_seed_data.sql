-- =============================================================================
-- EVAP Phase 4 Seed Data - 003_seed_data.sql
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- ROLES (RBAC)
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO roles (name, permissions) VALUES
(
    'super_admin',
    '{
        "users": ["create","read","update","delete"],
        "roles": ["create","read","update","delete"],
        "sites": ["create","read","update","delete"],
        "cameras": ["create","read","update","delete"],
        "alerts": ["create","read","update","delete","acknowledge"],
        "reports": ["create","read","delete"],
        "watchlist": ["create","read","update","delete"],
        "analytics": ["read","export"],
        "system": ["read","configure"],
        "api_keys": ["create","read","update","delete"],
        "erp": ["configure","sync"]
    }'
),
(
    'admin',
    '{
        "users": ["create","read","update"],
        "roles": ["read"],
        "sites": ["create","read","update"],
        "cameras": ["create","read","update"],
        "alerts": ["read","update","acknowledge"],
        "reports": ["create","read"],
        "watchlist": ["create","read","update","delete"],
        "analytics": ["read","export"],
        "system": ["read"],
        "api_keys": ["create","read","update"],
        "erp": ["sync"]
    }'
),
(
    'operator',
    '{
        "users": ["read"],
        "sites": ["read"],
        "cameras": ["read","update"],
        "alerts": ["read","acknowledge"],
        "reports": ["create","read"],
        "watchlist": ["read"],
        "analytics": ["read"],
        "system": ["read"]
    }'
),
(
    'viewer',
    '{
        "sites": ["read"],
        "cameras": ["read"],
        "alerts": ["read"],
        "reports": ["read"],
        "analytics": ["read"]
    }'
),
(
    'api_user',
    '{
        "cameras": ["read"],
        "alerts": ["read","create"],
        "analytics": ["read"],
        "watchlist": ["read"]
    }'
)
ON CONFLICT (name) DO UPDATE SET permissions = EXCLUDED.permissions;

-- ─────────────────────────────────────────────────────────────────────────────
-- DEFAULT ADMIN USER
-- Password: Admin@EVAP2026! — bcrypt hash (cost 12)
-- IMPORTANT: Change this password immediately after first login.
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO users (username, email, hashed_password, role, is_active, mfa_enabled)
VALUES (
    'admin',
    'admin@evap.local',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBpj2Z4cFp2WC6',
    'super_admin',
    TRUE,
    FALSE
)
ON CONFLICT (username) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- SAMPLE SITE
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO site_master (name, address, city, country, timezone, coord_lat, coord_lon, is_active)
VALUES (
    'HQ Campus',
    '100 Corporate Park, Whitefield',
    'Bengaluru',
    'IN',
    'Asia/Kolkata',
    12.9716,
    77.5946,
    TRUE
)
ON CONFLICT DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- SAMPLE BUILDING
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO building_master (site_id, name, floors_count, description)
SELECT s.site_id, 'Tower A', 5, 'Main office tower'
FROM site_master s WHERE s.name = 'HQ Campus'
ON CONFLICT DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- SAMPLE FLOORS
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO floor_master (building_id, floor_number, name, width_meters, height_meters)
SELECT
    b.building_id,
    f.floor_number,
    f.floor_name,
    80.0,
    60.0
FROM building_master b
CROSS JOIN (
    VALUES
        (0, 'Ground Floor'),
        (1, 'First Floor'),
        (2, 'Second Floor'),
        (3, 'Third Floor'),
        (4, 'Fourth Floor')
) AS f(floor_number, floor_name)
WHERE b.name = 'Tower A'
ON CONFLICT (building_id, floor_number) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- SAMPLE ZONES (Ground Floor)
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO zone_master (floor_id, name, zone_type, max_capacity, is_restricted, color_code)
SELECT
    f.floor_id,
    z.zone_name,
    z.zone_type,
    z.max_cap,
    z.restricted,
    z.color
FROM floor_master f
JOIN building_master b ON b.building_id = f.building_id
JOIN site_master s     ON s.site_id     = b.site_id
CROSS JOIN (
    VALUES
        ('Main Entrance',   'entrance',    50,  FALSE, '#4CAF50'),
        ('Reception Lobby', 'lobby',       80,  FALSE, '#2196F3'),
        ('Ground Canteen',  'canteen',     200, FALSE, '#FF9800'),
        ('Server Room GF',  'server_room', 10,  TRUE,  '#F44336'),
        ('Parking Level 0', 'parking',     150, FALSE, '#9E9E9E')
) AS z(zone_name, zone_type, max_cap, restricted, color)
WHERE s.name = 'HQ Campus'
  AND f.floor_number = 0
ON CONFLICT DO NOTHING;
