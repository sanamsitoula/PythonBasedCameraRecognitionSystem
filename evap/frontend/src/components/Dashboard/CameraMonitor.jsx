import React, { useState, useEffect } from 'react';
import { camerasAPI, dashboardAPI } from '../../services/api';
import {
  RiCameraLine, RiGroupLine, RiManLine, RiWomanLine,
  RiArrowLeftLine, RiArrowRightLine, RiRefreshLine,
  RiWifiLine, RiWifiOffLine, RiUserLine,
} from 'react-icons/ri';

const REFRESH_INTERVAL = 15000; // 15 seconds

function StatBox({ label, value, color = '#e6edf3', sub }) {
  return (
    <div style={{
      background: '#0d1117', borderRadius: 8, padding: '10px 12px',
      textAlign: 'center', flex: 1,
    }}>
      <div style={{ fontSize: 11, color: '#8b949e', marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700, color }}>{value ?? '—'}</div>
      {sub && <div style={{ fontSize: 10, color: '#6e7681', marginTop: 1 }}>{sub}</div>}
    </div>
  );
}

function GenderBar({ male = 0, female = 0 }) {
  const total = male + female;
  const malePct = total > 0 ? Math.round((male / total) * 100) : 50;
  const femalePct = 100 - malePct;
  return (
    <div>
      <div className="d-flex justify-content-between mb-1" style={{ fontSize: 11, color: '#8b949e' }}>
        <span><RiManLine size={12} /> Male {malePct}%</span>
        <span>Female {femalePct}% <RiWomanLine size={12} /></span>
      </div>
      <div style={{ height: 6, borderRadius: 3, background: '#21262d', overflow: 'hidden' }}>
        <div style={{
          height: '100%', width: `${malePct}%`,
          background: 'linear-gradient(90deg, #1f6feb, #58a6ff)',
          borderRadius: 3,
        }} />
      </div>
    </div>
  );
}

function CameraCard({ cam, stats }) {
  const isOnline = cam.status === 'online';
  return (
    <div style={{
      background: '#161b22', border: '1px solid #30363d',
      borderRadius: 10, overflow: 'hidden',
    }}>
      {/* Stream preview */}
      <div style={{
        background: '#0d1117', height: 160, position: 'relative',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        borderBottom: '1px solid #21262d',
      }}>
        <div className="text-center" style={{ color: '#21262d' }}>
          <RiCameraLine size={40} />
          <div style={{ fontSize: 11, marginTop: 4, color: '#30363d' }}>
            {isOnline ? 'RTSP stream' : 'Offline'}
          </div>
        </div>
        {/* Overlays */}
        <div style={{ position: 'absolute', top: 8, left: 10, display: 'flex', gap: 6 }}>
          {isOnline && (
            <span style={{
              background: 'rgba(248,81,73,0.85)', color: '#fff',
              fontSize: 10, padding: '2px 6px', borderRadius: 4, fontWeight: 700,
            }}>● LIVE</span>
          )}
        </div>
        <div style={{ position: 'absolute', top: 8, right: 10 }}>
          {isOnline
            ? <RiWifiLine size={14} color="#3fb950" />
            : <RiWifiOffLine size={14} color="#f85149" />}
        </div>
        {/* People count overlay */}
        {stats?.people_count > 0 && (
          <div style={{
            position: 'absolute', bottom: 8, left: 10,
            background: 'rgba(0,0,0,0.7)', color: '#e6edf3',
            fontSize: 11, padding: '2px 8px', borderRadius: 4,
            display: 'flex', alignItems: 'center', gap: 4,
          }}>
            <RiGroupLine size={12} /> {stats.people_count} detected
          </div>
        )}
      </div>

      {/* Camera info */}
      <div style={{ padding: '10px 12px' }}>
        <div className="d-flex justify-content-between align-items-start mb-2">
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#e6edf3' }}>{cam.name}</div>
            <div style={{ fontSize: 11, color: '#8b949e' }}>
              {cam.ip_address || '—'} · {cam.site || cam.manufacturer || '—'}
            </div>
          </div>
          <span style={{
            fontSize: 10, padding: '2px 6px', borderRadius: 4, fontWeight: 600,
            background: isOnline ? 'rgba(63,185,80,0.15)' : 'rgba(248,81,73,0.15)',
            color: isOnline ? '#3fb950' : '#f85149',
          }}>
            {cam.status || 'offline'}
          </span>
        </div>

        {/* Live stats from DB */}
        <div className="d-flex gap-2 mb-2">
          <StatBox label="People" value={stats?.people_count ?? 0} color="#58a6ff" />
          <StatBox label="Male" value={stats?.male_count ?? 0} color="#79c0ff" />
          <StatBox label="Female" value={stats?.female_count ?? 0} color="#ff7b72" />
          <StatBox label="Recognized" value={stats?.recognized ?? 0} color="#3fb950" />
        </div>

        {/* Gender bar */}
        <GenderBar male={stats?.male_count ?? 0} female={stats?.female_count ?? 0} />

        {/* Bottom row */}
        <div className="d-flex justify-content-between mt-2" style={{ fontSize: 10, color: '#6e7681' }}>
          <span>Zone: {cam.zone || cam.model || '—'}</span>
          <span>FPS: {cam.fps ?? '—'}</span>
          {stats?.last_detection && (
            <span>Last: {new Date(stats.last_detection).toLocaleTimeString()}</span>
          )}
        </div>
      </div>
    </div>
  );
}

export default function CameraMonitor() {
  const [cameras, setCameras] = useState([]);
  const [stats, setStats] = useState({});      // keyed by camera_id
  const [summary, setSummary] = useState(null); // dashboard-level stats
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const PER_PAGE = 4;

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchStats, REFRESH_INTERVAL);
    return () => clearInterval(interval);
  }, []);

  async function fetchAll() {
    setLoading(true);
    await Promise.all([fetchCameras(), fetchStats()]);
    setLoading(false);
  }

  async function fetchCameras() {
    try {
      const res = await camerasAPI.getAll();
      setCameras(res.data?.items || res.data || []);
    } catch {
      setCameras([]);
    }
  }

  async function fetchStats() {
    setRefreshing(true);
    try {
      // Pull latest dashboard stats for people/gender counts
      const res = await dashboardAPI.getStats();
      const data = res.data || {};
      setSummary(data);

      // Build per-camera stats from what we know
      // (full per-camera stats require per-camera API — use summary totals for now)
      setStats(prev => {
        const updated = { ...prev };
        // Distribute summary stats proportionally if we have cameras
        // This will be replaced by real per-camera endpoints later
        return updated;
      });
    } catch {
      // ignore stats errors
    } finally {
      setRefreshing(false);
    }
  }

  async function manualRefresh() {
    await fetchAll();
    toast && toast.success && null; // silent refresh
  }

  const totalPages = Math.ceil(cameras.length / PER_PAGE);
  const pageCameras = cameras.slice(page * PER_PAGE, (page + 1) * PER_PAGE);

  if (loading) {
    return (
      <div style={{
        background: '#161b22', border: '1px solid #30363d',
        borderRadius: 12, padding: 24, textAlign: 'center', color: '#8b949e',
      }}>
        Loading cameras…
      </div>
    );
  }

  if (cameras.length === 0) {
    return (
      <div style={{
        background: '#161b22', border: '1px solid #30363d',
        borderRadius: 12, padding: 32, textAlign: 'center',
      }}>
        <RiCameraLine size={40} style={{ color: '#30363d', marginBottom: 8 }} />
        <div style={{ fontSize: 13, color: '#8b949e' }}>
          No cameras registered. Go to <strong style={{ color: '#58a6ff' }}>Cameras</strong> page to add one.
        </div>
      </div>
    );
  }

  return (
    <div style={{
      background: '#161b22', border: '1px solid #30363d',
      borderRadius: 12, padding: 16,
    }}>
      {/* Header */}
      <div className="d-flex align-items-center justify-content-between mb-3">
        <div>
          <span style={{ fontSize: 14, fontWeight: 600, color: '#e6edf3' }}>
            Camera Monitor
          </span>
          <span className="ms-2" style={{ fontSize: 12, color: '#8b949e' }}>
            {cameras.filter(c => c.status === 'online').length}/{cameras.length} online
          </span>
        </div>
        <div className="d-flex align-items-center gap-2">
          {refreshing && (
            <RiRefreshLine size={14} style={{ color: '#8b949e', animation: 'spin 1s linear infinite' }} />
          )}
          <button className="btn btn-sm btn-outline-secondary py-0 px-2"
            style={{ fontSize: 11 }} onClick={manualRefresh}>
            Refresh
          </button>
          {totalPages > 1 && (
            <>
              <button className="btn btn-sm btn-outline-secondary py-0 px-2"
                disabled={page === 0} onClick={() => setPage(p => p - 1)}>
                <RiArrowLeftLine size={12} />
              </button>
              <span style={{ fontSize: 11, color: '#8b949e' }}>{page + 1}/{totalPages}</span>
              <button className="btn btn-sm btn-outline-secondary py-0 px-2"
                disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}>
                <RiArrowRightLine size={12} />
              </button>
            </>
          )}
        </div>
      </div>

      {/* Summary row */}
      {summary && (
        <div className="d-flex gap-2 mb-3">
          {[
            { label: 'People Now', val: summary.people_count ?? summary.total_people ?? 0, color: '#58a6ff' },
            { label: 'Employees', val: summary.employees_present ?? 0, color: '#3fb950' },
            { label: 'Visitors', val: summary.visitors_today ?? 0, color: '#d29922' },
            { label: 'Alerts', val: summary.active_alerts ?? 0, color: '#f85149' },
          ].map(({ label, val, color }) => (
            <div key={label} style={{
              flex: 1, background: '#0d1117', borderRadius: 8,
              padding: '8px 12px', textAlign: 'center',
            }}>
              <div style={{ fontSize: 10, color: '#8b949e' }}>{label}</div>
              <div style={{ fontSize: 18, fontWeight: 700, color }}>{val}</div>
            </div>
          ))}
        </div>
      )}

      {/* Camera cards grid */}
      <div className="row g-3">
        {pageCameras.map(cam => (
          <div key={cam.id} className="col-md-6">
            <CameraCard
              cam={cam}
              stats={stats[cam.id] || null}
            />
          </div>
        ))}
      </div>

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
