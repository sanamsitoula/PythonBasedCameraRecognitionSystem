import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { alertsAPI } from '../../services/api';
import useWebSocket from '../../hooks/useWebSocket';
import StatusBadge from '../common/StatusBadge';
import { formatDistanceToNow } from 'date-fns';
import {
  RiShieldLine, RiCarLine, RiUserLine, RiBuildingLine,
  RiAlertLine, RiCheckLine, RiLoader4Line,
} from 'react-icons/ri';

const TYPE_ICONS = {
  intrusion:    RiShieldLine,
  vehicle:      RiCarLine,
  person:       RiUserLine,
  zone:         RiBuildingLine,
};

function getIcon(type) {
  const Icon = TYPE_ICONS[(type || '').toLowerCase()] || RiAlertLine;
  return Icon;
}

export default function AlertsPanel() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [acking, setAcking] = useState(new Set());

  useEffect(() => { load(); }, []);

  async function load() {
    try {
      const res = await alertsAPI.getAll({ limit: 10, acknowledged: false });
      setAlerts(res.data?.items || res.data || []);
    } catch { setAlerts([]); }
    finally { setLoading(false); }
  }

  useWebSocket({
    onAlert: (alert) => {
      setAlerts((prev) => [alert, ...prev].slice(0, 10));
    },
  });

  async function acknowledge(id) {
    setAcking((p) => new Set([...p, id]));
    try {
      await alertsAPI.acknowledge(id);
      setAlerts((prev) => prev.filter((a) => a.id !== id));
    } catch {}
    finally { setAcking((p) => { const s = new Set(p); s.delete(id); return s; }); }
  }

  return (
    <div className="card h-100" style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 10 }}>
      <div className="card-header d-flex align-items-center justify-content-between px-3 py-2"
        style={{ background: 'transparent', borderBottom: '1px solid #30363d' }}>
        <span className="fw-semibold text-white" style={{ fontSize: 14 }}>Active Alerts</span>
        <Link to="/alerts" style={{ fontSize: 12, color: '#58a6ff' }}>View All →</Link>
      </div>

      <div className="card-body p-0" style={{ overflowY: 'auto', maxHeight: 340 }}>
        {loading ? (
          <div className="text-center py-4">
            <RiLoader4Line size={22} className="text-muted" style={{ animation: 'spin 1s linear infinite' }} />
          </div>
        ) : alerts.length === 0 ? (
          <div className="text-center text-muted py-5" style={{ fontSize: 13 }}>No active alerts</div>
        ) : alerts.map((alert) => {
          const Icon = getIcon(alert.alert_type);
          return (
            <div key={alert.id} className="px-3 py-2 border-bottom d-flex align-items-start gap-2"
              style={{ borderColor: '#30363d', fontSize: 13 }}>
              <Icon size={16} style={{ flexShrink: 0, marginTop: 2, color: '#8b949e' }} />
              <div className="flex-grow-1 overflow-hidden">
                <div className="d-flex align-items-center gap-2 mb-1">
                  <StatusBadge status={alert.severity} size="sm" />
                  <span className="text-muted" style={{ fontSize: 11 }}>
                    {formatDistanceToNow(new Date(alert.created_at || Date.now()), { addSuffix: true })}
                  </span>
                </div>
                <div className="text-white text-truncate">{alert.message}</div>
                {alert.camera_name && (
                  <div className="text-muted" style={{ fontSize: 11 }}>{alert.camera_name}</div>
                )}
              </div>
              <button
                className="btn btn-link p-0 text-muted"
                title="Acknowledge"
                onClick={() => acknowledge(alert.id)}
                disabled={acking.has(alert.id)}
              >
                {acking.has(alert.id) ? <RiLoader4Line size={15} /> : <RiCheckLine size={15} />}
              </button>
            </div>
          );
        })}
      </div>

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
