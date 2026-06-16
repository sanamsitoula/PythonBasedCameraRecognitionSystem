import React, { useState, useEffect, useMemo } from 'react';
import { attendanceAPI } from '../services/api';
import DataTable from '../components/common/DataTable';
import StatusBadge from '../components/common/StatusBadge';
import { createColumnHelper } from '@tanstack/react-table';
import { format, startOfMonth, endOfMonth, eachDayOfInterval, isSameDay, parseISO } from 'date-fns';
import toast from 'react-hot-toast';
import {
  RiDownloadLine, RiCalendarLine, RiGroupLine, RiUserLine,
  RiTimeLine, RiCloseCircleLine,
} from 'react-icons/ri';

const colHelper = createColumnHelper();
const DEPARTMENTS = ['All', 'Engineering', 'HR', 'Finance', 'Operations', 'Sales', 'R&D', 'Security', 'IT'];

function SummaryCard({ title, value, color, icon: Icon }) {
  return (
    <div className="card text-center" style={{ background: '#161b22', border: `1px solid ${color}44`, borderRadius: 10 }}>
      <div className="card-body py-3">
        <Icon size={20} color={color} className="mb-1" />
        <div className="text-white fw-bold" style={{ fontSize: 24 }}>{value}</div>
        <div className="text-muted" style={{ fontSize: 12 }}>{title}</div>
      </div>
    </div>
  );
}

export default function AttendancePage() {
  const [records, setRecords] = useState([]);
  const [summary, setSummary] = useState({ present: 0, absent: 0, late: 0, half_day: 0 });
  const [loading, setLoading] = useState(true);
  const [selectedDate, setSelectedDate] = useState(format(new Date(), 'yyyy-MM-dd'));
  const [filterDept, setFilterDept] = useState('All');
  const [globalFilter, setGlobalFilter] = useState('');
  const [view, setView] = useState('table'); // 'table' | 'calendar'
  const [heatmap, setHeatmap] = useState([]);

  useEffect(() => { load(); }, [selectedDate, filterDept]);
  useEffect(() => { if (view === 'calendar') loadHeatmap(); }, [view]);

  async function load() {
    setLoading(true);
    try {
      const dept = filterDept === 'All' ? undefined : filterDept;
      const [recRes, sumRes] = await Promise.all([
        attendanceAPI.getByDate(selectedDate, { department: dept }),
        attendanceAPI.getSummary({ date: selectedDate, department: dept }),
      ]);
      setRecords(recRes.data?.items || recRes.data || MOCK_RECORDS);
      setSummary(sumRes.data || MOCK_SUMMARY);
    } catch {
      setRecords(MOCK_RECORDS);
      setSummary(MOCK_SUMMARY);
    } finally { setLoading(false); }
  }

  async function loadHeatmap() {
    try {
      const res = await attendanceAPI.getMonthlyHeatmap({
        month: format(parseISO(selectedDate), 'yyyy-MM'),
      });
      setHeatmap(res.data || []);
    } catch { setHeatmap([]); }
  }

  async function handleExport(type) {
    try {
      const fn = type === 'pdf' ? attendanceAPI.exportPDF : attendanceAPI.exportExcel;
      const res = await fn({ date: selectedDate, department: filterDept === 'All' ? undefined : filterDept });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url; a.download = `attendance_${selectedDate}.${type === 'pdf' ? 'pdf' : 'xlsx'}`; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error('Export failed'); }
  }

  const columns = useMemo(() => [
    colHelper.accessor('employee_name', {
      header: 'Employee',
      cell: (i) => <span className="text-white fw-medium">{i.getValue()}</span>,
    }),
    colHelper.accessor('department', { header: 'Department', cell: (i) => <span className="text-muted">{i.getValue()}</span> }),
    colHelper.accessor('first_entry', {
      header: 'First Entry',
      cell: (i) => i.getValue()
        ? <span style={{ color: '#3fb950', fontSize: 13 }}>{i.getValue()}</span>
        : <span className="text-muted">—</span>,
    }),
    colHelper.accessor('last_exit', {
      header: 'Last Exit',
      cell: (i) => i.getValue()
        ? <span style={{ color: '#58a6ff', fontSize: 13 }}>{i.getValue()}</span>
        : <span className="text-muted">—</span>,
    }),
    colHelper.accessor('working_hours', {
      header: 'Working Hours',
      cell: (i) => {
        const h = i.getValue();
        if (!h) return <span className="text-muted">—</span>;
        const color = h >= 8 ? '#3fb950' : h >= 4 ? '#d29922' : '#f85149';
        return <span style={{ color, fontWeight: 600 }}>{h.toFixed(1)}h</span>;
      },
    }),
    colHelper.accessor('status', {
      header: 'Status',
      cell: (i) => <StatusBadge status={i.getValue()} />,
    }),
  ], []);

  // Calendar heatmap
  const calendarDays = useMemo(() => {
    const month = parseISO(selectedDate + '-01' in {} ? selectedDate : selectedDate);
    const start = startOfMonth(new Date(selectedDate));
    const end = endOfMonth(start);
    return eachDayOfInterval({ start, end });
  }, [selectedDate]);

  function getHeatIntensity(date) {
    const entry = heatmap.find((h) => isSameDay(parseISO(h.date), date));
    if (!entry) return '#21262d';
    const pct = entry.attendance_pct || 0;
    if (pct >= 90) return '#26a641';
    if (pct >= 70) return '#2da44e';
    if (pct >= 50) return '#216e39';
    if (pct > 0) return '#0e4429';
    return '#21262d';
  }

  return (
    <div>
      <div className="d-flex align-items-center justify-content-between mb-3 flex-wrap gap-2">
        <h4 className="text-white fw-semibold mb-0">Attendance</h4>
        <div className="d-flex gap-2 flex-wrap">
          <input type="date" className="form-control form-control-sm"
            style={{ background: '#0d1117', border: '1px solid #30363d', color: '#e6edf3', width: 160 }}
            value={selectedDate} onChange={(e) => setSelectedDate(e.target.value)} />
          <select className="form-select form-select-sm"
            style={{ background: '#0d1117', border: '1px solid #30363d', color: '#e6edf3', width: 'auto' }}
            value={filterDept} onChange={(e) => setFilterDept(e.target.value)}>
            {DEPARTMENTS.map((d) => <option key={d}>{d}</option>)}
          </select>
          <div className="btn-group btn-group-sm">
            <button className={`btn ${view === 'table' ? 'btn-primary' : 'btn-outline-secondary'}`}
              onClick={() => setView('table')}>Table</button>
            <button className={`btn ${view === 'calendar' ? 'btn-primary' : 'btn-outline-secondary'}`}
              onClick={() => setView('calendar')}>Calendar</button>
          </div>
          <div className="dropdown">
            <button className="btn btn-sm btn-outline-secondary dropdown-toggle" data-bs-toggle="dropdown">
              <RiDownloadLine size={14} /> Export
            </button>
            <ul className="dropdown-menu dropdown-menu-end" style={{ background: '#161b22', border: '1px solid #30363d' }}>
              <li><button className="dropdown-item text-white" onClick={() => handleExport('pdf')}>Export PDF</button></li>
              <li><button className="dropdown-item text-white" onClick={() => handleExport('excel')}>Export Excel</button></li>
            </ul>
          </div>
        </div>
      </div>

      {/* Summary cards */}
      <div className="row g-3 mb-3">
        <div className="col-6 col-md-3">
          <SummaryCard title="Present" value={summary.present} color="#3fb950" icon={RiGroupLine} />
        </div>
        <div className="col-6 col-md-3">
          <SummaryCard title="Absent" value={summary.absent} color="#f85149" icon={RiCloseCircleLine} />
        </div>
        <div className="col-6 col-md-3">
          <SummaryCard title="Late" value={summary.late} color="#d29922" icon={RiTimeLine} />
        </div>
        <div className="col-6 col-md-3">
          <SummaryCard title="Half Day" value={summary.half_day} color="#58a6ff" icon={RiUserLine} />
        </div>
      </div>

      {view === 'table' ? (
        <div className="card" style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 10 }}>
          <div className="card-body">
            <DataTable data={records} columns={columns} loading={loading}
              globalFilter={globalFilter} onGlobalFilterChange={setGlobalFilter} />
          </div>
        </div>
      ) : (
        <div className="card" style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 10 }}>
          <div className="card-header px-3 py-2" style={{ background: 'transparent', borderBottom: '1px solid #30363d' }}>
            <span className="fw-semibold text-white" style={{ fontSize: 14 }}>Monthly Attendance Heatmap</span>
          </div>
          <div className="card-body">
            <div className="d-grid gap-1" style={{ gridTemplateColumns: 'repeat(7, 1fr)', maxWidth: 420 }}>
              {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((d) => (
                <div key={d} className="text-muted text-center" style={{ fontSize: 11, padding: '4px 0' }}>{d}</div>
              ))}
              {Array.from({ length: calendarDays[0].getDay() }).map((_, i) => <div key={`pad-${i}`} />)}
              {calendarDays.map((day) => (
                <div key={day.toISOString()}
                  className="rounded d-flex align-items-center justify-content-center"
                  title={format(day, 'dd MMM yyyy')}
                  style={{ height: 36, background: getHeatIntensity(day), cursor: 'default', fontSize: 12, color: '#e6edf3' }}>
                  {format(day, 'd')}
                </div>
              ))}
            </div>
            <div className="d-flex gap-2 mt-3 flex-wrap align-items-center">
              <span className="text-muted" style={{ fontSize: 12 }}>Attendance %:</span>
              {[['< 50%', '#0e4429'], ['50-70%', '#216e39'], ['70-90%', '#2da44e'], ['> 90%', '#26a641'], ['No data', '#21262d']].map(([l, c]) => (
                <span key={l} className="d-flex align-items-center gap-1" style={{ fontSize: 12 }}>
                  <span style={{ width: 12, height: 12, borderRadius: 2, background: c, display: 'inline-block' }} />
                  <span className="text-muted">{l}</span>
                </span>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const MOCK_SUMMARY = { present: 87, absent: 12, late: 8, half_day: 5 };

const MOCK_RECORDS = [
  { id: 1, employee_name: 'Alice Johnson', department: 'Engineering', first_entry: '08:42', last_exit: '17:30', working_hours: 8.8, status: 'present' },
  { id: 2, employee_name: 'Bob Smith', department: 'HR', first_entry: '09:15', last_exit: '17:00', working_hours: 7.75, status: 'late' },
  { id: 3, employee_name: 'Carol White', department: 'Finance', first_entry: null, last_exit: null, working_hours: null, status: 'absent' },
  { id: 4, employee_name: 'David Brown', department: 'Operations', first_entry: '08:00', last_exit: '13:00', working_hours: 5.0, status: 'half-day' },
  { id: 5, employee_name: 'Eve Davis', department: 'Sales', first_entry: '08:55', last_exit: '18:10', working_hours: 9.25, status: 'present' },
  { id: 6, employee_name: 'Frank Miller', department: 'IT', first_entry: '08:30', last_exit: '17:45', working_hours: 9.25, status: 'present' },
];
