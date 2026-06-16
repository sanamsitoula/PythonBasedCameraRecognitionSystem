import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { camerasAPI } from '../services/api';
import StatusBadge from '../components/common/StatusBadge';
import toast from 'react-hot-toast';
import {
  RiAddLine, RiEditLine, RiDeleteBinLine, RiRestartLine,
  RiCameraLine, RiWifiLine, RiWifiOffLine, RiSignalWifiLine,
} from 'react-icons/ri';

const CAMERA_TYPES = ['fixed', 'ptz', 'fisheye', 'thermal', 'anpr', '360'];

const EMPTY_FORM = {
  name: '', site: '', ip_address: '', username: '',
  password: '', rtsp_url: '', camera_type: 'fixed', zone: '',
};

const FIELD_STYLE = {
  background: '#0d1117', border: '1px solid #30363d',
  color: '#e6edf3', borderRadius: 6,
};

export default function CamerasPage() {
  const [cameras, setCameras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState(null);   // null = add mode, object = edit mode
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [filterStatus, setFilterStatus] = useState('');
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    load().then(checkAllHealth);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function load() {
    setLoading(true);
    try {
      const res = await camerasAPI.getAll();
      setCameras(res.data?.items || res.data || []);
    } catch {
      setCameras([]);
    } finally {
      setLoading(false);
    }
  }

  async function checkAllHealth() {
    setChecking(true);
    try {
      await camerasAPI.healthCheckAll();
      // Wait 4 s for background pings to finish, then reload statuses
      await new Promise(r => setTimeout(r, 4000));
      const res = await camerasAPI.getAll();
      setCameras(res.data?.items || res.data || []);
    } catch {
      // silent — health check is best-effort
    } finally {
      setChecking(false);
    }
  }

  const filtered = useMemo(() =>
    filterStatus ? cameras.filter(c => c.status === filterStatus) : cameras,
    [cameras, filterStatus]
  );

  function openAdd() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setShowModal(true);
  }

  function openEdit(cam) {
    setEditing(cam);
    setForm({
      name: cam.name || '',
      site: cam.site || cam.manufacturer || '',
      ip_address: cam.ip_address || '',
      username: '',
      password: '',
      rtsp_url: '',
      camera_type: cam.camera_type || 'fixed',
      zone: cam.zone || cam.model || '',
    });
    setShowModal(true);
  }

  async function handleSave() {
    if (!form.name.trim()) { toast.error('Camera name is required'); return; }
    setSaving(true);
    try {
      if (editing) {
        await camerasAPI.update(editing.id, form);
        toast.success('Camera updated');
      } else {
        await camerasAPI.create(form);
        toast.success('Camera added');
      }
      setShowModal(false);
      load();
    } catch (e) {
      const detail = e?.response?.data?.detail;
      const msg = Array.isArray(detail)
        ? detail.map(d => d.msg).join('; ')
        : (typeof detail === 'string' ? detail : 'Failed to save camera');
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    try {
      await camerasAPI.delete(deleteTarget.id);
      toast.success('Camera deleted');
      setDeleteTarget(null);
      load();
    } catch {
      toast.error('Failed to delete camera');
    }
  }

  async function handleRestart(cam) {
    try {
      await camerasAPI.restartStream(cam.id);
      toast.success(`Stream restarted for ${cam.name}`);
      load();
    } catch {
      toast.error('Failed to restart stream');
    }
  }

  const cardStyle = {
    background: '#161b22', border: '1px solid #30363d',
    borderRadius: 10, padding: '14px 16px',
  };

  return (
    <div>
      {/* Header */}
      <div className="d-flex align-items-center justify-content-between mb-3">
        <div>
          <h4 className="text-white fw-semibold mb-0">Cameras</h4>
          <span className="text-muted" style={{ fontSize: 13 }}>
            {cameras.length} camera{cameras.length !== 1 ? 's' : ''} registered
          </span>
        </div>
        <div className="d-flex gap-2">
          <button
            className="btn btn-sm btn-outline-secondary d-flex align-items-center gap-1"
            onClick={checkAllHealth} disabled={checking}
            title="Ping all cameras via TCP:554 and update online/offline status">
            <RiSignalWifiLine size={15} />
            {checking ? 'Checking…' : 'Check Online'}
          </button>
          <button className="btn btn-primary btn-sm d-flex align-items-center gap-1" onClick={openAdd}>
            <RiAddLine size={16} /> Add Camera
          </button>
        </div>
      </div>

      {/* Filter bar */}
      <div className="d-flex gap-2 mb-3">
        {['', 'online', 'offline', 'error', 'maintenance'].map(s => (
          <button key={s}
            className={`btn btn-sm ${filterStatus === s ? 'btn-primary' : 'btn-outline-secondary'}`}
            onClick={() => setFilterStatus(s)}
            style={{ fontSize: 12 }}>
            {s === '' ? 'All' : s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}
      </div>

      {/* Camera grid */}
      {loading ? (
        <div className="text-center py-5 text-muted">Loading cameras…</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-5" style={{ color: '#8b949e' }}>
          <RiCameraLine size={48} style={{ opacity: 0.3 }} />
          <div className="mt-2" style={{ fontSize: 14 }}>
            {cameras.length === 0
              ? 'No cameras registered yet. Click "+ Add Camera" to add one.'
              : 'No cameras match the current filter.'}
          </div>
        </div>
      ) : (
        <div className="row g-3">
          {filtered.map(cam => (
            <div key={cam.id} className="col-md-6 col-xl-4">
              <div style={cardStyle}>
                {/* Camera header */}
                <div className="d-flex align-items-start justify-content-between mb-2">
                  <div className="d-flex align-items-center gap-2">
                    <div style={{
                      width: 36, height: 36, borderRadius: 8,
                      background: cam.status === 'online' ? 'rgba(63,185,80,0.15)' : 'rgba(139,148,158,0.15)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}>
                      {cam.status === 'online'
                        ? <RiWifiLine size={18} color="#3fb950" />
                        : <RiWifiOffLine size={18} color="#8b949e" />}
                    </div>
                    <div>
                      <div className="text-white fw-medium" style={{ fontSize: 14 }}>{cam.name}</div>
                      <div className="text-muted" style={{ fontSize: 11 }}>{cam.ip_address || '—'}</div>
                    </div>
                  </div>
                  <StatusBadge status={cam.status} />
                </div>

                {/* Snapshot placeholder */}
                <div style={{
                  background: '#0d1117', borderRadius: 8, height: 120,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  border: '1px solid #21262d', marginBottom: 12, position: 'relative', overflow: 'hidden',
                }}>
                  <div className="text-center" style={{ color: '#30363d' }}>
                    <RiCameraLine size={32} />
                    <div style={{ fontSize: 11, marginTop: 4 }}>
                      {cam.status === 'online' ? 'Live stream' : 'Stream offline'}
                    </div>
                  </div>
                  {cam.status === 'online' && (
                    <span style={{
                      position: 'absolute', top: 6, left: 8, background: 'rgba(248,81,73,0.85)',
                      color: '#fff', fontSize: 10, padding: '1px 6px', borderRadius: 4, fontWeight: 600,
                    }}>● LIVE</span>
                  )}
                  <span style={{
                    position: 'absolute', top: 6, right: 8, background: 'rgba(0,0,0,0.6)',
                    color: '#8b949e', fontSize: 10, padding: '1px 6px', borderRadius: 4,
                  }}>{cam.camera_type}</span>
                </div>

                {/* Stats row */}
                <div className="d-flex gap-2 mb-2" style={{ fontSize: 11 }}>
                  {[
                    { label: 'Site', val: cam.site || cam.manufacturer || '—' },
                    { label: 'Zone', val: cam.zone || cam.model || '—' },
                    { label: 'FPS', val: cam.fps ?? '—' },
                  ].map(({ label, val }) => (
                    <div key={label} style={{
                      flex: 1, background: '#0d1117', borderRadius: 6,
                      padding: '4px 8px', textAlign: 'center',
                    }}>
                      <div className="text-muted">{label}</div>
                      <div className="text-white fw-medium">{val}</div>
                    </div>
                  ))}
                </div>

                {cam.last_heartbeat && (
                  <div className="text-muted mb-2" style={{ fontSize: 10 }}>
                    Last seen: {new Date(cam.last_heartbeat).toLocaleString()}
                  </div>
                )}

                {/* Actions */}
                <div className="d-flex gap-1">
                  <button className="btn btn-sm btn-outline-primary flex-fill py-1"
                    style={{ fontSize: 11 }} onClick={() => openEdit(cam)}>
                    <RiEditLine size={12} /> Edit
                  </button>
                  <button className="btn btn-sm btn-outline-warning py-1 px-2"
                    title="Restart stream" onClick={() => handleRestart(cam)}>
                    <RiRestartLine size={13} />
                  </button>
                  <button className="btn btn-sm btn-outline-danger py-1 px-2"
                    title="Delete" onClick={() => setDeleteTarget(cam)}>
                    <RiDeleteBinLine size={13} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add / Edit Modal */}
      {showModal && (
        <div className="modal show d-block" style={{ background: 'rgba(0,0,0,0.7)' }}>
          <div className="modal-dialog modal-lg modal-dialog-centered">
            <div className="modal-content" style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 12 }}>
              <div className="modal-header" style={{ borderColor: '#30363d' }}>
                <h5 className="modal-title text-white" style={{ fontSize: 15 }}>
                  {editing ? 'Edit Camera' : 'Add Camera'}
                </h5>
                <button className="btn-close btn-close-white btn-sm" onClick={() => setShowModal(false)} />
              </div>
              <div className="modal-body">
                <div className="row g-3">
                  {/* Name */}
                  <div className="col-md-6">
                    <label className="form-label text-muted" style={{ fontSize: 12 }}>Camera Name *</label>
                    <input className="form-control form-control-sm" style={FIELD_STYLE}
                      value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} />
                  </div>
                  {/* IP */}
                  <div className="col-md-6">
                    <label className="form-label text-muted" style={{ fontSize: 12 }}>IP Address</label>
                    <input className="form-control form-control-sm" style={FIELD_STYLE}
                      value={form.ip_address} onChange={e => setForm(p => ({ ...p, ip_address: e.target.value }))} />
                  </div>
                  {/* Type */}
                  <div className="col-md-6">
                    <label className="form-label text-muted" style={{ fontSize: 12 }}>Camera Type</label>
                    <select className="form-select form-select-sm" style={FIELD_STYLE}
                      value={form.camera_type} onChange={e => setForm(p => ({ ...p, camera_type: e.target.value }))}>
                      {CAMERA_TYPES.map(t => <option key={t}>{t}</option>)}
                    </select>
                  </div>
                  {/* Site */}
                  <div className="col-md-6">
                    <label className="form-label text-muted" style={{ fontSize: 12 }}>Site</label>
                    <input className="form-control form-control-sm" style={FIELD_STYLE}
                      placeholder="e.g. Main Campus"
                      value={form.site} onChange={e => setForm(p => ({ ...p, site: e.target.value }))} />
                  </div>
                  {/* RTSP URL */}
                  <div className="col-12">
                    <label className="form-label text-muted" style={{ fontSize: 12 }}>RTSP URL</label>
                    <input className="form-control form-control-sm" style={FIELD_STYLE}
                      placeholder="rtsp://user:pass@ip:554/stream"
                      value={form.rtsp_url} onChange={e => setForm(p => ({ ...p, rtsp_url: e.target.value }))} />
                  </div>
                  {/* Username / Password */}
                  <div className="col-md-6">
                    <label className="form-label text-muted" style={{ fontSize: 12 }}>Username</label>
                    <input className="form-control form-control-sm" style={FIELD_STYLE}
                      value={form.username} onChange={e => setForm(p => ({ ...p, username: e.target.value }))} />
                  </div>
                  <div className="col-md-6">
                    <label className="form-label text-muted" style={{ fontSize: 12 }}>Password</label>
                    <input type="password" className="form-control form-control-sm" style={FIELD_STYLE}
                      value={form.password} onChange={e => setForm(p => ({ ...p, password: e.target.value }))} />
                  </div>
                  {/* Zone */}
                  <div className="col-md-6">
                    <label className="form-label text-muted" style={{ fontSize: 12 }}>Zone</label>
                    <input className="form-control form-control-sm" style={FIELD_STYLE}
                      placeholder="e.g. Entry, Parking"
                      value={form.zone} onChange={e => setForm(p => ({ ...p, zone: e.target.value }))} />
                  </div>
                </div>
              </div>
              <div className="modal-footer" style={{ borderColor: '#30363d' }}>
                <button className="btn btn-secondary btn-sm" onClick={() => setShowModal(false)}>Cancel</button>
                <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
                  {saving ? 'Saving…' : editing ? 'Save Changes' : 'Add Camera'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delete confirm */}
      {deleteTarget && (
        <div className="modal show d-block" style={{ background: 'rgba(0,0,0,0.7)' }}>
          <div className="modal-dialog modal-sm modal-dialog-centered">
            <div className="modal-content" style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 12 }}>
              <div className="modal-header" style={{ borderColor: '#30363d' }}>
                <h5 className="modal-title text-white" style={{ fontSize: 15 }}>Delete Camera</h5>
              </div>
              <div className="modal-body">
                <p className="text-white mb-0" style={{ fontSize: 14 }}>
                  Delete <strong>{deleteTarget.name}</strong>? This cannot be undone.
                </p>
              </div>
              <div className="modal-footer" style={{ borderColor: '#30363d' }}>
                <button className="btn btn-secondary btn-sm" onClick={() => setDeleteTarget(null)}>Cancel</button>
                <button className="btn btn-danger btn-sm" onClick={handleDelete}>Delete</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
