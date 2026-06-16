import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import {
  RiDashboardLine, RiVideoLine, RiGroupLine, RiUserCheckLine,
  RiCarLine, RiCalendarCheckLine, RiBellLine, RiMapLine,
  RiBarChartLine, RiFileTextLine, RiSettings3Line, RiLogoutBoxLine,
  RiShieldCheckLine, RiMenuFoldLine, RiMenuUnfoldLine,
} from 'react-icons/ri';

const NAV_ITEMS = [
  { to: '/', icon: RiDashboardLine, label: 'Dashboard', exact: true },
  { to: '/cameras', icon: RiVideoLine, label: 'Cameras' },
  { to: '/employees', icon: RiGroupLine, label: 'Employees' },
  { to: '/visitors', icon: RiUserCheckLine, label: 'Visitors' },
  { to: '/vehicles', icon: RiCarLine, label: 'Vehicles' },
  { to: '/attendance', icon: RiCalendarCheckLine, label: 'Attendance' },
  { to: '/alerts', icon: RiBellLine, label: 'Alerts', badge: true },
  { to: '/floor-map', icon: RiMapLine, label: 'Floor Map' },
  { to: '/analytics', icon: RiBarChartLine, label: 'Analytics' },
  { to: '/reports', icon: RiFileTextLine, label: 'Reports' },
  { to: '/settings', icon: RiSettings3Line, label: 'Settings' },
];

export default function Sidebar({ collapsed, onToggle }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const sidebarStyle = {
    width: collapsed ? '70px' : '260px',
    minHeight: '100vh',
    background: '#161b22',
    borderRight: '1px solid #30363d',
    position: 'fixed',
    top: 0,
    left: 0,
    zIndex: 1040,
    transition: 'width 0.25s ease',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  };

  return (
    <nav style={sidebarStyle}>
      {/* Brand */}
      <div
        className="d-flex align-items-center px-3 py-3"
        style={{
          borderBottom: '1px solid #30363d',
          minHeight: '60px',
          gap: '10px',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
        }}
      >
        <div
          className="d-flex align-items-center justify-content-center rounded"
          style={{ width: 36, height: 36, background: 'linear-gradient(135deg, #1f6feb, #0d419d)', flexShrink: 0 }}
        >
          <RiShieldCheckLine size={20} color="#fff" />
        </div>
        {!collapsed && (
          <div>
            <div className="fw-bold text-white" style={{ fontSize: 15, lineHeight: 1.2 }}>EVAP</div>
            <div className="text-muted" style={{ fontSize: 11 }}>v4.0 Enterprise</div>
          </div>
        )}
        <button
          className="btn btn-link ms-auto p-0 text-muted"
          onClick={onToggle}
          title={collapsed ? 'Expand' : 'Collapse'}
          style={{ flexShrink: 0, lineHeight: 1 }}
        >
          {collapsed ? <RiMenuUnfoldLine size={18} /> : <RiMenuFoldLine size={18} />}
        </button>
      </div>

      {/* Navigation */}
      <div className="flex-grow-1 py-2" style={{ overflowY: 'auto', overflowX: 'hidden' }}>
        {NAV_ITEMS.map(({ to, icon: Icon, label, exact }) => (
          <NavLink
            key={to}
            to={to}
            end={exact}
            title={collapsed ? label : undefined}
            style={({ isActive }) => ({
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '10px 16px',
              textDecoration: 'none',
              color: isActive ? '#58a6ff' : '#8b949e',
              background: isActive ? 'rgba(31,111,235,0.12)' : 'transparent',
              borderLeft: isActive ? '3px solid #1f6feb' : '3px solid transparent',
              whiteSpace: 'nowrap',
              fontSize: 14,
              fontWeight: isActive ? 600 : 400,
              transition: 'all 0.15s',
            })}
          >
            <Icon size={20} style={{ flexShrink: 0 }} />
            {!collapsed && <span>{label}</span>}
          </NavLink>
        ))}
      </div>

      {/* User profile */}
      <div style={{ borderTop: '1px solid #30363d', padding: '12px 16px' }}>
        <div className="d-flex align-items-center gap-2" style={{ whiteSpace: 'nowrap', overflow: 'hidden' }}>
          <div
            className="rounded-circle d-flex align-items-center justify-content-center text-white fw-bold"
            style={{
              width: 36,
              height: 36,
              background: 'linear-gradient(135deg, #3fb950, #238636)',
              fontSize: 14,
              flexShrink: 0,
            }}
          >
            {(user?.full_name || user?.username || 'U').charAt(0).toUpperCase()}
          </div>
          {!collapsed && (
            <div className="flex-grow-1 overflow-hidden">
              <div className="text-white fw-medium" style={{ fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {user?.full_name || user?.username}
              </div>
              <div className="text-muted" style={{ fontSize: 11 }}>{user?.role || 'Admin'}</div>
            </div>
          )}
          <button
            className="btn btn-link p-0 text-muted"
            title="Logout"
            onClick={logout}
            style={{ flexShrink: 0 }}
          >
            <RiLogoutBoxLine size={18} />
          </button>
        </div>
      </div>
    </nav>
  );
}
