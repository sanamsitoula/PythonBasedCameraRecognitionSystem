import React, { useState, useEffect, useCallback } from 'react';
import { dashboardAPI } from '../services/api';
import StatsCard from '../components/Dashboard/StatsCard';
import OccupancyChart from '../components/Dashboard/OccupancyChart';
import AlertsPanel from '../components/Dashboard/AlertsPanel';
import CameraMonitor from '../components/Dashboard/CameraMonitor';
import useWebSocket from '../hooks/useWebSocket';
import {
  RiGroupLine, RiUserFollowLine, RiCarLine, RiPercentLine,
  RiDoorOpenLine, RiBellLine,
} from 'react-icons/ri';
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, Legend, PieChart, Pie, Cell,
} from 'recharts';
import { formatDistanceToNow } from 'date-fns';

const PIE_COLORS = ['#58a6ff', '#3fb950', '#d29922', '#f85149', '#8b5cf6', '#f97316'];

function CardSkeleton() {
  return (
    <div className="card" style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 10, height: 108 }}>
      <div className="card-body p-3">
        <div style={{ height: 10, width: '40%', borderRadius: 4, background: '#21262d', marginBottom: 10 }} />
        <div style={{ height: 28, width: '60%', borderRadius: 4, background: '#21262d', marginBottom: 8 }} />
        <div style={{ height: 8, width: '50%', borderRadius: 4, background: '#21262d' }} />
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [occupancyHistory, setOccupancyHistory] = useState([]);
  const [cameras, setCameras] = useState([]);
  const [recentDetections, setRecentDetections] = useState([]);
  const [deptData, setDeptData] = useState([]);
  const [vehicleData, setVehicleData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState(null);

  const load = useCallback(async () => {
    try {
      const [statsRes, occRes, detRes] = await Promise.all([
        dashboardAPI.getStats(),
        dashboardAPI.getOccupancyHistory(),
        dashboardAPI.getRecentDetections(),
      ]);
      setStats(statsRes.data);
      setOccupancyHistory(occRes.data?.history || []);
      setCameras(statsRes.data?.cameras || []);
      setRecentDetections(detRes.data?.detections || []);
      setDeptData(statsRes.data?.department_attendance || []);
      setVehicleData(statsRes.data?.vehicle_types || []);
      setLastRefresh(new Date());
    } catch {
      setStats(null);
      setOccupancyHistory([]);
      setCameras([]);
      setRecentDetections([]);
      setDeptData([]);
      setVehicleData([]);
      setLastRefresh(new Date());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Auto-refresh every 30s
  useEffect(() => {
    const interval = setInterval(load, 30000);
    return () => clearInterval(interval);
  }, [load]);

  // Live occupancy updates
  useWebSocket({
    onOccupancyUpdate: (data) => {
      setStats((prev) => prev ? { ...prev, ...data } : prev);
    },
  });

  const s = stats;

  return (
    <div>
      <div className="d-flex align-items-center justify-content-between mb-3">
        <div>
          <h4 className="text-white mb-0 fw-semibold">Overview</h4>
          {lastRefresh && (
            <span className="text-muted" style={{ fontSize: 12 }}>
              Updated {formatDistanceToNow(lastRefresh, { addSuffix: true })}
            </span>
          )}
        </div>
        <button className="btn btn-sm btn-outline-secondary" onClick={load} disabled={loading}>
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {/* Row 1: Stats */}
      <div className="row g-3 mb-3">
        {loading ? Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="col-6 col-md-4 col-xl-2"><CardSkeleton /></div>
        )) : [
          { title: 'People Present', value: s?.people_present ?? 0, icon: RiGroupLine, color: 'blue', trend: 'up', trendValue: '+12', subtitle: 'vs yesterday' },
          { title: 'Visitors Today', value: s?.visitors_today ?? 0, icon: RiUserFollowLine, color: 'green', trend: 'up', trendValue: '+3', subtitle: 'on-site' },
          { title: 'Vehicles', value: s?.vehicles_present ?? 0, icon: RiCarLine, color: 'orange', trend: 'neutral', subtitle: 'in parking' },
          { title: 'Occupancy', value: s?.occupancy_percent ?? 0, icon: RiPercentLine, color: s?.occupancy_percent > 80 ? 'red' : 'purple', subtitle: 'of capacity' },
          { title: "Today's Entries", value: s?.today_entries ?? 0, icon: RiDoorOpenLine, color: 'yellow', trend: 'up', trendValue: '+8', subtitle: 'total today' },
          { title: 'Active Alerts', value: s?.active_alerts ?? 0, icon: RiBellLine, color: s?.active_alerts > 0 ? 'red' : 'green', subtitle: 'unacknowledged' },
        ].map((card, i) => (
          <div key={i} className="col-6 col-md-4 col-xl-2">
            <StatsCard {...card} />
          </div>
        ))}
      </div>

      {/* Row 2: Occupancy chart + Alerts */}
      <div className="row g-3 mb-3">
        <div className="col-12 col-lg-8">
          <OccupancyChart data={occupancyHistory} />
        </div>
        <div className="col-12 col-lg-4">
          <AlertsPanel />
        </div>
      </div>

      {/* Row 3: Camera Monitor — live feed + analytics side by side */}
      <div className="mb-3">
        <CameraMonitor />
      </div>

      {/* Row 3b: Recent detections */}
      <div className="row g-3 mb-3">
        <div className="col-12">
          <div className="card" style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 10 }}>
            <div className="card-header px-3 py-2" style={{ background: 'transparent', borderBottom: '1px solid #30363d' }}>
              <span className="fw-semibold text-white" style={{ fontSize: 14 }}>Recent Detections</span>
            </div>
            <div className="card-body p-0" style={{ overflowY: 'auto', maxHeight: 300 }}>
              {recentDetections.length === 0 ? (
                <div className="text-center text-muted py-4" style={{ fontSize: 13 }}>No recent detections</div>
              ) : recentDetections.map((d, i) => (
                <div key={i} className="px-3 py-2 border-bottom d-flex align-items-center gap-3"
                  style={{ borderColor: '#30363d', fontSize: 13 }}>
                  {d.snapshot ? (
                    <img src={d.snapshot} alt="Detection" className="rounded"
                      style={{ width: 40, height: 40, objectFit: 'cover', flexShrink: 0 }} />
                  ) : (
                    <div className="rounded d-flex align-items-center justify-content-center"
                      style={{ width: 40, height: 40, background: '#21262d', flexShrink: 0, color: '#8b949e', fontSize: 11 }}>
                      {d.type?.charAt(0)?.toUpperCase() || '?'}
                    </div>
                  )}
                  <div className="flex-grow-1 overflow-hidden">
                    <div className="text-white text-truncate fw-medium">{d.name || d.label || 'Unknown'}</div>
                    <div className="text-muted" style={{ fontSize: 11 }}>
                      {d.camera_name} · {formatDistanceToNow(new Date(d.timestamp || Date.now()), { addSuffix: true })}
                    </div>
                  </div>
                  <span style={{ fontSize: 11, color: '#8b949e', flexShrink: 0, textTransform: 'capitalize' }}>
                    {d.type}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Row 4: Dept attendance + Vehicle analytics */}
      <div className="row g-3">
        <div className="col-12 col-lg-8">
          <div className="card" style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 10 }}>
            <div className="card-header px-3 py-2" style={{ background: 'transparent', borderBottom: '1px solid #30363d' }}>
              <span className="fw-semibold text-white" style={{ fontSize: 14 }}>Department Attendance</span>
            </div>
            <div className="card-body p-2">
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={deptData} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
                  <XAxis dataKey="dept" tick={{ fill: '#8b949e', fontSize: 11 }} axisLine={{ stroke: '#30363d' }} tickLine={false} />
                  <YAxis tick={{ fill: '#8b949e', fontSize: 11 }} axisLine={{ stroke: '#30363d' }} tickLine={false} />
                  <Tooltip contentStyle={{ background: '#1c2128', border: '1px solid #30363d', borderRadius: 6, fontSize: 12 }} />
                  <Legend wrapperStyle={{ fontSize: 12, color: '#8b949e' }} iconType="circle" iconSize={8} />
                  <Bar dataKey="present" name="Present" fill="#3fb950" radius={[3, 3, 0, 0]} />
                  <Bar dataKey="absent" name="Absent" fill="#f85149" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
        <div className="col-12 col-lg-4">
          <div className="card h-100" style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 10 }}>
            <div className="card-header px-3 py-2" style={{ background: 'transparent', borderBottom: '1px solid #30363d' }}>
              <span className="fw-semibold text-white" style={{ fontSize: 14 }}>Vehicle Breakdown</span>
            </div>
            <div className="card-body p-2 d-flex flex-column align-items-center justify-content-center">
              <ResponsiveContainer width="100%" height={160}>
                <PieChart>
                  <Pie data={vehicleData} cx="50%" cy="50%" innerRadius={45} outerRadius={70}
                    dataKey="value" nameKey="name" paddingAngle={2}>
                    {vehicleData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                  </Pie>
                  <Tooltip contentStyle={{ background: '#1c2128', border: '1px solid #30363d', borderRadius: 6, fontSize: 12 }} />
                </PieChart>
              </ResponsiveContainer>
              <div className="d-flex flex-wrap justify-content-center gap-2 mt-1">
                {vehicleData.map((v, i) => (
                  <span key={v.name} style={{ fontSize: 11, color: PIE_COLORS[i % PIE_COLORS.length] }}>
                    ● {v.name}: {v.value}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

