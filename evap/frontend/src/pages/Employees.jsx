import React, {
  useState, useEffect, useRef, useCallback, useMemo,
} from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import {
  RiAddLine, RiEditLine, RiDeleteBinLine, RiEyeLine,
  RiTeamLine, RiCheckboxCircleLine, RiCloseCircleLine,
  RiTimeLine, RiUploadCloud2Line, RiCloseLine,
} from 'react-icons/ri';
import { employeesAPI } from '../services/api';
import api from '../services/api';

/* ─────────────────────────── constants ──────────────────────────── */
const DEPARTMENTS = [
  'Engineering', 'HR', 'Finance', 'Operations',
  'Sales', 'R&D', 'Security', 'IT', 'Admin', 'Legal',
];

const ENROLLMENT_STATUSES = ['not_started', 'pending', 'enrolled', 'failed'];

const PAGE_SIZE = 20;

const FIELD = {
  background: '#0d1117',
  border: '1px solid #30363d',
  color: '#e6edf3',
  borderRadius: 6,
};

const EMPTY_FORM = {
  employee_id: '',
  full_name: '',
  department: '',
  designation: '',
  employee_code: '',
  email: '',
  phone: '',
  work_start_time: '',
  work_end_time: '',
  notes: '',
};

/* ───────────────────── tiny helpers / sub-renders ───────────────── */
function StatusPill({ status }) {
  const map = {
    active:   { bg: 'rgba(63,185,80,0.15)',  color: '#3fb950', label: 'Active' },
    inactive: { bg: 'rgba(210,153,34,0.15)', color: '#d29922', label: 'Inactive' },
    deleted:  { bg: 'rgba(248,81,73,0.15)',  color: '#f85149', label: 'Deleted' },
  };
  const s = map[status] || map.inactive;
  return (
    <span style={{
      background: s.bg, color: s.color,
      fontSize: 11, fontWeight: 600, padding: '2px 8px',
      borderRadius: 12, display: 'inline-block',
    }}>{s.label}</span>
  );
}

function EnrollBadge({ status }) {
  const map = {
    enrolled:    { color: '#3fb950', label: 'Enrolled',     blink: false },
    pending:     { color: '#d29922', label: 'Pending',      blink: true  },
    failed:      { color: '#f85149', label: 'Failed',       blink: false },
    not_started: { color: '#8b949e', label: 'Not Started',  blink: false },
  };
  const s = map[status] || map.not_started;
  return (
    <span style={{
      color: s.color, fontSize: 11, fontWeight: 600,
      padding: '2px 8px', borderRadius: 12,
      background: `${s.color}22`, display: 'inline-block',
      animation: s.blink ? 'blink 1.4s ease-in-out infinite' : 'none',
    }}>{s.label}</span>
  );
}

/* ─────────────────────── Step progress bar ─────────────────────── */
function StepBar({ step }) {
  const steps = ['Details', 'Photos', 'Enroll'];
  return (
    <div className="d-flex align-items-center justify-content-center mb-3" style={{ gap: 0 }}>
      {steps.map((label, i) => {
        const idx = i + 1;
        const active = step === idx;
        const done   = step > idx;
        const color  = done ? '#3fb950' : active ? '#58a6ff' : '#30363d';
        const textColor = done || active ? '#e6edf3' : '#8b949e';
        return (
          <React.Fragment key={label}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', minWidth: 72 }}>
              <div style={{
                width: 28, height: 28, borderRadius: '50%',
                background: done ? '#3fb950' : active ? '#58a6ff' : '#21262d',
                border: `2px solid ${color}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 12, fontWeight: 700, color: done || active ? '#fff' : '#8b949e',
              }}>
                {done ? '✓' : idx}
              </div>
              <div style={{ fontSize: 11, marginTop: 3, color: textColor, fontWeight: active ? 600 : 400 }}>
                {label}
              </div>
            </div>
            {i < steps.length - 1 && (
              <div style={{
                flex: 1, height: 2,
                background: step > idx ? '#3fb950' : '#30363d',
                marginBottom: 16, minWidth: 24,
              }} />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

/* ═══════════════════════ Main Page Component ═══════════════════════ */
export default function EmployeesPage() {
  const navigate = useNavigate();

  /* ── list state ── */
  const [employees, setEmployees]   = useState([]);
  const [total, setTotal]           = useState(0);
  const [loading, setLoading]       = useState(true);
  const [page, setPage]             = useState(0);          // 0-based
  const [searchRaw, setSearchRaw]   = useState('');
  const [search, setSearch]         = useState('');
  const [filterDept, setFilterDept] = useState('');
  const [filterEnroll, setFilterEnroll] = useState('');

  /* ── modal state ── */
  const [modalOpen, setModalOpen]   = useState(false);      // add-employee 3-step
  const [editOpen, setEditOpen]     = useState(false);      // edit modal
  const [step, setStep]             = useState(1);

  /* ── created employee (steps 2-3) ── */
  const [createdEmp, setCreatedEmp] = useState(null);

  /* ── step 1 form ── */
  const [form, setForm]             = useState(EMPTY_FORM);
  const [formErrors, setFormErrors] = useState({});
  const [step1Saving, setStep1Saving] = useState(false);

  /* ── step 2 photos ── */
  const [photoFiles, setPhotoFiles] = useState([]);         // File[]
  const [photoPreviews, setPhotoPreviews] = useState([]);   // { url, name }[]
  const [uploadedCount, setUploadedCount] = useState(0);
  const [uploading, setUploading]   = useState(false);
  const [dragOver, setDragOver]     = useState(false);
  const fileInputRef                = useRef(null);

  /* ── step 3 enrollment ── */
  const [enrolling, setEnrolling]   = useState(false);
  const [enrollStatus, setEnrollStatus] = useState(null);   // 'pending'|'enrolled'|'failed'|null
  const [enrollError, setEnrollError]   = useState('');
  const [enrollEmbeddings, setEnrollEmbeddings] = useState(0);
  const pollRef                     = useRef(null);

  /* ── edit modal form ── */
  const [editTarget, setEditTarget] = useState(null);
  const [editForm, setEditForm]     = useState(EMPTY_FORM);
  const [editSaving, setEditSaving] = useState(false);

  /* ── deactivate confirm ── */
  const [deactivateTarget, setDeactivateTarget] = useState(null);

  /* ─── debounce search ─── */
  useEffect(() => {
    const t = setTimeout(() => { setSearch(searchRaw); setPage(0); }, 400);
    return () => clearTimeout(t);
  }, [searchRaw]);

  /* ─── load list ─── */
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {
        skip: page * PAGE_SIZE,
        limit: PAGE_SIZE,
        ...(filterDept   ? { department: filterDept }               : {}),
        ...(filterEnroll ? { enrollment_status: filterEnroll }      : {}),
        ...(search       ? { q: search }                            : {}),
      };
      const res = await employeesAPI.getAll(params);
      const data = res.data;
      if (Array.isArray(data)) {
        setEmployees(data);
        setTotal(data.length);
      } else {
        setEmployees(data?.items || []);
        setTotal(data?.total ?? data?.items?.length ?? 0);
      }
    } catch {
      setEmployees([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [page, search, filterDept, filterEnroll]);

  useEffect(() => { load(); }, [load]);

  /* ─── client-side stats ─── */
  const stats = useMemo(() => {
    const enrolled    = employees.filter(e => e.enrollment_status === 'enrolled').length;
    const pending     = employees.filter(e => e.enrollment_status === 'pending').length;
    const not_started = employees.filter(e => e.enrollment_status === 'not_started').length;
    return { total: employees.length, enrolled, pending, not_started };
  }, [employees]);

  /* ─── stop poll on unmount ─── */
  useEffect(() => () => clearInterval(pollRef.current), []);

  /* ══════════════════ Add modal helpers ═══════════════════ */
  function openAddModal() {
    setForm(EMPTY_FORM);
    setFormErrors({});
    setStep(1);
    setCreatedEmp(null);
    setPhotoFiles([]);
    setPhotoPreviews([]);
    setUploadedCount(0);
    setEnrollStatus(null);
    setEnrollError('');
    setEnrollEmbeddings(0);
    clearInterval(pollRef.current);
    setModalOpen(true);
  }

  function closeAddModal() {
    clearInterval(pollRef.current);
    setModalOpen(false);
    load();
  }

  /* ── step 1: create ── */
  async function handleStep1Next() {
    const errs = {};
    if (!form.employee_id.trim()) errs.employee_id = 'Employee ID is required';
    if (!form.full_name.trim())   errs.full_name   = 'Full Name is required';
    if (Object.keys(errs).length) { setFormErrors(errs); return; }
    setFormErrors({});
    setStep1Saving(true);
    try {
      const payload = {};
      Object.keys(EMPTY_FORM).forEach(k => { if (form[k]) payload[k] = form[k]; });
      const res = await employeesAPI.create(payload);
      setCreatedEmp(res.data);
      toast.success('Employee created');
      setStep(2);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : 'Failed to create employee';
      if (msg.toLowerCase().includes('already exists') || msg.toLowerCase().includes('duplicate')) {
        setFormErrors({ employee_id: 'Employee ID already exists' });
      } else {
        toast.error(msg);
      }
    } finally {
      setStep1Saving(false);
    }
  }

  /* ── step 2: photos ── */
  function addFiles(files) {
    const valid = Array.from(files).filter(f =>
      f.type === 'image/jpeg' || f.type === 'image/png' || f.type === 'image/jpg'
    );
    if (!valid.length) { toast.error('Only JPG/PNG files accepted'); return; }
    const newFiles    = [...photoFiles, ...valid];
    const newPreviews = [...photoPreviews];
    valid.forEach(f => {
      const url = URL.createObjectURL(f);
      newPreviews.push({ url, name: f.name });
    });
    setPhotoFiles(newFiles);
    setPhotoPreviews(newPreviews);
  }

  function removePhoto(idx) {
    URL.revokeObjectURL(photoPreviews[idx]?.url);
    setPhotoFiles(prev => prev.filter((_, i) => i !== idx));
    setPhotoPreviews(prev => prev.filter((_, i) => i !== idx));
  }

  async function handleUploadPhotos() {
    if (!photoFiles.length || !createdEmp) return;
    setUploading(true);
    try {
      const fd = new FormData();
      photoFiles.forEach(f => fd.append('files', f));
      await api.post(`/employees/${createdEmp.employee_id}/photos`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setUploadedCount(photoFiles.length);
      toast.success(`${photoFiles.length} photo(s) uploaded`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Photo upload failed');
    } finally {
      setUploading(false);
    }
  }

  /* ── step 3: enrollment ── */
  async function handleStartEnrollment() {
    if (!createdEmp) return;
    setEnrolling(true);
    setEnrollStatus('pending');
    setEnrollError('');
    try {
      await api.post(`/employees/${createdEmp.employee_id}/enroll`);
      pollRef.current = setInterval(async () => {
        try {
          const r = await api.get(`/employees/${createdEmp.employee_id}/enrollment-status`);
          const s = r.data?.enrollment_status || r.data?.status;
          if (s === 'enrolled') {
            clearInterval(pollRef.current);
            setEnrollStatus('enrolled');
            setEnrollEmbeddings(r.data?.embedding_count ?? r.data?.photo_count ?? 0);
            setEnrolling(false);
          } else if (s === 'failed') {
            clearInterval(pollRef.current);
            setEnrollStatus('failed');
            setEnrollError(r.data?.enrollment_error || 'Enrollment failed');
            setEnrolling(false);
          }
        } catch { /* keep polling */ }
      }, 3000);
    } catch (e) {
      setEnrollStatus('failed');
      setEnrollError(e?.response?.data?.detail || 'Failed to start enrollment');
      setEnrolling(false);
    }
  }

  /* ══════════════════ Edit modal helpers ═══════════════════ */
  function openEdit(emp) {
    setEditTarget(emp);
    setEditForm({
      employee_id:     emp.employee_id    || '',
      full_name:       emp.full_name      || '',
      department:      emp.department     || '',
      designation:     emp.designation    || '',
      employee_code:   emp.employee_code  || '',
      email:           emp.email          || '',
      phone:           emp.phone          || '',
      work_start_time: emp.work_start_time || '',
      work_end_time:   emp.work_end_time  || '',
      notes:           emp.notes          || '',
    });
    setEditOpen(true);
  }

  async function handleEditSave() {
    if (!editTarget) return;
    setEditSaving(true);
    try {
      const payload = {};
      Object.keys(EMPTY_FORM).forEach(k => {
        if (k !== 'employee_id') payload[k] = editForm[k] || null;
      });
      await employeesAPI.update(editTarget.employee_id, payload);
      toast.success('Employee updated');
      setEditOpen(false);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to update employee');
    } finally {
      setEditSaving(false);
    }
  }

  /* ══════════════════ Deactivate (soft-delete) ═════════════ */
  async function handleDeactivate() {
    if (!deactivateTarget) return;
    try {
      await employeesAPI.delete(deactivateTarget.employee_id);
      toast.success(`${deactivateTarget.full_name} deactivated`);
      setDeactivateTarget(null);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to deactivate employee');
    }
  }

  /* ══════════════════════ Pagination ═══════════════════════ */
  const totalPages   = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const displayStart = page * PAGE_SIZE + 1;
  const displayEnd   = Math.min((page + 1) * PAGE_SIZE, total);

  /* ══════════════════════ Render ═══════════════════════════ */
  return (
    <div>
      {/* blink keyframe */}
      <style>{`
        @keyframes blink {
          0%,100% { opacity: 1; }
          50%      { opacity: 0.35; }
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
      `}</style>

      {/* ── header ── */}
      <div className="d-flex align-items-center justify-content-between mb-3">
        <h4 className="text-white fw-semibold mb-0">Employees</h4>
        <button
          className="btn btn-primary btn-sm d-flex align-items-center gap-1"
          onClick={openAddModal}
        >
          <RiAddLine size={16} /> Add Employee
        </button>
      </div>

      {/* ── stats row ── */}
      <div className="row g-2 mb-3">
        {[
          { label: 'Total',       value: stats.total,       color: '#58a6ff' },
          { label: 'Enrolled',    value: stats.enrolled,    color: '#3fb950' },
          { label: 'Pending',     value: stats.pending,     color: '#d29922' },
          { label: 'Not Enrolled',value: stats.not_started, color: '#8b949e' },
        ].map(({ label, value, color }) => (
          <div key={label} className="col-6 col-md-3">
            <div style={{
              background: '#161b22', border: '1px solid #30363d',
              borderRadius: 8, padding: '10px 14px',
            }}>
              <div style={{ fontSize: 11, color: '#8b949e' }}>{label}</div>
              <div style={{ fontSize: 22, fontWeight: 700, color }}>{value}</div>
            </div>
          </div>
        ))}
      </div>

      {/* ── filter bar ── */}
      <div className="d-flex gap-2 mb-3 flex-wrap">
        <input
          type="text"
          className="form-control form-control-sm"
          placeholder="Search employees…"
          value={searchRaw}
          onChange={e => setSearchRaw(e.target.value)}
          style={{ ...FIELD, maxWidth: 260 }}
        />
        <select
          className="form-select form-select-sm"
          value={filterDept}
          onChange={e => { setFilterDept(e.target.value); setPage(0); }}
          style={{ ...FIELD, width: 'auto' }}
        >
          <option value="">All Departments</option>
          {DEPARTMENTS.map(d => <option key={d} value={d}>{d}</option>)}
        </select>
        <select
          className="form-select form-select-sm"
          value={filterEnroll}
          onChange={e => { setFilterEnroll(e.target.value); setPage(0); }}
          style={{ ...FIELD, width: 'auto' }}
        >
          <option value="">All Enrollment</option>
          {ENROLLMENT_STATUSES.map(s => (
            <option key={s} value={s}>{s.replace('_', ' ')}</option>
          ))}
        </select>
      </div>

      {/* ── table card ── */}
      <div style={{
        background: '#161b22', border: '1px solid #30363d',
        borderRadius: 10, overflow: 'hidden',
      }}>
        {loading ? (
          <div className="text-center py-5" style={{ color: '#8b949e' }}>
            <div className="spinner-border spinner-border-sm text-primary me-2" role="status" />
            Loading employees…
          </div>
        ) : employees.length === 0 ? (
          <div className="text-center py-5" style={{ color: '#8b949e' }}>
            <RiTeamLine size={48} style={{ opacity: 0.25 }} />
            <div className="mt-2" style={{ fontSize: 14 }}>No employees found</div>
            <div style={{ fontSize: 12, marginTop: 4 }}>
              {search || filterDept || filterEnroll
                ? 'Try adjusting your filters'
                : 'Click "+ Add Employee" to get started'}
            </div>
          </div>
        ) : (
          <div className="table-responsive">
            <table className="table table-hover mb-0" style={{ color: '#e6edf3', fontSize: 13 }}>
              <thead style={{ background: '#0d1117', color: '#8b949e', fontSize: 11 }}>
                <tr>
                  <th style={{ padding: '10px 16px', fontWeight: 600, borderColor: '#21262d' }}>Employee ID</th>
                  <th style={{ padding: '10px 16px', fontWeight: 600, borderColor: '#21262d' }}>Name</th>
                  <th style={{ padding: '10px 16px', fontWeight: 600, borderColor: '#21262d' }}>Department</th>
                  <th style={{ padding: '10px 16px', fontWeight: 600, borderColor: '#21262d' }}>Designation</th>
                  <th style={{ padding: '10px 16px', fontWeight: 600, borderColor: '#21262d' }}>Status</th>
                  <th style={{ padding: '10px 16px', fontWeight: 600, borderColor: '#21262d' }}>Enrollment</th>
                  <th style={{ padding: '10px 16px', fontWeight: 600, borderColor: '#21262d' }}>Photos</th>
                  <th style={{ padding: '10px 16px', fontWeight: 600, borderColor: '#21262d' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {employees.map(emp => (
                  <tr key={emp.employee_id} style={{ borderColor: '#21262d' }}>
                    <td style={{ padding: '10px 16px', borderColor: '#21262d', verticalAlign: 'middle' }}>
                      <span style={{ color: '#58a6ff', fontFamily: 'monospace', fontSize: 12 }}>
                        {emp.employee_id}
                      </span>
                    </td>
                    <td style={{ padding: '10px 16px', borderColor: '#21262d', verticalAlign: 'middle' }}>
                      <span className="fw-medium">{emp.full_name}</span>
                    </td>
                    <td style={{ padding: '10px 16px', borderColor: '#21262d', verticalAlign: 'middle', color: '#8b949e' }}>
                      {emp.department || '—'}
                    </td>
                    <td style={{ padding: '10px 16px', borderColor: '#21262d', verticalAlign: 'middle', color: '#8b949e' }}>
                      {emp.designation || '—'}
                    </td>
                    <td style={{ padding: '10px 16px', borderColor: '#21262d', verticalAlign: 'middle' }}>
                      <StatusPill status={emp.status} />
                    </td>
                    <td style={{ padding: '10px 16px', borderColor: '#21262d', verticalAlign: 'middle' }}>
                      <EnrollBadge status={emp.enrollment_status} />
                    </td>
                    <td style={{ padding: '10px 16px', borderColor: '#21262d', verticalAlign: 'middle', color: '#8b949e' }}>
                      {emp.photo_count ?? 0}
                    </td>
                    <td style={{ padding: '10px 16px', borderColor: '#21262d', verticalAlign: 'middle' }}>
                      <div className="d-flex gap-1">
                        <button
                          className="btn btn-sm py-1 px-2"
                          title="View"
                          style={{ background: 'rgba(88,166,255,0.1)', border: '1px solid #30363d', color: '#58a6ff' }}
                          onClick={() => navigate(`/employees/${emp.employee_id}`)}
                        >
                          <RiEyeLine size={13} />
                        </button>
                        <button
                          className="btn btn-sm py-1 px-2"
                          title="Edit"
                          style={{ background: 'rgba(88,166,255,0.08)', border: '1px solid #30363d', color: '#8b949e' }}
                          onClick={() => openEdit(emp)}
                        >
                          <RiEditLine size={13} />
                        </button>
                        <button
                          className="btn btn-sm py-1 px-2"
                          title="Deactivate"
                          style={{ background: 'rgba(248,81,73,0.08)', border: '1px solid #30363d', color: '#f85149' }}
                          onClick={() => setDeactivateTarget(emp)}
                          disabled={emp.status === 'deleted'}
                        >
                          <RiDeleteBinLine size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* ── pagination ── */}
        {!loading && total > 0 && (
          <div
            className="d-flex align-items-center justify-content-between px-3 py-2"
            style={{ borderTop: '1px solid #21262d', fontSize: 12, color: '#8b949e' }}
          >
            <span>{displayStart}–{displayEnd} of {total}</span>
            <div className="d-flex gap-1">
              <button
                className="btn btn-sm"
                style={{ ...FIELD, fontSize: 12, padding: '2px 10px' }}
                disabled={page === 0}
                onClick={() => setPage(p => p - 1)}
              >
                ← Prev
              </button>
              <button
                className="btn btn-sm"
                style={{ ...FIELD, fontSize: 12, padding: '2px 10px' }}
                disabled={page >= totalPages - 1}
                onClick={() => setPage(p => p + 1)}
              >
                Next →
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ════════════════ 3-Step Add Modal ════════════════ */}
      {modalOpen && (
        <div
          className="modal show d-block"
          style={{ background: 'rgba(0,0,0,0.75)', zIndex: 1050 }}
          onClick={e => { if (e.target === e.currentTarget) closeAddModal(); }}
        >
          <div className="modal-dialog modal-lg modal-dialog-centered modal-dialog-scrollable">
            <div className="modal-content" style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 12 }}>

              {/* header */}
              <div className="modal-header" style={{ borderColor: '#30363d' }}>
                <h5 className="modal-title text-white" style={{ fontSize: 15 }}>Add Employee</h5>
                <button
                  className="btn-close btn-close-white btn-sm"
                  onClick={closeAddModal}
                  disabled={step === 3 && enrollStatus === 'pending'}
                />
              </div>

              <div className="modal-body">
                <StepBar step={step} />

                {/* ─── Step 1: Details ─── */}
                {step === 1 && (
                  <div className="row g-3">
                    {/* Employee ID */}
                    <div className="col-md-6">
                      <label className="form-label text-muted" style={{ fontSize: 12 }}>
                        Employee ID <span style={{ color: '#f85149' }}>*</span>
                      </label>
                      <input
                        className="form-control form-control-sm"
                        style={{ ...FIELD, borderColor: formErrors.employee_id ? '#f85149' : '#30363d' }}
                        value={form.employee_id}
                        onChange={e => setForm(p => ({ ...p, employee_id: e.target.value }))}
                        placeholder="e.g. EMP001"
                      />
                      {formErrors.employee_id && (
                        <div style={{ color: '#f85149', fontSize: 11, marginTop: 3 }}>
                          {formErrors.employee_id}
                        </div>
                      )}
                    </div>
                    {/* Full Name */}
                    <div className="col-md-6">
                      <label className="form-label text-muted" style={{ fontSize: 12 }}>
                        Full Name <span style={{ color: '#f85149' }}>*</span>
                      </label>
                      <input
                        className="form-control form-control-sm"
                        style={{ ...FIELD, borderColor: formErrors.full_name ? '#f85149' : '#30363d' }}
                        value={form.full_name}
                        onChange={e => setForm(p => ({ ...p, full_name: e.target.value }))}
                        placeholder="Jane Smith"
                      />
                      {formErrors.full_name && (
                        <div style={{ color: '#f85149', fontSize: 11, marginTop: 3 }}>
                          {formErrors.full_name}
                        </div>
                      )}
                    </div>
                    {/* Department */}
                    <div className="col-md-6">
                      <label className="form-label text-muted" style={{ fontSize: 12 }}>Department</label>
                      <select
                        className="form-select form-select-sm"
                        style={FIELD}
                        value={form.department}
                        onChange={e => setForm(p => ({ ...p, department: e.target.value }))}
                      >
                        <option value="">Select department…</option>
                        {DEPARTMENTS.map(d => <option key={d} value={d}>{d}</option>)}
                      </select>
                    </div>
                    {/* Designation */}
                    <div className="col-md-6">
                      <label className="form-label text-muted" style={{ fontSize: 12 }}>Designation</label>
                      <input
                        className="form-control form-control-sm"
                        style={FIELD}
                        value={form.designation}
                        onChange={e => setForm(p => ({ ...p, designation: e.target.value }))}
                        placeholder="e.g. Senior Engineer"
                      />
                    </div>
                    {/* Employee Code */}
                    <div className="col-md-6">
                      <label className="form-label text-muted" style={{ fontSize: 12 }}>Employee Code</label>
                      <input
                        className="form-control form-control-sm"
                        style={FIELD}
                        value={form.employee_code}
                        onChange={e => setForm(p => ({ ...p, employee_code: e.target.value }))}
                        placeholder="Internal code / badge number"
                      />
                    </div>
                    {/* Email */}
                    <div className="col-md-6">
                      <label className="form-label text-muted" style={{ fontSize: 12 }}>Email</label>
                      <input
                        type="email"
                        className="form-control form-control-sm"
                        style={FIELD}
                        value={form.email}
                        onChange={e => setForm(p => ({ ...p, email: e.target.value }))}
                        placeholder="jane@company.com"
                      />
                    </div>
                    {/* Phone */}
                    <div className="col-md-6">
                      <label className="form-label text-muted" style={{ fontSize: 12 }}>Phone</label>
                      <input
                        className="form-control form-control-sm"
                        style={FIELD}
                        value={form.phone}
                        onChange={e => setForm(p => ({ ...p, phone: e.target.value }))}
                        placeholder="+1 555 000 0000"
                      />
                    </div>
                    {/* Work Start */}
                    <div className="col-md-3">
                      <label className="form-label text-muted" style={{ fontSize: 12 }}>
                        <RiTimeLine size={11} className="me-1" />Work Start
                      </label>
                      <input
                        type="time"
                        className="form-control form-control-sm"
                        style={FIELD}
                        value={form.work_start_time}
                        onChange={e => setForm(p => ({ ...p, work_start_time: e.target.value }))}
                      />
                    </div>
                    {/* Work End */}
                    <div className="col-md-3">
                      <label className="form-label text-muted" style={{ fontSize: 12 }}>
                        <RiTimeLine size={11} className="me-1" />Work End
                      </label>
                      <input
                        type="time"
                        className="form-control form-control-sm"
                        style={FIELD}
                        value={form.work_end_time}
                        onChange={e => setForm(p => ({ ...p, work_end_time: e.target.value }))}
                      />
                    </div>
                    {/* Notes */}
                    <div className="col-12">
                      <label className="form-label text-muted" style={{ fontSize: 12 }}>Notes</label>
                      <textarea
                        className="form-control form-control-sm"
                        style={{ ...FIELD, resize: 'vertical', minHeight: 72 }}
                        rows={3}
                        value={form.notes}
                        onChange={e => setForm(p => ({ ...p, notes: e.target.value }))}
                        placeholder="Optional notes…"
                      />
                    </div>
                  </div>
                )}

                {/* ─── Step 2: Photos ─── */}
                {step === 2 && (
                  <div>
                    {/* mini employee info */}
                    <div
                      className="mb-3 p-2 rounded d-flex align-items-center gap-2"
                      style={{ background: '#0d1117', border: '1px solid #21262d' }}
                    >
                      <div style={{
                        width: 32, height: 32, borderRadius: '50%',
                        background: '#21262d', display: 'flex', alignItems: 'center',
                        justifyContent: 'center', color: '#58a6ff', fontSize: 13, fontWeight: 700,
                      }}>
                        {createdEmp?.full_name?.[0]?.toUpperCase() || '?'}
                      </div>
                      <div>
                        <div style={{ color: '#e6edf3', fontSize: 13, fontWeight: 600 }}>
                          {createdEmp?.full_name}
                        </div>
                        <div style={{ color: '#58a6ff', fontSize: 11, fontFamily: 'monospace' }}>
                          {createdEmp?.employee_id}
                        </div>
                      </div>
                      {uploadedCount > 0 && (
                        <span
                          className="ms-auto"
                          style={{ color: '#3fb950', fontSize: 12, fontWeight: 600 }}
                        >
                          ✓ {uploadedCount} photo{uploadedCount !== 1 ? 's' : ''} uploaded
                        </span>
                      )}
                    </div>

                    {/* drag-drop zone */}
                    <div
                      onClick={() => fileInputRef.current?.click()}
                      onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                      onDragLeave={() => setDragOver(false)}
                      onDrop={e => {
                        e.preventDefault();
                        setDragOver(false);
                        addFiles(e.dataTransfer.files);
                      }}
                      style={{
                        border: `2px dashed ${dragOver ? '#58a6ff' : '#30363d'}`,
                        borderRadius: 8,
                        background: dragOver ? 'rgba(88,166,255,0.05)' : '#0d1117',
                        padding: '28px 16px',
                        textAlign: 'center',
                        cursor: 'pointer',
                        transition: 'all 0.15s',
                        marginBottom: 12,
                      }}
                    >
                      <RiUploadCloud2Line size={32} color={dragOver ? '#58a6ff' : '#30363d'} />
                      <div style={{ color: '#8b949e', fontSize: 13, marginTop: 6 }}>
                        Drag &amp; drop photos here, or{' '}
                        <span style={{ color: '#58a6ff' }}>click to browse</span>
                      </div>
                      <div style={{ color: '#30363d', fontSize: 11, marginTop: 3 }}>
                        JPG / PNG — multiple files allowed
                      </div>
                    </div>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept="image/jpeg,image/png"
                      multiple
                      className="d-none"
                      onChange={e => addFiles(e.target.files)}
                    />

                    {/* thumbnails */}
                    {photoPreviews.length > 0 && (
                      <div className="d-flex flex-wrap gap-2 mb-3">
                        {photoPreviews.map((p, idx) => (
                          <div
                            key={idx}
                            style={{ position: 'relative', width: 90, height: 90 }}
                          >
                            <img
                              src={p.url}
                              alt={p.name}
                              style={{
                                width: 90, height: 90, objectFit: 'cover',
                                borderRadius: 6, border: '1px solid #30363d',
                              }}
                            />
                            <button
                              onClick={() => removePhoto(idx)}
                              style={{
                                position: 'absolute', top: 2, right: 2,
                                width: 18, height: 18, borderRadius: '50%',
                                background: 'rgba(248,81,73,0.85)', border: 'none',
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                cursor: 'pointer', padding: 0,
                              }}
                            >
                              <RiCloseLine size={11} color="#fff" />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* upload button */}
                    {photoFiles.length > 0 && uploadedCount === 0 && (
                      <button
                        className="btn btn-sm btn-outline-primary w-100"
                        onClick={handleUploadPhotos}
                        disabled={uploading}
                      >
                        {uploading
                          ? <><span className="spinner-border spinner-border-sm me-1" />Uploading…</>
                          : <><RiUploadCloud2Line size={14} className="me-1" />Upload {photoFiles.length} Photo{photoFiles.length !== 1 ? 's' : ''}</>
                        }
                      </button>
                    )}
                  </div>
                )}

                {/* ─── Step 3: Enrollment ─── */}
                {step === 3 && (
                  <div className="text-center py-2">
                    {/* employee summary */}
                    <div
                      className="mb-4 p-3 rounded d-inline-flex align-items-center gap-3 text-start"
                      style={{ background: '#0d1117', border: '1px solid #21262d', minWidth: 260 }}
                    >
                      <div style={{
                        width: 40, height: 40, borderRadius: '50%',
                        background: '#21262d', display: 'flex', alignItems: 'center',
                        justifyContent: 'center', color: '#58a6ff', fontSize: 15, fontWeight: 700,
                      }}>
                        {createdEmp?.full_name?.[0]?.toUpperCase() || '?'}
                      </div>
                      <div>
                        <div style={{ color: '#e6edf3', fontSize: 14, fontWeight: 600 }}>
                          {createdEmp?.full_name}
                        </div>
                        <div style={{ color: '#58a6ff', fontSize: 11, fontFamily: 'monospace' }}>
                          {createdEmp?.employee_id}
                        </div>
                        <div style={{ color: '#8b949e', fontSize: 11, marginTop: 2 }}>
                          {uploadedCount} photo{uploadedCount !== 1 ? 's' : ''} uploaded
                        </div>
                      </div>
                    </div>

                    {/* enrollment status display */}
                    {!enrollStatus && !enrolling && (
                      <>
                        <div style={{ color: '#8b949e', fontSize: 13, marginBottom: 16 }}>
                          Ready to generate face embeddings from the uploaded photos.
                        </div>
                        <button
                          className="btn btn-primary"
                          onClick={handleStartEnrollment}
                          disabled={uploadedCount === 0}
                        >
                          Start Enrollment
                        </button>
                        {uploadedCount === 0 && (
                          <div style={{ color: '#f85149', fontSize: 11, marginTop: 8 }}>
                            No photos uploaded — go back and upload at least one photo
                          </div>
                        )}
                      </>
                    )}

                    {enrollStatus === 'pending' && (
                      <div>
                        <div style={{
                          width: 48, height: 48, border: '3px solid #30363d',
                          borderTopColor: '#58a6ff', borderRadius: '50%',
                          animation: 'spin 0.9s linear infinite',
                          margin: '0 auto 12px',
                        }} />
                        <div style={{ color: '#58a6ff', fontWeight: 600 }}>Processing face embeddings…</div>
                        <div style={{ color: '#8b949e', fontSize: 12, marginTop: 4 }}>This may take a few seconds</div>
                      </div>
                    )}

                    {enrollStatus === 'enrolled' && (
                      <div>
                        <RiCheckboxCircleLine size={48} color="#3fb950" />
                        <div style={{ color: '#3fb950', fontWeight: 700, fontSize: 15, marginTop: 8 }}>
                          Enrolled successfully
                        </div>
                        {enrollEmbeddings > 0 && (
                          <div style={{ color: '#8b949e', fontSize: 12, marginTop: 4 }}>
                            {enrollEmbeddings} embedding{enrollEmbeddings !== 1 ? 's' : ''} generated
                          </div>
                        )}
                      </div>
                    )}

                    {enrollStatus === 'failed' && (
                      <div>
                        <RiCloseCircleLine size={48} color="#f85149" />
                        <div style={{ color: '#f85149', fontWeight: 700, fontSize: 15, marginTop: 8 }}>
                          Enrollment failed
                        </div>
                        <div style={{ color: '#8b949e', fontSize: 12, marginTop: 4 }}>
                          {enrollError || 'Unknown error during face embedding'}
                        </div>
                        <button
                          className="btn btn-sm btn-outline-danger mt-3"
                          onClick={() => { setEnrollStatus(null); setEnrolling(false); }}
                        >
                          Retry
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* footer */}
              <div className="modal-footer" style={{ borderColor: '#30363d', justifyContent: 'space-between' }}>
                {/* left: skip */}
                <div>
                  {step === 3 && enrollStatus !== 'enrolled' && (
                    <button
                      className="btn btn-link btn-sm"
                      style={{ color: '#8b949e', textDecoration: 'none' }}
                      onClick={closeAddModal}
                    >
                      Skip for now
                    </button>
                  )}
                </div>

                {/* right: nav buttons */}
                <div className="d-flex gap-2">
                  {step === 1 && (
                    <button className="btn btn-secondary btn-sm" onClick={closeAddModal}>
                      Cancel
                    </button>
                  )}
                  {step === 2 && (
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => setStep(1)}
                      disabled={uploading}
                    >
                      ← Back
                    </button>
                  )}

                  {step === 1 && (
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={handleStep1Next}
                      disabled={step1Saving}
                    >
                      {step1Saving
                        ? <><span className="spinner-border spinner-border-sm me-1" />Saving…</>
                        : 'Next →'
                      }
                    </button>
                  )}
                  {step === 2 && (
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={() => setStep(3)}
                      disabled={uploadedCount === 0}
                      title={uploadedCount === 0 ? 'Upload at least one photo first' : ''}
                    >
                      Next →
                    </button>
                  )}
                  {step === 3 && enrollStatus === 'enrolled' && (
                    <button className="btn btn-success btn-sm" onClick={closeAddModal}>
                      Done
                    </button>
                  )}
                </div>
              </div>

            </div>
          </div>
        </div>
      )}

      {/* ════════════════ Edit Modal ════════════════ */}
      {editOpen && editTarget && (
        <div
          className="modal show d-block"
          style={{ background: 'rgba(0,0,0,0.75)', zIndex: 1050 }}
          onClick={e => { if (e.target === e.currentTarget) setEditOpen(false); }}
        >
          <div className="modal-dialog modal-lg modal-dialog-centered modal-dialog-scrollable">
            <div className="modal-content" style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 12 }}>
              <div className="modal-header" style={{ borderColor: '#30363d' }}>
                <h5 className="modal-title text-white" style={{ fontSize: 15 }}>Edit Employee</h5>
                <button className="btn-close btn-close-white btn-sm" onClick={() => setEditOpen(false)} />
              </div>
              <div className="modal-body">
                <div className="row g-3">
                  {/* Employee ID — readonly */}
                  <div className="col-md-6">
                    <label className="form-label text-muted" style={{ fontSize: 12 }}>Employee ID</label>
                    <input
                      className="form-control form-control-sm"
                      style={{ ...FIELD, opacity: 0.55, cursor: 'not-allowed' }}
                      value={editForm.employee_id}
                      readOnly
                    />
                  </div>
                  {/* Full Name */}
                  <div className="col-md-6">
                    <label className="form-label text-muted" style={{ fontSize: 12 }}>
                      Full Name <span style={{ color: '#f85149' }}>*</span>
                    </label>
                    <input
                      className="form-control form-control-sm"
                      style={FIELD}
                      value={editForm.full_name}
                      onChange={e => setEditForm(p => ({ ...p, full_name: e.target.value }))}
                    />
                  </div>
                  {/* Department */}
                  <div className="col-md-6">
                    <label className="form-label text-muted" style={{ fontSize: 12 }}>Department</label>
                    <select
                      className="form-select form-select-sm"
                      style={FIELD}
                      value={editForm.department}
                      onChange={e => setEditForm(p => ({ ...p, department: e.target.value }))}
                    >
                      <option value="">Select department…</option>
                      {DEPARTMENTS.map(d => <option key={d} value={d}>{d}</option>)}
                    </select>
                  </div>
                  {/* Designation */}
                  <div className="col-md-6">
                    <label className="form-label text-muted" style={{ fontSize: 12 }}>Designation</label>
                    <input
                      className="form-control form-control-sm"
                      style={FIELD}
                      value={editForm.designation}
                      onChange={e => setEditForm(p => ({ ...p, designation: e.target.value }))}
                    />
                  </div>
                  {/* Employee Code */}
                  <div className="col-md-6">
                    <label className="form-label text-muted" style={{ fontSize: 12 }}>Employee Code</label>
                    <input
                      className="form-control form-control-sm"
                      style={FIELD}
                      value={editForm.employee_code}
                      onChange={e => setEditForm(p => ({ ...p, employee_code: e.target.value }))}
                    />
                  </div>
                  {/* Email */}
                  <div className="col-md-6">
                    <label className="form-label text-muted" style={{ fontSize: 12 }}>Email</label>
                    <input
                      type="email"
                      className="form-control form-control-sm"
                      style={FIELD}
                      value={editForm.email}
                      onChange={e => setEditForm(p => ({ ...p, email: e.target.value }))}
                    />
                  </div>
                  {/* Phone */}
                  <div className="col-md-6">
                    <label className="form-label text-muted" style={{ fontSize: 12 }}>Phone</label>
                    <input
                      className="form-control form-control-sm"
                      style={FIELD}
                      value={editForm.phone}
                      onChange={e => setEditForm(p => ({ ...p, phone: e.target.value }))}
                    />
                  </div>
                  {/* Work Start */}
                  <div className="col-md-3">
                    <label className="form-label text-muted" style={{ fontSize: 12 }}>Work Start</label>
                    <input
                      type="time"
                      className="form-control form-control-sm"
                      style={FIELD}
                      value={editForm.work_start_time}
                      onChange={e => setEditForm(p => ({ ...p, work_start_time: e.target.value }))}
                    />
                  </div>
                  {/* Work End */}
                  <div className="col-md-3">
                    <label className="form-label text-muted" style={{ fontSize: 12 }}>Work End</label>
                    <input
                      type="time"
                      className="form-control form-control-sm"
                      style={FIELD}
                      value={editForm.work_end_time}
                      onChange={e => setEditForm(p => ({ ...p, work_end_time: e.target.value }))}
                    />
                  </div>
                  {/* Notes */}
                  <div className="col-12">
                    <label className="form-label text-muted" style={{ fontSize: 12 }}>Notes</label>
                    <textarea
                      className="form-control form-control-sm"
                      style={{ ...FIELD, resize: 'vertical', minHeight: 72 }}
                      rows={3}
                      value={editForm.notes}
                      onChange={e => setEditForm(p => ({ ...p, notes: e.target.value }))}
                    />
                  </div>
                </div>
              </div>
              <div className="modal-footer" style={{ borderColor: '#30363d' }}>
                <button className="btn btn-secondary btn-sm" onClick={() => setEditOpen(false)}>
                  Cancel
                </button>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={handleEditSave}
                  disabled={editSaving}
                >
                  {editSaving
                    ? <><span className="spinner-border spinner-border-sm me-1" />Saving…</>
                    : 'Save Changes'
                  }
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ════════════════ Deactivate Confirm Modal ════════════════ */}
      {deactivateTarget && (
        <div
          className="modal show d-block"
          style={{ background: 'rgba(0,0,0,0.75)', zIndex: 1050 }}
          onClick={e => { if (e.target === e.currentTarget) setDeactivateTarget(null); }}
        >
          <div className="modal-dialog modal-sm modal-dialog-centered">
            <div className="modal-content" style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 12 }}>
              <div className="modal-header" style={{ borderColor: '#30363d' }}>
                <h5 className="modal-title text-white" style={{ fontSize: 15 }}>Deactivate Employee</h5>
              </div>
              <div className="modal-body">
                <p className="mb-1" style={{ color: '#e6edf3', fontSize: 14 }}>
                  Deactivate <strong>{deactivateTarget.full_name}</strong>?
                </p>
                <p className="mb-0" style={{ color: '#8b949e', fontSize: 12 }}>
                  The employee record will be soft-deleted and excluded from active operations.
                </p>
              </div>
              <div className="modal-footer" style={{ borderColor: '#30363d' }}>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => setDeactivateTarget(null)}
                >
                  Cancel
                </button>
                <button className="btn btn-danger btn-sm" onClick={handleDeactivate}>
                  Deactivate
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
