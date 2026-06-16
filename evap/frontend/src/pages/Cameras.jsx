import React, { useState, useEffect, useMemo } from 'react';
import { camerasAPI } from '../services/api';
import DataTable from '../components/common/DataTable';
import Modal from '../components/common/Modal';
import StatusBadge from '../components/common/StatusBadge';
import { createColumnHelper } from '@tanstack/react-table';
import toast from 'react-hot-toast';
import { RiAddLine, RiEditLine, RiDeleteBinLine, RiRestartLine, RiHeartPulseLine } from 'react-icons/ri';

const colHelper = createColumnHelper();

const CAMERA_TYPES = ['IP', 'RTSP', 'USB', 'NVR', 'DVR'];
const SITES = ['Main Campus', 'Branch A', 'Branch B', 'Warehouse', 'Parking'];

const EMPTY_FORM = {
  name: '', site: '', ip_address: '', port: 554, username: '',
  password: '', rtsp_url: '', type: 'IP', zone: '',
};

export default function CamerasPage() {
  const [cameras, setCameras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterSite, setFilterSite] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterType, setFilterType] = useState('');
  const [showAdd, setShowAdd] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [showDetail, setShowDetail] = useState(false);
  const [showDelete, setShowDelete] = useState(false);
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [globalFilter, setGlobalFilter] = useState('');

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    try {
      const res = await camerasAPI.getAll();
      setCameras(res.data?.items || res.data || MOCK_CAMERAS);
    } catch {
      setCameras(MOCK_CAMERAS);
    } finally { setLoading(false); }
  }

  const filtered = useMemo(() => cameras.filter((c) => {
    if (filterSite && c.site !== filterSite) return false;
    if (filterStatus && c.status?.toLowerCase() !== filterStatus) return false;
    if (filterType && c.type !== filterType) return false;
    return true;
  }), [cameras, filterSite, filterStatus, filterType]);

  async function handleSave() {
    setSaving(true);
    try {
      if (showEdit) {
        await camerasAPI.update(selected.id, form);
        toast.success('Camera updated');
      } else {
        await camerasAPI.create(form);
        toast.success('Camera added');
      }
      setShowAdd(false); setShowEdit(false);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to save camera');
    } finally { setSaving(false); }
  }

  async function handleDelete() {
    try {
      await camerasAPI.delete(selected.id);
      toast.success('Camera deleted');
      setShowDelete(false);
      load();
    } catch { toast.error('Failed to delete camera'); }
  }

  async function handleRestart(cam) {
    try {
      await camerasAPI.restartStream(cam.id);
      toast.success(`Stream restarted for ${cam.name}`);
    } catch { toast.error('Failed to restart stream'); }
  }

  const columns = useMemo(() => [
    colHelper.accessor('name', {
      header: 'Name',
      cell: (i) => <span className="text-white fw-medium">{i.getValue()}</span>,
    }),
    colHelper.accessor('site', { header: 'Site' }),
    colHelper.accessor('status', {
      header: 'Status',
      cell: (i) => <StatusBadge status={i.getValue()} />,
    }),
    colHelper.accessor('ip_address', { header: 'IP Address' }),
    colHelper.accessor('type', { header: 'Type' }),
    colHelper.accessor('fps', {
      header: 'FPS',
      cell: (i) => <span style={{ color: (i.getValue() || 0) < 10 ? '#d29922' : '#3fb950' }}>{i.getValue() || '—'}</span>,
    }),
    colHelper.accessor('last_heartbeat', {
      header: 'Last Heartbeat',
      cell: (i) => i.getValue()
        ? <span className="text-muted" style={{ fontSize: 12 }}>{new Date(i.getValue()).toLocaleTimeString()}</span>
        : <span className="text-muted">—</span>,
    }),
    colHelper.display({
      id: 'actions',
      header: 'Actions',
      cell: ({ row }) => {
        const cam = row.original;
        return (
          <div className="d-flex gap-1">
            <button className="btn btn-sm btn-outline-secondary py-1 px-2" title="Details"
              onClick={() => { setSelected(cam); setShowDetail(true); }}>
              <RiHeartPulseLine size={13} />
            </button>
            <button className="btn btn-sm btn-outline-primary py-1 px-2" title="Edit"
              onClick={() => { setSelected(cam); setForm({ ...cam }); setShowEdit(true); }}>
              <RiEditLine size={13} />
            </button>
            <button className="btn btn-sm btn-outline-warning py-1 px-2" title="Restart Stream"
              onClick={() => handleRestart(cam)}>
              <RiRestartLine size={13} />
            </button>
            <button className="btn btn-sm btn-outline-danger py-1 px-2" title="Delete"
              onClick={() => { setSelected(cam); setShowDelete(true); }}>
              <RiDeleteBinLine size={13} />
            </button>
          </div>
        );
      },
    }),
  ], []);

  const FilterBar = (
    <div className="d-flex gap-2 flex-wrap">
      <select className="form-select form-select-sm" value={filterSite} onChange={(e) => setFilterSite(e.target.value)}
        style={{ background: '#0d1117', border: '1px solid #30363d', color: '#e6edf3', width: 'auto' }}>
        <option value="">All Sites</option>
        {SITES.map((s) => <option key={s}>{s}</option>)}
      </select>
      <select className="form-select form-select-sm" value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}
        style={{ background: '#0d1117', border: '1px solid #30363d', color: '#e6edf3', width: 'auto' }}>
        <option value="">All Status</option>
        {['online', 'offline', 'degraded', 'error'].map((s) => <option key={s}>{s}</option>)}
      </select>
      <select className="form-select form-select-sm" value={filterType} onChange={(e) => setFilterType(e.target.value)}
        style={{ background: '#0d1117', border: '1px solid #30363d', color: '#e6edf3', width: 'auto' }}>
        <option value="">All Types</option>
        {CAMERA_TYPES.map((t) => <option key={t}>{t}</option>)}
      </select>
    </div>
  );

  return (
    <div>
      <div className="d-flex align-items-center justify-content-between mb-3">
        <h4 className="text-white fw-semibold mb-0">Cameras</h4>
        <button className="btn btn-primary btn-sm d-flex align-items-center gap-1"
          onClick={() => { setForm(EMPTY_FORM); setShowAdd(true); }}>
          <RiAddLine size={16} /> Add Camera
        </button>
      </div>

      <div className="card" style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 10 }}>
        <div className="card-body">
          <DataTable
            data={filtered} columns={columns} loading={loading}
            globalFilter={globalFilter} onGlobalFilterChange={setGlobalFilter}
            extra={FilterBar}
          />
        </div>
      </div>

      {/* Add/Edit Modal */}
      <Modal
        show={showAdd || showEdit}
        onHide={() => { setShowAdd(false); setShowEdit(false); }}
        title={showEdit ? 'Edit Camera' : 'Add Camera'}
        size="lg"
        footer={
          <>
            <button className="btn btn-secondary btn-sm" onClick={() => { setShowAdd(false); setShowEdit(false); }}>Cancel</button>
            <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
              {saving ? 'Saving…' : showEdit ? 'Save Changes' : 'Add Camera'}
            </button>
          </>
        }
      >
        <div className="row g-3">
          {[
            { label: 'Camera Name', key: 'name', type: 'text', required: true },
            { label: 'IP Address', key: 'ip_address', type: 'text' },
          ].map(({ label, key, type, required }) => (
            <div key={key} className="col-md-6">
              <label className="form-label text-muted" style={{ fontSize: 13 }}>{label}</label>
              <input type={type} className="form-control form-control-sm"
                style={{ background: '#0d1117', border: '1px solid #30363d', color: '#e6edf3' }}
                value={form[key] || ''} required={required}
                onChange={(e) => setForm((p) => ({ ...p, [key]: e.target.value }))} />
            </div>
          ))}
          <div className="col-md-6">
            <label className="form-label text-muted" style={{ fontSize: 13 }}>Site</label>
            <select className="form-select form-select-sm"
              style={{ background: '#0d1117', border: '1px solid #30363d', color: '#e6edf3' }}
              value={form.site || ''} onChange={(e) => setForm((p) => ({ ...p, site: e.target.value }))}>
              <option value="">Select site…</option>
              {SITES.map((s) => <option key={s}>{s}</option>)}
            </select>
          </div>
          <div className="col-md-6">
            <label className="form-label text-muted" style={{ fontSize: 13 }}>Type</label>
            <select className="form-select form-select-sm"
              style={{ background: '#0d1117', border: '1px solid #30363d', color: '#e6edf3' }}
              value={form.type || 'IP'} onChange={(e) => setForm((p) => ({ ...p, type: e.target.value }))}>
              {CAMERA_TYPES.map((t) => <option key={t}>{t}</option>)}
            </select>
          </div>
          <div className="col-12">
            <label className="form-label text-muted" style={{ fontSize: 13 }}>RTSP URL</label>
            <input type="text" className="form-control form-control-sm"
              style={{ background: '#0d1117', border: '1px solid #30363d', color: '#e6edf3' }}
              placeholder="rtsp://user:pass@ip:554/stream" value={form.rtsp_url || ''}
              onChange={(e) => setForm((p) => ({ ...p, rtsp_url: e.target.value }))} />
          </div>
          {[
            { label: 'Username', key: 'username' },
            { label: 'Password', key: 'password', type: 'password' },
            { label: 'Zone', key: 'zone' },
          ].map(({ label, key, type = 'text' }) => (
            <div key={key} className="col-md-6">
              <label className="form-label text-muted" style={{ fontSize: 13 }}>{label}</label>
              <input type={type} className="form-control form-control-sm"
                style={{ background: '#0d1117', border: '1px solid #30363d', color: '#e6edf3' }}
                value={form[key] || ''}
                onChange={(e) => setForm((p) => ({ ...p, [key]: e.target.value }))} />
            </div>
          ))}
        </div>
      </Modal>

      {/* Delete confirm */}
      <Modal show={showDelete} onHide={() => setShowDelete(false)} title="Delete Camera" size="sm"
        footer={
          <>
            <button className="btn btn-secondary btn-sm" onClick={() => setShowDelete(false)}>Cancel</button>
            <button className="btn btn-danger btn-sm" onClick={handleDelete}>Delete</button>
          </>
        }>
        <p className="text-white mb-0">Are you sure you want to delete <strong>{selected?.name}</strong>? This action cannot be undone.</p>
      </Modal>

      {/* Detail modal */}
      <Modal show={showDetail} onHide={() => setShowDetail(false)} title="Camera Details" size="md">
        {selected && (
          <div className="row g-2" style={{ fontSize: 13 }}>
            {[
              ['Name', selected.name], ['Site', selected.site], ['IP', selected.ip_address],
              ['Type', selected.type], ['Zone', selected.zone || '—'],
              ['Status', <StatusBadge status={selected.status} />],
              ['FPS', selected.fps || '—'], ['Detections', selected.detections ?? '—'],
              ['Last Heartbeat', selected.last_heartbeat ? new Date(selected.last_heartbeat).toLocaleString() : '—'],
              ['RTSP URL', selected.rtsp_url || '—'],
            ].map(([k, v]) => (
              <div key={k} className="col-6">
                <div className="text-muted mb-1">{k}</div>
                <div className="text-white">{v}</div>
              </div>
            ))}
          </div>
        )}
      </Modal>
    </div>
  );
}

const MOCK_CAMERAS = [
  { id: 1, name: 'Main Entrance', site: 'Main Campus', status: 'online', ip_address: '192.168.1.101', type: 'RTSP', fps: 25, detections: 3, last_heartbeat: new Date().toISOString(), zone: 'Entry' },
  { id: 2, name: 'Parking A', site: 'Main Campus', status: 'online', ip_address: '192.168.1.102', type: 'IP', fps: 20, detections: 1, last_heartbeat: new Date().toISOString(), zone: 'Parking' },
  { id: 3, name: 'Lobby', site: 'Main Campus', status: 'degraded', ip_address: '192.168.1.103', type: 'RTSP', fps: 12, detections: 0, last_heartbeat: new Date().toISOString(), zone: 'Lobby' },
  { id: 4, name: 'Server Room', site: 'Main Campus', status: 'online', ip_address: '192.168.1.104', type: 'IP', fps: 25, detections: 0, last_heartbeat: new Date().toISOString(), zone: 'Restricted' },
  { id: 5, name: 'Cafeteria', site: 'Main Campus', status: 'offline', ip_address: '192.168.1.105', type: 'RTSP', fps: 0, detections: 0, last_heartbeat: null, zone: 'Common' },
  { id: 6, name: 'Branch A Entrance', site: 'Branch A', status: 'online', ip_address: '10.0.1.101', type: 'NVR', fps: 25, detections: 2, last_heartbeat: new Date().toISOString(), zone: 'Entry' },
];
