import React, { useState, useEffect, useMemo, useRef } from 'react';
import { employeesAPI } from '../services/api';
import DataTable from '../components/common/DataTable';
import Modal from '../components/common/Modal';
import StatusBadge from '../components/common/StatusBadge';
import { createColumnHelper } from '@tanstack/react-table';
import toast from 'react-hot-toast';
import {
  RiAddLine, RiEditLine, RiDeleteBinLine, RiCameraLine,
  RiDownloadLine, RiCheckboxCircleLine, RiCloseCircleLine,
} from 'react-icons/ri';

const colHelper = createColumnHelper();

const DEPARTMENTS = ['Engineering', 'HR', 'Finance', 'Operations', 'Sales', 'R&D', 'Security', 'IT'];
const EMPTY_FORM = { employee_id: '', full_name: '', department: '', designation: '', email: '', phone: '', status: 'active' };

export default function EmployeesPage() {
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterDept, setFilterDept] = useState('');
  const [globalFilter, setGlobalFilter] = useState('');
  const [showAdd, setShowAdd] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [showFace, setShowFace] = useState(false);
  const [showDelete, setShowDelete] = useState(false);
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [faceFile, setFaceFile] = useState(null);
  const [facePreview, setFacePreview] = useState(null);
  const [enrolling, setEnrolling] = useState(false);
  const fileRef = useRef(null);

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    try {
      const res = await employeesAPI.getAll();
      setEmployees(res.data?.items || res.data || MOCK_EMPLOYEES);
    } catch { setEmployees(MOCK_EMPLOYEES); }
    finally { setLoading(false); }
  }

  const filtered = useMemo(() =>
    employees.filter((e) => !filterDept || e.department === filterDept),
    [employees, filterDept]
  );

  async function handleSave() {
    setSaving(true);
    try {
      if (showEdit) {
        await employeesAPI.update(selected.id, form);
        toast.success('Employee updated');
      } else {
        await employeesAPI.create(form);
        toast.success('Employee added');
      }
      setShowAdd(false); setShowEdit(false);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to save employee');
    } finally { setSaving(false); }
  }

  async function handleDelete() {
    try {
      await employeesAPI.delete(selected.id);
      toast.success('Employee deleted');
      setShowDelete(false); load();
    } catch { toast.error('Delete failed'); }
  }

  async function handleEnrollFace() {
    if (!faceFile) return;
    setEnrolling(true);
    try {
      const fd = new FormData();
      fd.append('image', faceFile);
      await employeesAPI.enrollFace(selected.id, fd);
      toast.success('Face enrolled successfully');
      setShowFace(false); setFaceFile(null); setFacePreview(null);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Face enrollment failed');
    } finally { setEnrolling(false); }
  }

  function handleFileChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setFaceFile(file);
    const reader = new FileReader();
    reader.onload = (ev) => setFacePreview(ev.target.result);
    reader.readAsDataURL(file);
  }

  async function handleExport() {
    try {
      const res = await employeesAPI.exportCSV({ department: filterDept });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url; a.download = 'employees.csv'; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error('Export failed'); }
  }

  const columns = useMemo(() => [
    colHelper.accessor('employee_id', {
      header: 'ID',
      cell: (i) => <span style={{ color: '#58a6ff', fontFamily: 'monospace', fontSize: 12 }}>{i.getValue()}</span>,
    }),
    colHelper.accessor('full_name', {
      header: 'Name',
      cell: (i) => <span className="text-white fw-medium">{i.getValue()}</span>,
    }),
    colHelper.accessor('department', { header: 'Department' }),
    colHelper.accessor('designation', { header: 'Designation', cell: (i) => <span className="text-muted">{i.getValue()}</span> }),
    colHelper.accessor('status', {
      header: 'Status',
      cell: (i) => <StatusBadge status={i.getValue()} />,
    }),
    colHelper.accessor('face_enrolled', {
      header: 'Face',
      cell: (i) => i.getValue()
        ? <RiCheckboxCircleLine size={16} color="#3fb950" />
        : <RiCloseCircleLine size={16} color="#8b949e" />,
    }),
    colHelper.display({
      id: 'actions',
      header: 'Actions',
      cell: ({ row }) => {
        const emp = row.original;
        return (
          <div className="d-flex gap-1">
            <button className="btn btn-sm btn-outline-primary py-1 px-2" title="Edit"
              onClick={() => { setSelected(emp); setForm({ ...emp }); setShowEdit(true); }}>
              <RiEditLine size={13} />
            </button>
            <button className="btn btn-sm btn-outline-secondary py-1 px-2" title="Face Enroll"
              onClick={() => { setSelected(emp); setFaceFile(null); setFacePreview(null); setShowFace(true); }}>
              <RiCameraLine size={13} />
            </button>
            <button className="btn btn-sm btn-outline-danger py-1 px-2" title="Delete"
              onClick={() => { setSelected(emp); setShowDelete(true); }}>
              <RiDeleteBinLine size={13} />
            </button>
          </div>
        );
      },
    }),
  ], []);

  const FilterBar = (
    <select className="form-select form-select-sm" value={filterDept}
      onChange={(e) => setFilterDept(e.target.value)}
      style={{ background: '#0d1117', border: '1px solid #30363d', color: '#e6edf3', width: 'auto' }}>
      <option value="">All Departments</option>
      {DEPARTMENTS.map((d) => <option key={d}>{d}</option>)}
    </select>
  );

  const FormFields = () => (
    <div className="row g-3">
      {[
        { label: 'Employee ID', key: 'employee_id', required: true },
        { label: 'Full Name', key: 'full_name', required: true },
        { label: 'Email', key: 'email', type: 'email' },
        { label: 'Phone', key: 'phone' },
        { label: 'Designation', key: 'designation' },
      ].map(({ label, key, type = 'text', required }) => (
        <div key={key} className="col-md-6">
          <label className="form-label text-muted" style={{ fontSize: 13 }}>{label}</label>
          <input type={type} className="form-control form-control-sm"
            style={{ background: '#0d1117', border: '1px solid #30363d', color: '#e6edf3' }}
            value={form[key] || ''} required={required}
            onChange={(e) => setForm((p) => ({ ...p, [key]: e.target.value }))} />
        </div>
      ))}
      <div className="col-md-6">
        <label className="form-label text-muted" style={{ fontSize: 13 }}>Department</label>
        <select className="form-select form-select-sm"
          style={{ background: '#0d1117', border: '1px solid #30363d', color: '#e6edf3' }}
          value={form.department || ''} onChange={(e) => setForm((p) => ({ ...p, department: e.target.value }))}>
          <option value="">Select…</option>
          {DEPARTMENTS.map((d) => <option key={d}>{d}</option>)}
        </select>
      </div>
      <div className="col-md-6">
        <label className="form-label text-muted" style={{ fontSize: 13 }}>Status</label>
        <select className="form-select form-select-sm"
          style={{ background: '#0d1117', border: '1px solid #30363d', color: '#e6edf3' }}
          value={form.status || 'active'} onChange={(e) => setForm((p) => ({ ...p, status: e.target.value }))}>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
          <option value="suspended">Suspended</option>
        </select>
      </div>
    </div>
  );

  return (
    <div>
      <div className="d-flex align-items-center justify-content-between mb-3">
        <h4 className="text-white fw-semibold mb-0">Employees</h4>
        <div className="d-flex gap-2">
          <button className="btn btn-sm btn-outline-secondary d-flex align-items-center gap-1" onClick={handleExport}>
            <RiDownloadLine size={14} /> Export CSV
          </button>
          <button className="btn btn-sm btn-primary d-flex align-items-center gap-1"
            onClick={() => { setForm(EMPTY_FORM); setShowAdd(true); }}>
            <RiAddLine size={16} /> Add Employee
          </button>
        </div>
      </div>

      <div className="card" style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 10 }}>
        <div className="card-body">
          <DataTable data={filtered} columns={columns} loading={loading}
            globalFilter={globalFilter} onGlobalFilterChange={setGlobalFilter}
            extra={FilterBar} />
        </div>
      </div>

      {/* Add/Edit */}
      <Modal show={showAdd || showEdit} onHide={() => { setShowAdd(false); setShowEdit(false); }}
        title={showEdit ? 'Edit Employee' : 'Add Employee'} size="lg"
        footer={
          <>
            <button className="btn btn-secondary btn-sm" onClick={() => { setShowAdd(false); setShowEdit(false); }}>Cancel</button>
            <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
              {saving ? 'Saving…' : 'Save'}
            </button>
          </>
        }>
        <FormFields />
      </Modal>

      {/* Face Enrollment */}
      <Modal show={showFace} onHide={() => setShowFace(false)} title={`Face Enrollment — ${selected?.full_name}`} size="sm"
        footer={
          <>
            <button className="btn btn-secondary btn-sm" onClick={() => setShowFace(false)}>Cancel</button>
            <button className="btn btn-primary btn-sm" onClick={handleEnrollFace} disabled={!faceFile || enrolling}>
              {enrolling ? 'Enrolling…' : 'Enroll Face'}
            </button>
          </>
        }>
        <div className="text-center">
          <div className="mb-3" style={{ cursor: 'pointer' }} onClick={() => fileRef.current?.click()}>
            {facePreview ? (
              <img src={facePreview} alt="Preview" className="rounded-circle"
                style={{ width: 120, height: 120, objectFit: 'cover', border: '2px solid #30363d' }} />
            ) : (
              <div className="rounded-circle d-inline-flex align-items-center justify-content-center"
                style={{ width: 120, height: 120, border: '2px dashed #30363d', background: '#0d1117', color: '#8b949e' }}>
                <RiCameraLine size={32} />
              </div>
            )}
          </div>
          <button className="btn btn-outline-secondary btn-sm" onClick={() => fileRef.current?.click()}>
            Choose Photo
          </button>
          <input ref={fileRef} type="file" accept="image/*" className="d-none" onChange={handleFileChange} />
          <p className="text-muted mt-2 mb-0" style={{ fontSize: 12 }}>
            Use a clear frontal face photo (JPEG/PNG)
          </p>
        </div>
      </Modal>

      {/* Delete */}
      <Modal show={showDelete} onHide={() => setShowDelete(false)} title="Delete Employee" size="sm"
        footer={
          <>
            <button className="btn btn-secondary btn-sm" onClick={() => setShowDelete(false)}>Cancel</button>
            <button className="btn btn-danger btn-sm" onClick={handleDelete}>Delete</button>
          </>
        }>
        <p className="text-white mb-0">Delete <strong>{selected?.full_name}</strong>? All associated data will be removed.</p>
      </Modal>
    </div>
  );
}

const MOCK_EMPLOYEES = [
  { id: 1, employee_id: 'EMP001', full_name: 'Alice Johnson', department: 'Engineering', designation: 'Senior Dev', email: 'alice@co.com', phone: '+1234567890', status: 'active', face_enrolled: true },
  { id: 2, employee_id: 'EMP002', full_name: 'Bob Smith', department: 'HR', designation: 'HR Manager', email: 'bob@co.com', phone: '+1234567891', status: 'active', face_enrolled: true },
  { id: 3, employee_id: 'EMP003', full_name: 'Carol White', department: 'Finance', designation: 'Analyst', email: 'carol@co.com', phone: '+1234567892', status: 'inactive', face_enrolled: false },
  { id: 4, employee_id: 'EMP004', full_name: 'David Brown', department: 'Operations', designation: 'Manager', email: 'david@co.com', phone: '+1234567893', status: 'active', face_enrolled: true },
  { id: 5, employee_id: 'EMP005', full_name: 'Eve Davis', department: 'Sales', designation: 'Rep', email: 'eve@co.com', phone: '+1234567894', status: 'active', face_enrolled: false },
];
