import React, { useState, useEffect, useMemo } from 'react';
import { alertsAPI } from '../services/api';
import StatusBadge from '../components/common/StatusBadge';
import useWebSocket from '../hooks/useWebSocket';
import { formatDistanceToNow, format } from 'date-fns';
import toast from 'react-hot-toast';
import {
  RiShieldLine, RiCarLine, RiUserLine, RiBuildingLine, RiAlertLine,
  RiCheckLine, RiCheckDoubleLine, RiLoader4Line,
} from 'react-icons/ri';
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell,
} from 'recharts';

const TYPE_ICONS = {
  intrusion: RiShieldLine, vehicle: RiCarLine,
  person: RiUserLine, zone: RiBuildingLine,
};
const SEVERITY_ORDER = { critical: 0, warning: 1, info: 2 };
const BAR_COLORS = { critical: '#f85149', warning: '#d29922', info: '#58a6ff', other: '#8b949e' };

export default function AlertsPage() {
  const [alerts, setAlerts] = useState([]);
  const [stats, setStats] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterSeverity, setFilterSeverity] = useState('all');
  const [filterAcked, setFilterAcked] = useState('unacknowledged');
  const [acking, setAcking] = useState(new Set());
  const [ackingAll, setAckingAll] = useState(false);

  useEffect(() => { load(); }, [filterSeverity, filterAcked]);

  async function load() {
    setLoading(true);
    try {
      const params = {};
      if (filterSeverity !== 'all') params.severity = filterSeverity;
      if (filterAcked !== 'all') params.acknowledged = filterAcked === 'acknowledged';
      const [aRes, sRes] = await Promise.all([
        alertsAPI.getAll({ ...params, limit: 100 }),
        alertsAPI.getStats(),
      ]);
      setAlerts(aRes.data?.items || aRes.data || MOCK_ALERTS);
      setStats(sRes.data || MOCK_STATS);
    } catch {
      setAlerts(MOCK_ALERTS);
      setStats(MOCK_STATS);
    } finally { setLoading(false); }
  }

  useWebSocket({
    onAlert: (alert) => {
      setAlerts((prev) => [alert, ...prev]);
      toast(`New ${alert.severity} alert: ${alert.message}`, {
        icon: alert.severity === 'critical' ? '🚨' : '⚠️',
      });
    },
  });

  async function acknowledge(id) {
    setAcking((p) => new Set([...p, id]));
    try {
      await alertsAPI.acknowledge(id);
      setAlerts((prev) => prev.map((a) => a.id === id ? { ...a, acknowledged: true } : a));
      toast.success('Alert acknowledged');
    } catch { toast.error('Failed'); }
    finally { setAcking((p) => { const s = new Set(p); s.delete(id); return s; }); }
  }

  async function acknowledgeAll() {
    setAckingAll(true);
    try {
      await alertsAPI.acknowledgeAll();
      setAlerts((prev) => prev.map((a) => ({ ...a, acknowledged: true })));
      toast.success('All alerts acknowledged');
    } catch { toast.error('Failed'); }
    finally { setAckingAll(false); }
  }

  const sortedAlerts = useMemo(() =>
    [...alerts].sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 3) - (SEVERITY_ORDER[b.severity] ?? 3)),
    [alerts]
  );

  const unreadCount = alerts.filter((a) => !a.acknowledged).length;

  return (
    <div>
      <div className="d-flex align-items-center justify-content-between mb-3 flex-wrap gap-2">
        <div className="d-flex align-items-center gap-3">
          <h4 className="text-white fw-semibold mb-0">Alerts</h4>
          {unreadCount > 0 && (
            <span className="badge bg-danger" style={{ fontSize: 12 }}>{unreadCount} unread</span>
          )}
        </div>
        <div className="d-flex gap-2 flex-wrap">
          <select className="form-select form-select-sm" value={filterSeverity}
            onChange={(e) => setFilterSeverity(e.target.value)}
            style={{ background: '#0d1117', border: '1px solid #30363d', color: '#e6edf3', width: 'auto' }}>
            <option value="all">All Severity</option>
            <option value="critical">Critical</option>
            <option value="warning">Warning</option>
            <option value="info">Info</option>
          </select>
          <select className="form-select form-select-sm" value={filterAcked}
            onChange={(e) => setFilterAcked(e.target.value)}
            style={{ background: '#0d1117', border: '1px solid #30363d', color: '#e6edf3', width: 'auto' }}>
            <option value="all">All</option>
            <option value="unacknowledged">Unacknowledged</option>
            <option value="acknowledged">Acknowledged</option>
          </select>
          {unreadCount > 0 && (
            <button className="btn btn-sm btn-outline-secondary d-flex align-items-center gap-1"
              onClick={acknowledgeAll} disabled={ackingAll}>
              <RiCheckDoubleLine size={14} />
              {ackingAll ? 'Acking…' : 'Ack All'}
            </button>
          )}
        </div>
      </div>

      {/* Stats chart */}
      <div className="row g-3 mb-3">
        <div className="col-12">
          <div className="card" style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 10 }}>
            <div className="card-header px-3 py-2" style={{ background: 'transparent', borderBottom: '1px solid #30363d' }}>
              <span className="fw-semibold text-white" style={{ fontSize: 14 }}>Alert Activity (Last 7 Days)</span>
            </div>
            <div className="card-body p-2">
              <ResponsiveContainer width="100%" height={140}>
                <BarChart data={stats} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
                  <XAxis dataKey="date" tick={{ fill: '#8b949e', fontSize: 11 }} axisLine={{ stroke: '#30363d' }} tickLine={false} />
                  <YAxis tick={{ fill: '#8b949e', fontSize: 11 }} axisLine={{ stroke: '#30363d' }} tickLine={false} />
                  <Tooltip contentStyle={{ background: '#1c2128', border: '1px solid #30363d', borderRadius: 6, fontSize: 12 }} />
                  <Bar dataKey="critical" name="Critical" fill="#f85149" stackId="a" />
                  <Bar dataKey="warning" name="Warning" fill="#d29922" stackId="a" />
                  <Bar dataKey="info" name="Info" fill="#58a6ff" stackId="a" radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>

      {/* Alert list */}
      {loading ? (
        <div className="text-center py-5">
          <div className="spinner-border text-primary" />
        </div>
      ) : sortedAlerts.length === 0 ? (
        <div className="text-center text-muted py-5">No alerts found</div>
      ) : (
        <div className="d-flex flex-column gap-2">
          {sortedAlerts.map((alert) => {
            const Icon = TYPE_ICONS[(alert.alert_type || '').toLowerCase()] || RiAlertLine;
            return (
              <div key={alert.id}
                className="card"
                style={{
                  background: '#161b22',
                  border: `1px solid ${alert.acknowledged ? '#30363d' : (BAR_COLORS[alert.severity] + '44' || '#30363d')}`,
                  borderRadius: 8,
                  opacity: alert.acknowledged ? 0.6 : 1,
                  transition: 'opacity 0.2s',
                }}>
                <div className="card-body py-2 px-3 d-flex align-items-start gap-3">
                  <div className="rounded d-flex align-items-center justify-content-center mt-1"
                    style={{ width: 32, height: 32, background: '#21262d', flexShrink: 0 }}>
                    <Icon size={16} color={BAR_COLORS[alert.severity] || '#8b949e'} />
                  </div>
                  <div className="flex-grow-1 overflow-hidden">
                    <div className="d-flex align-items-center gap-2 mb-1 flex-wrap">
                      <StatusBadge status={alert.severity} size="sm" />
                      <span className="text-muted" style={{ fontSize: 11 }}>
                        {alert.alert_type} · {alert.camera_name}
                      </span>
                      <span className="text-muted ms-auto" style={{ fontSize: 11 }}>
                        {alert.created_at ? formatDistanceToNow(new Date(alert.created_at), { addSuffix: true }) : ''}
                      </span>
                    </div>
                    <div className="text-white" style={{ fontSize: 13 }}>{alert.message}</div>
                    {alert.person_name && (
                      <div className="text-muted" style={{ fontSize: 11 }}>Person: {alert.person_name}</div>
                    )}
                  </div>
                  {!alert.acknowledged && (
                    <button className="btn btn-sm btn-outline-secondary py-1 px-2 flex-shrink-0"
                      title="Acknowledge" onClick={() => acknowledge(alert.id)} disabled={acking.has(alert.id)}>
                      {acking.has(alert.id)
                        ? <RiLoader4Line size={14} style={{ animation: 'spin 1s linear infinite' }} />
                        : <RiCheckLine size={14} />}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
      <style>{`@keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }`}</style>
    </div>
  );
}

const MOCK_ALERTS = [
  { id: 1, severity: 'critical', alert_type: 'intrusion', message: 'Unauthorized access detected in Server Room', camera_name: 'Server Room Cam', person_name: 'Unknown', created_at: new Date(Date.now() - 300000).toISOString(), acknowledged: false },
  { id: 2, severity: 'warning', alert_type: 'zone', message: 'Zone capacity exceeded — Cafeteria at 95%', camera_name: 'Cafeteria Cam', created_at: new Date(Date.now() - 900000).toISOString(), acknowledged: false },
  { id: 3, severity: 'info', alert_type: 'vehicle', message: 'New vehicle detected: MH-12-AB-5678', camera_name: 'Main Gate Cam', created_at: new Date(Date.now() - 1800000).toISOString(), acknowledged: false },
  { id: 4, severity: 'warning', alert_type: 'person', message: 'Visitor loitering near restricted zone', camera_name: 'Lobby Cam', created_at: new Date(Date.now() - 3600000).toISOString(), acknowledged: true },
  { id: 5, severity: 'info', alert_type: 'intrusion', message: 'After-hours motion detected in Warehouse', camera_name: 'Warehouse Cam', created_at: new Date(Date.now() - 7200000).toISOString(), acknowledged: true },
];

const MOCK_STATS = Array.from({ length: 7 }, (_, i) => {
  const d = new Date(Date.now() - (6 - i) * 86400000);
  return {
    date: format(d, 'dd/MM'),
    critical: Math.floor(Math.random() * 5),
    warning: Math.floor(Math.random() * 10 + 2),
    info: Math.floor(Math.random() * 15 + 5),
  };
});
