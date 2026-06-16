import React, { useState, useEffect, useRef } from 'react';
import { useLocation, Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { alertsAPI } from '../../services/api';
import { RiBellLine, RiMenuLine, RiCheckLine, RiCircleFill } from 'react-icons/ri';
import { formatDistanceToNow } from 'date-fns';

const PAGE_TITLES = {
  '/': 'Dashboard',
  '/cameras': 'Camera Management',
  '/employees': 'Employee Management',
  '/visitors': 'Visitor Management',
  '/vehicles': 'Vehicle Analytics',
  '/attendance': 'Attendance',
  '/alerts': 'Alerts',
  '/floor-map': 'Floor Map',
  '/analytics': 'Analytics',
  '/reports': 'Reports',
  '/settings': 'Settings',
};

const SEVERITY_COLORS = { critical: '#f85149', warning: '#d29922', info: '#58a6ff' };

export default function Navbar({ onToggleSidebar }) {
  const location = useLocation();
  const { user, logout } = useAuth();
  const [alerts, setAlerts] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [showAlerts, setShowAlerts] = useState(false);
  const [showUser, setShowUser] = useState(false);
  const [allCamerasOnline, setAllCamerasOnline] = useState(true);
  const alertRef = useRef(null);
  const userRef = useRef(null);

  const title = PAGE_TITLES[location.pathname] || 'EVAP';

  useEffect(() => {
    loadAlerts();
    const interval = setInterval(loadAlerts, 30000);
    return () => clearInterval(interval);
  }, []);

  async function loadAlerts() {
    try {
      const [alertRes, countRes] = await Promise.all([
        alertsAPI.getAll({ limit: 5, acknowledged: false }),
        alertsAPI.getUnreadCount(),
      ]);
      setAlerts(alertRes.data?.items || alertRes.data || []);
      setUnreadCount(countRes.data?.count || 0);
    } catch {
      // silently ignore
    }
  }

  // Close dropdowns on outside click
  useEffect(() => {
    function handle(e) {
      if (alertRef.current && !alertRef.current.contains(e.target)) setShowAlerts(false);
      if (userRef.current && !userRef.current.contains(e.target)) setShowUser(false);
    }
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, []);

  async function handleAcknowledge(id, e) {
    e.stopPropagation();
    try {
      await alertsAPI.acknowledge(id);
      setAlerts((prev) => prev.filter((a) => a.id !== id));
      setUnreadCount((p) => Math.max(0, p - 1));
    } catch {}
  }

  return (
    <header
      style={{
        height: 60,
        background: '#161b22',
        borderBottom: '1px solid #30363d',
        position: 'fixed',
        top: 0,
        right: 0,
        left: 0,
        zIndex: 1030,
        display: 'flex',
        alignItems: 'center',
        padding: '0 20px',
        gap: 12,
      }}
    >
      <button className="btn btn-link p-0 text-muted d-md-none" onClick={onToggleSidebar}>
        <RiMenuLine size={22} />
      </button>

      <h5 className="mb-0 text-white fw-semibold" style={{ fontSize: 16 }}>{title}</h5>

      <div className="ms-auto d-flex align-items-center gap-3">
        {/* System status */}
        <div className="d-flex align-items-center gap-1" title={allCamerasOnline ? 'All systems online' : 'Some cameras offline'}>
          <RiCircleFill size={10} color={allCamerasOnline ? '#3fb950' : '#f85149'} />
          <span className="text-muted" style={{ fontSize: 12, display: 'none' }}>
            {allCamerasOnline ? 'Online' : 'Issues'}
          </span>
        </div>

        {/* Alert bell */}
        <div className="position-relative" ref={alertRef}>
          <button
            className="btn btn-link p-1 text-muted position-relative"
            onClick={() => { setShowAlerts((p) => !p); setShowUser(false); }}
          >
            <RiBellLine size={20} />
            {unreadCount > 0 && (
              <span
                className="position-absolute top-0 start-100 translate-middle badge rounded-pill bg-danger"
                style={{ fontSize: 10, padding: '2px 5px' }}
              >
                {unreadCount > 99 ? '99+' : unreadCount}
              </span>
            )}
          </button>

          {showAlerts && (
            <div
              className="dropdown-menu dropdown-menu-end show p-0"
              style={{ width: 340, maxHeight: 420, overflowY: 'auto', background: '#161b22', border: '1px solid #30363d' }}
            >
              <div className="px-3 py-2 d-flex justify-content-between align-items-center border-bottom border-secondary">
                <span className="fw-semibold text-white" style={{ fontSize: 14 }}>Alerts</span>
                <Link to="/alerts" className="text-primary" style={{ fontSize: 12 }} onClick={() => setShowAlerts(false)}>View all</Link>
              </div>
              {alerts.length === 0 ? (
                <div className="text-center text-muted py-4" style={{ fontSize: 13 }}>No new alerts</div>
              ) : alerts.map((alert) => (
                <div key={alert.id} className="px-3 py-2 border-bottom border-secondary d-flex align-items-start gap-2"
                  style={{ fontSize: 13 }}>
                  <div className="rounded-circle mt-1" style={{
                    width: 8, height: 8, flexShrink: 0,
                    background: SEVERITY_COLORS[alert.severity] || '#8b949e',
                  }} />
                  <div className="flex-grow-1 overflow-hidden">
                    <div className="text-white text-truncate">{alert.message}</div>
                    <div className="text-muted" style={{ fontSize: 11 }}>
                      {alert.camera_name} &middot; {formatDistanceToNow(new Date(alert.created_at), { addSuffix: true })}
                    </div>
                  </div>
                  <button className="btn btn-link p-0 text-muted" title="Acknowledge"
                    onClick={(e) => handleAcknowledge(alert.id, e)}>
                    <RiCheckLine size={16} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* User menu */}
        <div className="position-relative" ref={userRef}>
          <button
            className="btn btn-link p-0 d-flex align-items-center gap-2 text-decoration-none"
            onClick={() => { setShowUser((p) => !p); setShowAlerts(false); }}
          >
            <div className="rounded-circle d-flex align-items-center justify-content-center text-white fw-bold"
              style={{ width: 32, height: 32, background: 'linear-gradient(135deg, #3fb950, #238636)', fontSize: 13 }}>
              {(user?.full_name || user?.username || 'U').charAt(0).toUpperCase()}
            </div>
            <span className="text-white d-none d-md-block" style={{ fontSize: 13 }}>
              {user?.full_name || user?.username}
            </span>
          </button>

          {showUser && (
            <div className="dropdown-menu dropdown-menu-end show"
              style={{ background: '#161b22', border: '1px solid #30363d', minWidth: 180 }}>
              <div className="px-3 py-2 border-bottom border-secondary">
                <div className="text-white fw-medium" style={{ fontSize: 13 }}>{user?.full_name}</div>
                <div className="text-muted" style={{ fontSize: 11 }}>{user?.email}</div>
              </div>
              <Link className="dropdown-item text-muted" to="/settings" onClick={() => setShowUser(false)}
                style={{ fontSize: 13, background: 'transparent' }}>
                Settings
              </Link>
              <div className="dropdown-divider border-secondary" />
              <button className="dropdown-item text-danger" onClick={logout} style={{ fontSize: 13, background: 'transparent' }}>
                Logout
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
