import React from 'react';
import { useNavigate } from 'react-router-dom';
import StatusBadge from '../common/StatusBadge';
import { RiVideoLine, RiLoader4Line } from 'react-icons/ri';
import useWebSocket from '../../hooks/useWebSocket';
import { useState } from 'react';

export default function CameraGrid({ cameras: initialCameras = [], loading = false }) {
  const navigate = useNavigate();
  const [cameras, setCameras] = useState(initialCameras);

  // Sync when props change
  React.useEffect(() => { setCameras(initialCameras); }, [initialCameras]);

  // Live camera status updates
  useWebSocket({
    onCameraStatus: ({ camera_id, status, fps, detections }) => {
      setCameras((prev) =>
        prev.map((c) =>
          c.id === camera_id ? { ...c, status, fps: fps ?? c.fps, detections: detections ?? c.detections } : c
        )
      );
    },
  });

  const statusColor = {
    online:   { border: 'rgba(63,185,80,0.3)',  bg: 'rgba(63,185,80,0.05)' },
    offline:  { border: 'rgba(248,81,73,0.3)',  bg: 'rgba(248,81,73,0.05)' },
    degraded: { border: 'rgba(210,153,34,0.3)', bg: 'rgba(210,153,34,0.05)' },
    error:    { border: 'rgba(248,81,73,0.3)',  bg: 'rgba(248,81,73,0.05)' },
  };

  return (
    <div className="card h-100" style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 10 }}>
      <div className="card-header d-flex align-items-center justify-content-between px-3 py-2"
        style={{ background: 'transparent', borderBottom: '1px solid #30363d' }}>
        <span className="fw-semibold text-white" style={{ fontSize: 14 }}>Camera Status</span>
        <button className="btn btn-link p-0 text-primary" style={{ fontSize: 12 }}
          onClick={() => navigate('/cameras')}>Manage →</button>
      </div>
      <div className="card-body p-2">
        {loading ? (
          <div className="text-center py-4">
            <RiLoader4Line size={22} className="text-muted" style={{ animation: 'spin 1s linear infinite' }} />
          </div>
        ) : cameras.length === 0 ? (
          <div className="text-center text-muted py-4" style={{ fontSize: 13 }}>No cameras configured</div>
        ) : (
          <div className="row g-2">
            {cameras.map((cam) => {
              const status = (cam.status || 'unknown').toLowerCase();
              const palette = statusColor[status] || statusColor.offline;
              return (
                <div key={cam.id} className="col-6 col-md-4">
                  <div
                    className="rounded p-2 cursor-pointer"
                    style={{
                      background: palette.bg,
                      border: `1px solid ${palette.border}`,
                      cursor: 'pointer',
                      transition: 'opacity 0.15s',
                    }}
                    onClick={() => navigate('/cameras')}
                    onMouseOver={(e) => (e.currentTarget.style.opacity = 0.8)}
                    onMouseOut={(e) => (e.currentTarget.style.opacity = 1)}
                  >
                    <div className="d-flex align-items-center gap-2 mb-1">
                      <RiVideoLine size={14} color="#8b949e" />
                      <span className="text-white text-truncate" style={{ fontSize: 12, fontWeight: 500 }}>
                        {cam.name}
                      </span>
                    </div>
                    <StatusBadge status={status} size="sm" />
                    <div className="text-muted mt-1" style={{ fontSize: 11 }}>
                      {cam.fps ? `${cam.fps} FPS` : '—'}
                      {cam.detections !== undefined ? ` · ${cam.detections} det` : ''}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
      <style>{`@keyframes spin { from { transform:rotate(0deg); } to { transform:rotate(360deg); } }`}</style>
    </div>
  );
}
