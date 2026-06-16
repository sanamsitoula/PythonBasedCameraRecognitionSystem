import React, { useState, useEffect, useMemo } from 'react';
import { visitorsAPI } from '../services/api';
import DataTable from '../components/common/DataTable';
import Modal from '../components/common/Modal';
import StatusBadge from '../components/common/StatusBadge';
import { createColumnHelper } from '@tanstack/react-table';
import toast from 'react-hot-toast';
import { format, formatDistanceToNow } from 'date-fns';
import { RiEyeLine, RiAlertLine, RiMapPinLine, RiTimeLine } from 'react-icons/ri';

const colHelper = createColumnHelper();

export default function VisitorsPage() {
  const [visitors, setVisitors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [globalFilter, setGlobalFilter] = useState('');
  const [showDetail, setShowDetail] = useState(false);
  const [selected, setSelected] = useState(null);
  const [history, setHistory] = useState([]);
  const [journey, setJourney] = useState([]);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    try {
      const res = await visitorsAPI.getAll();
      setVisitors(res.data?.items || res.data || MOCK_VISITORS);
    } catch { setVisitors(MOCK_VISITORS); }
    finally { setLoading(false); }
  }

  async function openDetail(visitor) {
    setSelected(visitor);
    setShowDetail(true);
    setDetailLoading(true);
    try {
      const [hRes, jRes] = await Promise.all([
        visitorsAPI.getHistory(visitor.id),
        visitorsAPI.getJourney(visitor.id),
      ]);
      setHistory(hRes.data || MOCK_HISTORY);
      setJourney(jRes.data || MOCK_JOURNEY);
    } catch {
      setHistory(MOCK_HISTORY);
      setJourney(MOCK_JOURNEY);
    } finally { setDetailLoading(false); }
  }

  async function addToWatchlist(id) {
    try {
      await visitorsAPI.addToWatchlist(id);
      toast.success('Added to watchlist');
    } catch { toast.error('Failed to add to watchlist'); }
  }

  const columns = useMemo(() => [
    colHelper.accessor('visitor_id', {
      header: 'Visitor ID',
      cell: (i) => <span style={{ color: '#58a6ff', fontFamily: 'monospace', fontSize: 12 }}>{i.getValue()}</span>,
    }),
    colHelper.accessor('snapshot', {
      header: 'Snapshot',
      enableSorting: false,
      cell: (i) => i.getValue()
        ? <img src={i.getValue()} alt="Visitor" className="rounded"
            style={{ width: 40, height: 40, objectFit: 'cover' }} />
        : <div className="rounded d-flex align-items-center justify-content-center"
            style={{ width: 40, height: 40, background: '#21262d', color: '#8b949e', fontSize: 11 }}>?</div>,
    }),
    colHelper.accessor('first_seen', {
      header: 'First Seen',
      cell: (i) => i.getValue()
        ? <span className="text-muted" style={{ fontSize: 12 }}>{format(new Date(i.getValue()), 'dd MMM HH:mm')}</span>
        : '—',
    }),
    colHelper.accessor('last_seen', {
      header: 'Last Seen',
      cell: (i) => i.getValue()
        ? <span className="text-muted" style={{ fontSize: 12 }}>{formatDistanceToNow(new Date(i.getValue()), { addSuffix: true })}</span>
        : '—',
    }),
    colHelper.accessor('total_visits', {
      header: 'Visits',
      cell: (i) => <span className="text-white">{i.getValue() || 1}</span>,
    }),
    colHelper.accessor('status', {
      header: 'Status',
      cell: (i) => <StatusBadge status={i.getValue() || 'active'} />,
    }),
    colHelper.display({
      id: 'actions',
      header: 'Actions',
      cell: ({ row }) => (
        <div className="d-flex gap-1">
          <button className="btn btn-sm btn-outline-primary py-1 px-2" onClick={() => openDetail(row.original)}>
            <RiEyeLine size={13} />
          </button>
          <button className="btn btn-sm btn-outline-warning py-1 px-2" title="Watchlist"
            onClick={() => addToWatchlist(row.original.id)}>
            <RiAlertLine size={13} />
          </button>
        </div>
      ),
    }),
  ], []);

  return (
    <div>
      <div className="d-flex align-items-center justify-content-between mb-3">
        <h4 className="text-white fw-semibold mb-0">Visitors</h4>
        <span className="text-muted" style={{ fontSize: 13 }}>{visitors.length} total visitors</span>
      </div>

      <div className="card" style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 10 }}>
        <div className="card-body">
          <DataTable data={visitors} columns={columns} loading={loading}
            globalFilter={globalFilter} onGlobalFilterChange={setGlobalFilter} />
        </div>
      </div>

      {/* Detail Modal */}
      <Modal show={showDetail} onHide={() => setShowDetail(false)}
        title={`Visitor — ${selected?.visitor_id}`} size="lg" scrollable>
        {selected && (
          <div>
            <div className="d-flex gap-3 mb-4 align-items-start">
              {selected.snapshot ? (
                <img src={selected.snapshot} alt="Visitor" className="rounded"
                  style={{ width: 80, height: 80, objectFit: 'cover', border: '2px solid #30363d' }} />
              ) : (
                <div className="rounded d-flex align-items-center justify-content-center"
                  style={{ width: 80, height: 80, background: '#21262d', color: '#8b949e', fontSize: 12 }}>
                  No photo
                </div>
              )}
              <div>
                <div className="text-white fw-semibold" style={{ fontSize: 16 }}>{selected.visitor_id}</div>
                <div className="d-flex align-items-center gap-2 mt-1">
                  <StatusBadge status={selected.status || 'active'} />
                  <span className="text-muted" style={{ fontSize: 13 }}>{selected.total_visits || 1} visit(s)</span>
                </div>
                <button className="btn btn-sm btn-outline-warning mt-2 d-flex align-items-center gap-1"
                  style={{ fontSize: 12 }} onClick={() => addToWatchlist(selected.id)}>
                  <RiAlertLine size={13} /> Add to Watchlist
                </button>
              </div>
            </div>

            {detailLoading ? (
              <div className="text-center py-3">
                <div className="spinner-border spinner-border-sm text-primary" />
              </div>
            ) : (
              <>
                {/* Visit history */}
                <h6 className="text-white mb-3 d-flex align-items-center gap-2">
                  <RiTimeLine /> Visit History
                </h6>
                <div className="mb-4">
                  {history.length === 0 ? (
                    <p className="text-muted" style={{ fontSize: 13 }}>No history</p>
                  ) : (
                    <div style={{ borderLeft: '2px solid #30363d', paddingLeft: 16 }}>
                      {history.map((h, i) => (
                        <div key={i} className="mb-3 position-relative">
                          <div className="position-absolute" style={{ left: -21, top: 4, width: 8, height: 8, borderRadius: '50%', background: '#1f6feb' }} />
                          <div className="text-white" style={{ fontSize: 13 }}>{h.event || 'Visit'}</div>
                          <div className="text-muted" style={{ fontSize: 11 }}>
                            {h.camera_name} · {h.timestamp ? format(new Date(h.timestamp), 'dd MMM yyyy HH:mm') : ''}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Zone journey */}
                <h6 className="text-white mb-3 d-flex align-items-center gap-2">
                  <RiMapPinLine /> Zone Journey
                </h6>
                <div className="d-flex flex-wrap gap-2">
                  {journey.map((z, i) => (
                    <React.Fragment key={i}>
                      <span className="badge rounded-pill" style={{ background: '#21262d', color: '#e6edf3', fontSize: 12, padding: '5px 12px' }}>
                        {z.zone}
                      </span>
                      {i < journey.length - 1 && <span className="text-muted" style={{ alignSelf: 'center' }}>→</span>}
                    </React.Fragment>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}

const MOCK_VISITORS = Array.from({ length: 12 }, (_, i) => ({
  id: i + 1,
  visitor_id: `VIS-${String(i + 1).padStart(4, '0')}`,
  snapshot: null,
  first_seen: new Date(Date.now() - (i + 1) * 3600000 * 2).toISOString(),
  last_seen: new Date(Date.now() - i * 3600000).toISOString(),
  total_visits: Math.floor(Math.random() * 5 + 1),
  status: i % 5 === 0 ? 'watchlist' : 'active',
}));

const MOCK_HISTORY = [
  { event: 'Entry via Main Entrance', camera_name: 'Main Entrance Cam', timestamp: new Date(Date.now() - 7200000).toISOString() },
  { event: 'Detected in Lobby', camera_name: 'Lobby Cam', timestamp: new Date(Date.now() - 6800000).toISOString() },
  { event: 'Detected in Meeting Room B', camera_name: 'Meeting Room B', timestamp: new Date(Date.now() - 5400000).toISOString() },
  { event: 'Exit via Side Gate', camera_name: 'Side Gate Cam', timestamp: new Date(Date.now() - 3600000).toISOString() },
];

const MOCK_JOURNEY = [
  { zone: 'Main Entrance' }, { zone: 'Lobby' }, { zone: 'Reception' },
  { zone: 'Meeting Room B' }, { zone: 'Cafeteria' }, { zone: 'Exit' },
];
