import React, { useState, useEffect, useMemo } from 'react';
import { vehiclesAPI } from '../services/api';
import DataTable from '../components/common/DataTable';
import DateRangePicker from '../components/common/DateRangePicker';
import StatusBadge from '../components/common/StatusBadge';
import { createColumnHelper } from '@tanstack/react-table';
import { format, formatDistanceToNow } from 'date-fns';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, PieChart, Pie, Cell } from 'recharts';
import { RiCarLine, RiTimeLine } from 'react-icons/ri';

const colHelper = createColumnHelper();
const PIE_COLORS = ['#58a6ff', '#3fb950', '#d29922', '#f85149', '#8b5cf6'];

const today = new Date();
const EMPTY_RANGE = {
  startDate: format(new Date(today.getFullYear(), today.getMonth(), 1), 'yyyy-MM-dd'),
  endDate: format(today, 'yyyy-MM-dd'),
};

export default function VehiclesPage() {
  const [plates, setPlates] = useState([]);
  const [active, setActive] = useState([]);
  const [parkingData, setParkingData] = useState([]);
  const [typeData, setTypeData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dateRange, setDateRange] = useState(EMPTY_RANGE);
  const [globalFilter, setGlobalFilter] = useState('');

  useEffect(() => { load(); }, [dateRange]);

  async function load() {
    setLoading(true);
    try {
      const [platesRes, activeRes, parkRes] = await Promise.all([
        vehiclesAPI.getLicensePlateLog(dateRange),
        vehiclesAPI.getActive(),
        vehiclesAPI.getParkingAnalytics(dateRange),
      ]);
      setPlates(platesRes.data?.items || platesRes.data || MOCK_PLATES);
      setActive(activeRes.data?.items || activeRes.data || MOCK_ACTIVE);
      setParkingData(parkRes.data?.hourly || MOCK_PARKING);
      setTypeData(parkRes.data?.types || MOCK_TYPES);
    } catch {
      setPlates(MOCK_PLATES); setActive(MOCK_ACTIVE);
      setParkingData(MOCK_PARKING); setTypeData(MOCK_TYPES);
    } finally { setLoading(false); }
  }

  const columns = useMemo(() => [
    colHelper.accessor('plate', {
      header: 'License Plate',
      cell: (i) => (
        <span style={{ fontFamily: 'monospace', color: '#e6edf3', fontWeight: 600, fontSize: 13,
          background: '#21262d', padding: '2px 8px', borderRadius: 4 }}>
          {i.getValue()}
        </span>
      ),
    }),
    colHelper.accessor('type', { header: 'Type' }),
    colHelper.accessor('camera_name', { header: 'Camera' }),
    colHelper.accessor('entry_time', {
      header: 'Entry',
      cell: (i) => i.getValue()
        ? <span className="text-muted" style={{ fontSize: 12 }}>{format(new Date(i.getValue()), 'HH:mm dd/MM')}</span>
        : '—',
    }),
    colHelper.accessor('exit_time', {
      header: 'Exit',
      cell: (i) => i.getValue()
        ? <span className="text-muted" style={{ fontSize: 12 }}>{format(new Date(i.getValue()), 'HH:mm dd/MM')}</span>
        : <StatusBadge status="active" label="Still Inside" size="sm" />,
    }),
    colHelper.accessor('duration_mins', {
      header: 'Duration',
      cell: (i) => i.getValue()
        ? <span style={{ color: '#58a6ff', fontSize: 12 }}>{Math.floor(i.getValue() / 60)}h {i.getValue() % 60}m</span>
        : '—',
    }),
    colHelper.accessor('confidence', {
      header: 'ANPR Confidence',
      cell: (i) => {
        const v = i.getValue();
        if (!v) return '—';
        const color = v >= 0.9 ? '#3fb950' : v >= 0.7 ? '#d29922' : '#f85149';
        return (
          <div className="d-flex align-items-center gap-2">
            <div style={{ width: 50, height: 4, background: '#21262d', borderRadius: 2, overflow: 'hidden' }}>
              <div style={{ width: `${v * 100}%`, height: '100%', background: color, borderRadius: 2 }} />
            </div>
            <span style={{ color, fontSize: 12 }}>{(v * 100).toFixed(0)}%</span>
          </div>
        );
      },
    }),
  ], []);

  return (
    <div>
      <div className="d-flex align-items-center justify-content-between mb-3">
        <h4 className="text-white fw-semibold mb-0">Vehicle Analytics</h4>
        <DateRangePicker startDate={dateRange.startDate} endDate={dateRange.endDate}
          onChange={setDateRange} label="" />
      </div>

      {/* Active vehicles summary */}
      <div className="row g-3 mb-3">
        <div className="col-md-3">
          <div className="card text-center" style={{ background: '#161b22', border: '1px solid rgba(88,166,255,0.3)', borderRadius: 10 }}>
            <div className="card-body py-3">
              <RiCarLine size={24} color="#58a6ff" className="mb-2" />
              <div className="text-white fw-bold" style={{ fontSize: 28 }}>{active.length}</div>
              <div className="text-muted" style={{ fontSize: 12 }}>Vehicles Inside</div>
            </div>
          </div>
        </div>
        {active.slice(0, 3).map((v, i) => (
          <div key={i} className="col-md-3">
            <div className="card" style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 10 }}>
              <div className="card-body py-3 px-3">
                <div className="d-flex align-items-center gap-2 mb-1">
                  <span style={{ fontFamily: 'monospace', color: '#e6edf3', fontWeight: 700, fontSize: 14 }}>{v.plate}</span>
                  <StatusBadge status="active" size="sm" />
                </div>
                <div className="text-muted" style={{ fontSize: 12 }}>{v.zone || 'Parking Area'}</div>
                <div className="d-flex align-items-center gap-1 mt-1">
                  <RiTimeLine size={11} color="#8b949e" />
                  <span className="text-muted" style={{ fontSize: 11 }}>
                    {v.entry_time ? formatDistanceToNow(new Date(v.entry_time), { addSuffix: false }) : '—'}
                  </span>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Charts */}
      <div className="row g-3 mb-3">
        <div className="col-lg-8">
          <div className="card" style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 10 }}>
            <div className="card-header px-3 py-2" style={{ background: 'transparent', borderBottom: '1px solid #30363d' }}>
              <span className="fw-semibold text-white" style={{ fontSize: 14 }}>Hourly Parking Activity</span>
            </div>
            <div className="card-body p-2">
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={parkingData} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
                  <XAxis dataKey="hour" tick={{ fill: '#8b949e', fontSize: 11 }} axisLine={{ stroke: '#30363d' }} tickLine={false} />
                  <YAxis tick={{ fill: '#8b949e', fontSize: 11 }} axisLine={{ stroke: '#30363d' }} tickLine={false} />
                  <Tooltip contentStyle={{ background: '#1c2128', border: '1px solid #30363d', borderRadius: 6, fontSize: 12 }} />
                  <Bar dataKey="entries" name="Entries" fill="#3fb950" radius={[2, 2, 0, 0]} />
                  <Bar dataKey="exits" name="Exits" fill="#f85149" radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
        <div className="col-lg-4">
          <div className="card h-100" style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 10 }}>
            <div className="card-header px-3 py-2" style={{ background: 'transparent', borderBottom: '1px solid #30363d' }}>
              <span className="fw-semibold text-white" style={{ fontSize: 14 }}>Vehicle Types</span>
            </div>
            <div className="card-body p-2 d-flex flex-column align-items-center justify-content-center">
              <ResponsiveContainer width="100%" height={140}>
                <PieChart>
                  <Pie data={typeData} cx="50%" cy="50%" innerRadius={35} outerRadius={60}
                    dataKey="value" nameKey="name" paddingAngle={3}>
                    {typeData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                  </Pie>
                  <Tooltip contentStyle={{ background: '#1c2128', border: '1px solid #30363d', borderRadius: 6, fontSize: 12 }} />
                </PieChart>
              </ResponsiveContainer>
              <div className="d-flex flex-wrap justify-content-center gap-2 mt-1">
                {typeData.map((t, i) => (
                  <span key={t.name} style={{ fontSize: 11, color: PIE_COLORS[i % PIE_COLORS.length] }}>
                    ● {t.name}: {t.value}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* License plate log */}
      <div className="card" style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 10 }}>
        <div className="card-header px-3 py-2" style={{ background: 'transparent', borderBottom: '1px solid #30363d' }}>
          <span className="fw-semibold text-white" style={{ fontSize: 14 }}>License Plate Log</span>
        </div>
        <div className="card-body">
          <DataTable data={plates} columns={columns} loading={loading}
            globalFilter={globalFilter} onGlobalFilterChange={setGlobalFilter} />
        </div>
      </div>
    </div>
  );
}

const MOCK_PLATES = Array.from({ length: 15 }, (_, i) => ({
  id: i + 1,
  plate: `MH${Math.floor(Math.random() * 20 + 1).toString().padStart(2, '0')}-AB-${Math.floor(1000 + Math.random() * 9000)}`,
  type: ['Car', 'Truck', 'Bike', 'Van'][i % 4],
  camera_name: ['Parking A Cam', 'Main Gate', 'Parking B Cam'][i % 3],
  entry_time: new Date(Date.now() - (i + 1) * 1800000).toISOString(),
  exit_time: i % 3 === 0 ? null : new Date(Date.now() - i * 600000).toISOString(),
  duration_mins: i % 3 === 0 ? null : Math.floor(60 + Math.random() * 120),
  confidence: 0.75 + Math.random() * 0.24,
}));

const MOCK_ACTIVE = Array.from({ length: 4 }, (_, i) => ({
  id: i + 1,
  plate: `KA${i + 1 < 10 ? '0' : ''}${i + 1}-MN-${Math.floor(1000 + Math.random() * 9000)}`,
  zone: ['Zone A', 'Zone B', 'Zone C', 'VIP'][i],
  entry_time: new Date(Date.now() - (i + 1) * 3600000).toISOString(),
}));

const MOCK_PARKING = Array.from({ length: 12 }, (_, i) => ({
  hour: `${(8 + i).toString().padStart(2, '0')}:00`,
  entries: Math.floor(Math.random() * 10 + 2),
  exits: Math.floor(Math.random() * 8 + 1),
}));

const MOCK_TYPES = [
  { name: 'Car', value: 45 },
  { name: 'Bike', value: 18 },
  { name: 'Truck', value: 7 },
  { name: 'Van', value: 12 },
  { name: 'Other', value: 4 },
];
