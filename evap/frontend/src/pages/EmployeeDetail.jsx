import React, { useEffect, useRef, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { format, parseISO, differenceInMinutes } from 'date-fns';
import {
  RiArrowLeftLine,
  RiEditLine,
  RiUserLine,
  RiMailLine,
  RiPhoneLine,
  RiBuildingLine,
  RiBriefcaseLine,
  RiIdCardLine,
  RiTimeLine,
  RiFileTextLine,
  RiCalendarLine,
  RiCheckboxCircleLine,
  RiCloseCircleLine,
  RiLoader4Line,
  RiRadioButtonLine,
  RiCameraLine,
  RiDeleteBinLine,
  RiAddLine,
  RiRefreshLine,
  RiUserUnfollowLine,
  RiDownloadLine,
  RiEyeLine,
} from 'react-icons/ri';
import { employeesAPI, attendanceAPI } from '../services/api';

/* ─── theme tokens ──────────────────────────────────────────────────────── */
const T = {
  bg: '#0d1117',
  card: '#161b22',
  border: '#30363d',
  text: '#e6edf3',
  muted: '#8b949e',
  blue: '#58a6ff',
  green: '#3fb950',
  red: '#f85149',
  yellow: '#d29922',
  purple: '#8b5cf6',
  orange: '#f0883e',
};

/* ─── helpers ───────────────────────────────────────────────────────────── */
const fmt = (iso) => {
  if (!iso) return '—';
  try { return format(parseISO(iso), 'dd MMM yyyy, HH:mm'); } catch { return iso; }
};

const fmtTime = (t) => {
  if (!t) return '—';
  try { return format(parseISO(`2000-01-01T${t}`), 'hh:mm a'); } catch { return t; }
};

const fmtDate = (iso) => {
  if (!iso) return '—';
  try { return format(parseISO(iso), 'dd MMM yyyy'); } catch { return iso; }
};

const fmtDuration = (inIso, outIso) => {
  if (!inIso || !outIso) return '—';
  try {
    const mins = differenceInMinutes(parseISO(outIso), parseISO(inIso));
    if (mins < 0) return '—';
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return `${h}h ${m}m`;
  } catch { return '—'; }
};

const basename = (path) => {
  if (!path) return '';
  return path.split(/[\\/]/).pop();
};

/* ─── sub-components ────────────────────────────────────────────────────── */
const cardStyle = {
  backgroundColor: T.card,
  border: `1px solid ${T.border}`,
  borderRadius: 8,
  padding: '20px 24px',
  marginBottom: 20,
};

const labelStyle = {
  fontSize: 12,
  color: T.muted,
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  marginBottom: 2,
};

const valueStyle = {
  color: T.text,
  fontSize: 14,
  wordBreak: 'break-word',
};

const sectionTitle = {
  color: T.text,
  fontWeight: 600,
  fontSize: 15,
  marginBottom: 16,
  paddingBottom: 10,
  borderBottom: `1px solid ${T.border}`,
  display: 'flex',
  alignItems: 'center',
  gap: 8,
};

function InfoField({ label, value, icon: Icon }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={labelStyle}>
        {Icon && <Icon style={{ marginRight: 4, verticalAlign: 'middle' }} />}
        {label}
      </div>
      <div style={valueStyle}>{value || '—'}</div>
    </div>
  );
}

function StatusBadge({ status }) {
  const map = {
    active: { color: T.green, label: 'Active' },
    inactive: { color: T.yellow, label: 'Inactive' },
    deleted: { color: T.red, label: 'Deleted' },
  };
  const cfg = map[status] || { color: T.muted, label: status };
  return (
    <span style={{
      fontSize: 12, fontWeight: 600, padding: '3px 10px',
      borderRadius: 20, backgroundColor: cfg.color + '22',
      color: cfg.color, border: `1px solid ${cfg.color}44`,
    }}>
      {cfg.label}
    </span>
  );
}

function EnrollmentBadge({ status }) {
  const map = {
    not_started: { color: T.muted, label: 'Not Enrolled' },
    pending: { color: T.yellow, label: 'Enrolling…' },
    enrolled: { color: T.green, label: 'Enrolled' },
    failed: { color: T.red, label: 'Enroll Failed' },
  };
  const cfg = map[status] || { color: T.muted, label: status };
  return (
    <span style={{
      fontSize: 12, fontWeight: 600, padding: '3px 10px',
      borderRadius: 20, backgroundColor: cfg.color + '22',
      color: cfg.color, border: `1px solid ${cfg.color}44`,
    }}>
      {cfg.label}
    </span>
  );
}

function AttendanceBadge({ status }) {
  const map = {
    present: { color: T.green },
    late: { color: T.yellow },
    absent: { color: T.red },
    half_day: { color: T.orange },
  };
  const cfg = map[status] || { color: T.muted };
  const label = status ? status.replace('_', ' ') : '—';
  return (
    <span style={{
      fontSize: 11, fontWeight: 600, padding: '2px 8px',
      borderRadius: 12, backgroundColor: cfg.color + '22',
      color: cfg.color, border: `1px solid ${cfg.color}44`,
      textTransform: 'capitalize',
    }}>
      {label}
    </span>
  );
}

function Btn({ onClick, disabled, variant = 'outline', color = T.blue, children, style = {} }) {
  const base = {
    border: `1px solid ${color}`,
    borderRadius: 6,
    padding: '6px 14px',
    fontSize: 13,
    fontWeight: 500,
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.5 : 1,
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    transition: 'all 0.15s',
    ...style,
  };
  if (variant === 'solid') {
    base.backgroundColor = color;
    base.color = '#fff';
  } else {
    base.backgroundColor = color + '15';
    base.color = color;
  }
  return (
    <button onClick={onClick} disabled={disabled} style={base}>
      {children}
    </button>
  );
}

function Skeleton({ height = 16, width = '100%', style = {} }) {
  return (
    <div style={{
      height, width, borderRadius: 4,
      backgroundColor: T.border,
      animation: 'pulse 1.5s ease-in-out infinite',
      ...style,
    }} />
  );
}

/* ─── main component ────────────────────────────────────────────────────── */
export default function EmployeeDetail() {
  const { employee_id } = useParams();
  const navigate = useNavigate();

  /* data state */
  const [employee, setEmployee] = useState(null);
  const [loading, setLoading] = useState(true);
  const [attendance, setAttendance] = useState([]);
  const [attendanceLoading, setAttendanceLoading] = useState(true);

  /* enrollment polling */
  const [enrolling, setEnrolling] = useState(false);
  const pollRef = useRef(null);

  /* photo upload */
  const photoInputRef = useRef(null);
  const [photoUploading, setPhotoUploading] = useState(false);
  const [deletingPhoto, setDeletingPhoto] = useState(null);

  /* edit modal */
  const modalRef = useRef(null);
  const bsModalRef = useRef(null);
  const [editForm, setEditForm] = useState({});
  const [editSaving, setEditSaving] = useState(false);

  /* deactivate */
  const [deactivating, setDeactivating] = useState(false);

  /* ── fetch employee ── */
  const fetchEmployee = useCallback(async () => {
    try {
      const res = await employeesAPI.getById(employee_id);
      setEmployee(res.data);
    } catch (err) {
      toast.error('Failed to load employee');
    }
  }, [employee_id]);

  /* ── fetch attendance ── */
  const fetchAttendance = useCallback(async () => {
    setAttendanceLoading(true);
    try {
      const res = await attendanceAPI.getAll({ employee_id, skip: 0, limit: 10 });
      setAttendance(Array.isArray(res.data) ? res.data : (res.data?.items ?? []));
    } catch {
      setAttendance([]);
    } finally {
      setAttendanceLoading(false);
    }
  }, [employee_id]);

  useEffect(() => {
    (async () => {
      setLoading(true);
      await fetchEmployee();
      setLoading(false);
    })();
    fetchAttendance();
  }, [fetchEmployee, fetchAttendance]);

  /* ── enrollment polling ── */
  const stopPoll = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }, []);

  const startPoll = useCallback(() => {
    stopPoll();
    pollRef.current = setInterval(async () => {
      try {
        const res = await employeesAPI.getEnrollmentStatus(employee_id);
        const status = res.data?.enrollment_status ?? res.data?.status;
        setEmployee((prev) => prev ? { ...prev, enrollment_status: status, enrollment_error: res.data?.enrollment_error ?? null } : prev);
        if (status === 'enrolled') {
          stopPoll();
          setEnrolling(false);
          toast.success('Face enrollment completed!');
          fetchEmployee();
        } else if (status === 'failed') {
          stopPoll();
          setEnrolling(false);
          toast.error('Enrollment failed');
          fetchEmployee();
        }
      } catch { /* keep polling */ }
    }, 3000);
  }, [employee_id, stopPoll, fetchEmployee]);

  /* auto-poll if already pending on load */
  useEffect(() => {
    if (employee?.enrollment_status === 'pending') {
      setEnrolling(true);
      startPoll();
    }
    return () => stopPoll();
  }, [employee?.enrollment_status, startPoll, stopPoll]);

  /* ── bootstrap modal init ── */
  useEffect(() => {
    if (modalRef.current && window.bootstrap?.Modal) {
      bsModalRef.current = new window.bootstrap.Modal(modalRef.current);
    }
  }, []);

  /* ── handlers ── */
  const handleTriggerEnroll = async () => {
    setEnrolling(true);
    try {
      await employeesAPI.triggerEnrollment(employee_id);
      setEmployee((prev) => prev ? { ...prev, enrollment_status: 'pending' } : prev);
      startPoll();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to start enrollment');
      setEnrolling(false);
    }
  };

  const handlePhotoUpload = async (e) => {
    const files = Array.from(e.target.files);
    if (!files.length) return;
    const formData = new FormData();
    files.forEach((f) => formData.append('photos', f));
    setPhotoUploading(true);
    try {
      await employeesAPI.uploadPhotos(employee_id, formData);
      toast.success(`${files.length} photo(s) uploaded`);
      fetchEmployee();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Upload failed');
    } finally {
      setPhotoUploading(false);
      e.target.value = '';
    }
  };

  const handleDeletePhoto = async (path) => {
    const name = basename(path);
    setDeletingPhoto(name);
    try {
      await employeesAPI.deletePhoto(employee_id, name);
      toast.success('Photo deleted');
      fetchEmployee();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Delete failed');
    } finally {
      setDeletingPhoto(null);
    }
  };

  const openEditModal = () => {
    if (!employee) return;
    setEditForm({
      full_name: employee.full_name || '',
      department: employee.department || '',
      designation: employee.designation || '',
      employee_code: employee.employee_code || '',
      email: employee.email || '',
      phone: employee.phone || '',
      notes: employee.notes || '',
      work_start_time: employee.work_start_time || '',
      work_end_time: employee.work_end_time || '',
    });
    bsModalRef.current?.show();
  };

  const handleEditSave = async () => {
    setEditSaving(true);
    try {
      const payload = {};
      Object.entries(editForm).forEach(([k, v]) => { payload[k] = v === '' ? null : v; });
      await employeesAPI.update(employee_id, payload);
      toast.success('Profile updated');
      bsModalRef.current?.hide();
      fetchEmployee();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Update failed');
    } finally {
      setEditSaving(false);
    }
  };

  const handleDeactivate = async () => {
    if (!window.confirm(`Deactivate ${employee?.full_name}? This will remove their access.`)) return;
    setDeactivating(true);
    try {
      await employeesAPI.delete(employee_id);
      toast.success('Employee deactivated');
      navigate(-1);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Deactivation failed');
      setDeactivating(false);
    }
  };

  /* ── loading skeleton ── */
  if (loading) {
    return (
      <div style={{ backgroundColor: T.bg, minHeight: '100vh', padding: '24px 32px' }}>
        <style>{`@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }`}</style>
        <Skeleton height={20} width={120} style={{ marginBottom: 24 }} />
        <Skeleton height={36} width={300} style={{ marginBottom: 8 }} />
        <Skeleton height={20} width={180} style={{ marginBottom: 32 }} />
        {[1, 2, 3].map((i) => (
          <div key={i} style={{ ...cardStyle, marginBottom: 20 }}>
            <Skeleton height={18} width={160} style={{ marginBottom: 16 }} />
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              {[1, 2, 3, 4].map((j) => <Skeleton key={j} height={14} />)}
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (!employee) {
    return (
      <div style={{ backgroundColor: T.bg, minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ color: T.muted, textAlign: 'center' }}>
          <RiUserLine size={48} style={{ marginBottom: 12, opacity: 0.4 }} />
          <div>Employee not found</div>
        </div>
      </div>
    );
  }

  const BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

  return (
    <div style={{ backgroundColor: T.bg, minHeight: '100vh', color: T.text }}>
      <style>{`
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
        @keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
        .photo-thumb { position:relative; display:inline-block; }
        .photo-thumb .del-btn { display:none; }
        .photo-thumb:hover .del-btn { display:flex; }
        .action-card-btn:hover { opacity:0.85; }
        .tbl-row:hover { background:${T.border}33; }
        input[type="text"],input[type="email"],input[type="tel"],input[type="time"],textarea,select {
          background:${T.bg}; border:1px solid ${T.border}; color:${T.text};
          border-radius:6px; padding:8px 12px; width:100%; font-size:13px;
          outline:none; box-sizing:border-box;
        }
        input:focus,textarea:focus,select:focus { border-color:${T.blue}; }
        label.form-label { font-size:12px; color:${T.muted}; margin-bottom:4px; display:block; }
        .modal-content { background:${T.card}; border:1px solid ${T.border}; color:${T.text}; }
        .modal-header { border-bottom:1px solid ${T.border}; }
        .modal-footer { border-top:1px solid ${T.border}; }
        .btn-close { filter:invert(1); }
      `}</style>

      <div style={{ maxWidth: 1100, margin: '0 auto', padding: '24px 24px' }}>

        {/* ── Page Header ── */}
        <div style={{ marginBottom: 24 }}>
          <button
            onClick={() => navigate(-1)}
            style={{
              background: 'none', border: 'none', color: T.muted, cursor: 'pointer',
              display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13,
              padding: '4px 0', marginBottom: 16,
            }}
          >
            <RiArrowLeftLine size={15} /> Employees
          </button>

          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
            <div>
              <h1 style={{ color: T.text, fontSize: 26, fontWeight: 700, margin: 0 }}>
                {employee.full_name}
              </h1>
              <div style={{ color: T.muted, fontSize: 13, marginTop: 4 }}>
                ID: {employee.employee_id}
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
                <StatusBadge status={employee.status} />
                <EnrollmentBadge status={employee.enrollment_status} />
              </div>
            </div>

            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <Btn onClick={openEditModal} color={T.blue}>
                <RiEditLine size={14} /> Edit
              </Btn>
              <Btn onClick={handleTriggerEnroll} disabled={enrolling} color={T.purple}>
                {enrolling
                  ? <><RiLoader4Line size={14} style={{ animation: 'spin 1s linear infinite' }} /> Enrolling…</>
                  : <><RiRefreshLine size={14} /> Re-enroll</>}
              </Btn>
              <Btn onClick={handleDeactivate} disabled={deactivating} color={T.red}>
                <RiUserUnfollowLine size={14} />
                {deactivating ? 'Deactivating…' : 'Deactivate'}
              </Btn>
            </div>
          </div>
        </div>

        {/* ── Section 1: Profile Info ── */}
        <div style={cardStyle}>
          <div style={sectionTitle}>
            <RiUserLine size={16} color={T.blue} /> Profile Information
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '4px 32px' }}>
            <InfoField label="Full Name" icon={RiUserLine} value={employee.full_name} />
            <InfoField label="Employee ID" icon={RiIdCardLine} value={employee.employee_id} />
            <InfoField label="Employee Code" icon={RiIdCardLine} value={employee.employee_code} />
            <InfoField label="Department" icon={RiBuildingLine} value={employee.department} />
            <InfoField label="Designation" icon={RiBriefcaseLine} value={employee.designation} />
            <InfoField label="Email" icon={RiMailLine} value={employee.email} />
            <InfoField label="Phone" icon={RiPhoneLine} value={employee.phone} />
            <div style={{ marginBottom: 16 }}>
              <div style={labelStyle}><RiTimeLine style={{ marginRight: 4, verticalAlign: 'middle' }} />Work Hours</div>
              <div style={valueStyle}>
                {employee.work_start_time || employee.work_end_time
                  ? `${fmtTime(employee.work_start_time)} – ${fmtTime(employee.work_end_time)}`
                  : '—'}
              </div>
            </div>
            <InfoField label="Created At" icon={RiCalendarLine} value={fmt(employee.created_at)} />
          </div>
          {employee.notes && (
            <div style={{ marginTop: 4 }}>
              <div style={labelStyle}><RiFileTextLine style={{ marginRight: 4, verticalAlign: 'middle' }} />Notes</div>
              <div style={{ ...valueStyle, whiteSpace: 'pre-wrap' }}>{employee.notes}</div>
            </div>
          )}
        </div>

        {/* ── Section 2: Enrollment Status ── */}
        <div style={cardStyle}>
          <div style={sectionTitle}>
            <RiCameraLine size={16} color={T.purple} /> Enrollment Status
          </div>

          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
            <div style={{ flex: 1, minWidth: 220 }}>
              {/* status icon row */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                {employee.enrollment_status === 'enrolled' && (
                  <RiCheckboxCircleLine size={22} color={T.green} />
                )}
                {employee.enrollment_status === 'failed' && (
                  <RiCloseCircleLine size={22} color={T.red} />
                )}
                {employee.enrollment_status === 'pending' && (
                  <RiLoader4Line size={22} color={T.yellow} style={{ animation: 'spin 1s linear infinite' }} />
                )}
                {employee.enrollment_status === 'not_started' && (
                  <RiRadioButtonLine size={22} color={T.muted} />
                )}
                <span style={{
                  fontSize: 14, fontWeight: 600,
                  color: employee.enrollment_status === 'enrolled' ? T.green
                    : employee.enrollment_status === 'failed' ? T.red
                    : employee.enrollment_status === 'pending' ? T.yellow
                    : T.muted,
                }}>
                  {employee.enrollment_status === 'enrolled' && 'Face Embeddings Active'}
                  {employee.enrollment_status === 'pending' && 'Enrollment In Progress…'}
                  {employee.enrollment_status === 'failed' && 'Enrollment Failed'}
                  {employee.enrollment_status === 'not_started' && 'Not Enrolled'}
                </span>
              </div>

              {employee.enrollment_status === 'enrolled' && (
                <div style={{ color: T.muted, fontSize: 13 }}>
                  Last updated: {fmt(employee.updated_at)}
                </div>
              )}
              {employee.enrollment_status === 'failed' && employee.enrollment_error && (
                <div style={{
                  color: T.red, fontSize: 13, backgroundColor: T.red + '11',
                  border: `1px solid ${T.red}33`, borderRadius: 6, padding: '8px 12px', marginTop: 8,
                }}>
                  {employee.enrollment_error}
                </div>
              )}
              {employee.enrollment_status === 'pending' && (
                <div style={{ color: T.muted, fontSize: 13 }}>
                  Checking every 3 seconds… please wait.
                </div>
              )}
            </div>

            {(employee.enrollment_status === 'not_started' || employee.enrollment_status === 'failed') && (
              <div>
                <Btn onClick={handleTriggerEnroll} disabled={enrolling} variant="solid" color={T.purple}>
                  {enrolling
                    ? <><RiLoader4Line size={14} style={{ animation: 'spin 1s linear infinite' }} /> Starting…</>
                    : <><RiCameraLine size={14} /> Start Enrollment</>}
                </Btn>
              </div>
            )}
          </div>
        </div>

        {/* ── Section 3: Face Photos ── */}
        <div style={cardStyle}>
          <div style={{ ...sectionTitle, justifyContent: 'space-between' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <RiCameraLine size={16} color={T.blue} /> Face Photos
              <span style={{ fontSize: 12, color: T.muted, fontWeight: 400 }}>
                ({employee.photo_count ?? employee.photo_paths?.length ?? 0} / 10)
              </span>
            </span>
            <div>
              <input
                ref={photoInputRef}
                type="file"
                accept="image/*"
                multiple
                style={{ display: 'none' }}
                onChange={handlePhotoUpload}
              />
              <Btn
                onClick={() => photoInputRef.current?.click()}
                disabled={photoUploading}
                color={T.green}
              >
                {photoUploading
                  ? <><RiLoader4Line size={14} style={{ animation: 'spin 1s linear infinite' }} /> Uploading…</>
                  : <><RiAddLine size={14} /> Add Photos</>}
              </Btn>
            </div>
          </div>

          {employee.photo_paths && employee.photo_paths.length > 0 ? (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
              {employee.photo_paths.map((path) => {
                const name = basename(path);
                const url = `${BASE_URL}/api/v1/employees/${employee_id}/photos/${name}`;
                const isDeleting = deletingPhoto === name;
                return (
                  <div key={path} className="photo-thumb" style={{ width: 80, height: 80, borderRadius: 6, overflow: 'hidden', border: `1px solid ${T.border}`, position: 'relative', flexShrink: 0 }}>
                    <img
                      src={url}
                      alt={name}
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      onError={(e) => { e.target.style.display = 'none'; }}
                    />
                    <button
                      className="del-btn"
                      onClick={() => !isDeleting && handleDeletePhoto(path)}
                      disabled={isDeleting}
                      style={{
                        position: 'absolute', inset: 0, backgroundColor: 'rgba(248,81,73,0.75)',
                        border: 'none', color: '#fff', cursor: isDeleting ? 'wait' : 'pointer',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 12, flexDirection: 'column', gap: 2,
                      }}
                    >
                      {isDeleting
                        ? <RiLoader4Line size={18} style={{ animation: 'spin 1s linear infinite' }} />
                        : <><RiDeleteBinLine size={18} /><span style={{ fontSize: 10 }}>Delete</span></>}
                    </button>
                  </div>
                );
              })}
            </div>
          ) : (
            <div style={{
              textAlign: 'center', padding: '32px 0', color: T.muted,
              border: `1px dashed ${T.border}`, borderRadius: 8,
            }}>
              <RiCameraLine size={32} style={{ marginBottom: 8, opacity: 0.4 }} />
              <div style={{ fontSize: 13 }}>No photos uploaded yet</div>
              <div style={{ fontSize: 12, marginTop: 4 }}>Upload face photos to enable recognition</div>
            </div>
          )}
        </div>

        {/* ── Section 4: Recent Attendance ── */}
        <div style={cardStyle}>
          <div style={{ ...sectionTitle, justifyContent: 'space-between' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <RiCalendarLine size={16} color={T.green} /> Recent Attendance
            </span>
            <a
              href={`/attendance?employee_id=${employee_id}`}
              style={{ fontSize: 12, color: T.blue, textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4 }}
            >
              <RiEyeLine size={13} /> View All
            </a>
          </div>

          {attendanceLoading ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {[1, 2, 3].map((i) => <Skeleton key={i} height={38} />)}
            </div>
          ) : attendance.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '32px 0', color: T.muted }}>
              <RiCalendarLine size={32} style={{ marginBottom: 8, opacity: 0.4 }} />
              <div style={{ fontSize: 13 }}>No attendance records found</div>
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                    {['Date', 'Check In', 'Check Out', 'Duration', 'Status'].map((h) => (
                      <th key={h} style={{ padding: '8px 12px', textAlign: 'left', color: T.muted, fontWeight: 500, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {attendance.map((rec, i) => (
                    <tr key={rec.id ?? i} className="tbl-row" style={{ borderBottom: `1px solid ${T.border}33` }}>
                      <td style={{ padding: '10px 12px', color: T.text }}>{fmtDate(rec.date ?? rec.check_in)}</td>
                      <td style={{ padding: '10px 12px', color: T.text }}>{rec.check_in ? format(parseISO(rec.check_in), 'HH:mm') : '—'}</td>
                      <td style={{ padding: '10px 12px', color: T.text }}>{rec.check_out ? format(parseISO(rec.check_out), 'HH:mm') : '—'}</td>
                      <td style={{ padding: '10px 12px', color: T.muted }}>{fmtDuration(rec.check_in, rec.check_out)}</td>
                      <td style={{ padding: '10px 12px' }}><AttendanceBadge status={rec.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* ── Section 5: Quick Actions ── */}
        <div style={cardStyle}>
          <div style={sectionTitle}>
            <RiEditLine size={16} color={T.yellow} /> Quick Actions
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <Btn onClick={openEditModal} color={T.blue} style={{ padding: '10px 18px' }}>
              <RiEditLine size={15} /> Edit Profile
            </Btn>
            <Btn onClick={handleTriggerEnroll} disabled={enrolling} color={T.purple} style={{ padding: '10px 18px' }}>
              {enrolling
                ? <><RiLoader4Line size={15} style={{ animation: 'spin 1s linear infinite' }} /> Enrolling…</>
                : <><RiCameraLine size={15} /> Re-enroll Face</>}
            </Btn>
            <Btn onClick={handleDeactivate} disabled={deactivating} color={T.red} style={{ padding: '10px 18px' }}>
              <RiUserUnfollowLine size={15} />
              {deactivating ? 'Deactivating…' : 'Deactivate Employee'}
            </Btn>
            <Btn
              onClick={() => toast('Export coming soon', { icon: '📋' })}
              color={T.muted}
              style={{ padding: '10px 18px' }}
            >
              <RiDownloadLine size={15} /> Export Report
            </Btn>
          </div>
        </div>

      </div>{/* end maxWidth wrapper */}

      {/* ── Section 6: Edit Profile Modal ── */}
      <div className="modal fade" ref={modalRef} tabIndex="-1">
        <div className="modal-dialog modal-lg">
          <div className="modal-content">
            <div className="modal-header">
              <h5 className="modal-title" style={{ color: T.text, fontWeight: 600 }}>
                Edit Profile — {employee.full_name}
              </h5>
              <button type="button" className="btn-close" data-bs-dismiss="modal" />
            </div>
            <div className="modal-body">
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 20px' }}>

                <div className="mb-3">
                  <label className="form-label">Full Name</label>
                  <input type="text" value={editForm.full_name || ''} onChange={(e) => setEditForm((p) => ({ ...p, full_name: e.target.value }))} />
                </div>
                <div className="mb-3">
                  <label className="form-label">Employee Code</label>
                  <input type="text" value={editForm.employee_code || ''} onChange={(e) => setEditForm((p) => ({ ...p, employee_code: e.target.value }))} />
                </div>
                <div className="mb-3">
                  <label className="form-label">Department</label>
                  <input type="text" value={editForm.department || ''} onChange={(e) => setEditForm((p) => ({ ...p, department: e.target.value }))} />
                </div>
                <div className="mb-3">
                  <label className="form-label">Designation</label>
                  <input type="text" value={editForm.designation || ''} onChange={(e) => setEditForm((p) => ({ ...p, designation: e.target.value }))} />
                </div>
                <div className="mb-3">
                  <label className="form-label">Email</label>
                  <input type="email" value={editForm.email || ''} onChange={(e) => setEditForm((p) => ({ ...p, email: e.target.value }))} />
                </div>
                <div className="mb-3">
                  <label className="form-label">Phone</label>
                  <input type="tel" value={editForm.phone || ''} onChange={(e) => setEditForm((p) => ({ ...p, phone: e.target.value }))} />
                </div>
                <div className="mb-3">
                  <label className="form-label">Work Start Time</label>
                  <input type="time" value={editForm.work_start_time || ''} onChange={(e) => setEditForm((p) => ({ ...p, work_start_time: e.target.value }))} />
                </div>
                <div className="mb-3">
                  <label className="form-label">Work End Time</label>
                  <input type="time" value={editForm.work_end_time || ''} onChange={(e) => setEditForm((p) => ({ ...p, work_end_time: e.target.value }))} />
                </div>
                <div className="mb-3" style={{ gridColumn: '1 / -1' }}>
                  <label className="form-label">Notes</label>
                  <textarea rows={3} value={editForm.notes || ''} onChange={(e) => setEditForm((p) => ({ ...p, notes: e.target.value }))} style={{ resize: 'vertical' }} />
                </div>

              </div>
            </div>
            <div className="modal-footer">
              <button
                type="button"
                data-bs-dismiss="modal"
                style={{
                  background: 'none', border: `1px solid ${T.border}`, color: T.muted,
                  borderRadius: 6, padding: '7px 16px', cursor: 'pointer', fontSize: 13,
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleEditSave}
                disabled={editSaving}
                style={{
                  backgroundColor: T.blue, border: 'none', color: '#fff',
                  borderRadius: 6, padding: '7px 20px', cursor: editSaving ? 'not-allowed' : 'pointer',
                  fontSize: 13, fontWeight: 600, opacity: editSaving ? 0.6 : 1,
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                }}
              >
                {editSaving
                  ? <><RiLoader4Line size={14} style={{ animation: 'spin 1s linear infinite' }} /> Saving…</>
                  : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      </div>

    </div>
  );
}
