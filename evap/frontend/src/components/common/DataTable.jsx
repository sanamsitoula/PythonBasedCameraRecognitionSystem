import React, { useState, useMemo } from 'react';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getPaginationRowModel,
  getFilteredRowModel,
  flexRender,
} from '@tanstack/react-table';
import { RiArrowUpLine, RiArrowDownLine, RiArrowUpDownLine, RiDownloadLine } from 'react-icons/ri';

function SkeletonRow({ cols }) {
  return (
    <tr>
      {Array.from({ length: cols }).map((_, i) => (
        <td key={i}>
          <div
            style={{
              height: 14,
              borderRadius: 4,
              background: 'linear-gradient(90deg, #21262d 25%, #30363d 50%, #21262d 75%)',
              backgroundSize: '200% 100%',
              animation: 'shimmer 1.5s infinite',
              width: `${60 + Math.random() * 30}%`,
            }}
          />
        </td>
      ))}
    </tr>
  );
}

export default function DataTable({
  data = [],
  columns = [],
  loading = false,
  onExport,
  exportLabel = 'Export',
  globalFilter: externalFilter,
  onGlobalFilterChange,
  pageSize: defaultPageSize = 15,
  extra,
}) {
  const [sorting, setSorting] = useState([]);
  const [internalFilter, setInternalFilter] = useState('');
  const [rowSelection, setRowSelection] = useState({});

  const globalFilter = externalFilter !== undefined ? externalFilter : internalFilter;
  const setGlobalFilter = onGlobalFilterChange || setInternalFilter;

  const table = useReactTable({
    data,
    columns,
    state: { sorting, globalFilter, rowSelection },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    initialState: { pagination: { pageSize: defaultPageSize } },
  });

  const { pageIndex, pageSize } = table.getState().pagination;
  const totalRows = table.getFilteredRowModel().rows.length;
  const from = pageIndex * pageSize + 1;
  const to = Math.min(from + pageSize - 1, totalRows);

  return (
    <>
      <style>{`
        @keyframes shimmer {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
      `}</style>

      {/* Toolbar */}
      <div className="d-flex align-items-center gap-2 mb-3 flex-wrap">
        {externalFilter === undefined && (
          <input
            type="search"
            className="form-control form-control-sm"
            placeholder="Search..."
            value={globalFilter}
            onChange={(e) => setGlobalFilter(e.target.value)}
            style={{ background: '#0d1117', border: '1px solid #30363d', color: '#e6edf3', maxWidth: 220 }}
          />
        )}
        {extra}
        <div className="ms-auto d-flex align-items-center gap-2">
          {onExport && (
            <button className="btn btn-sm btn-outline-secondary d-flex align-items-center gap-1" onClick={onExport}>
              <RiDownloadLine size={14} /> {exportLabel}
            </button>
          )}
          <select
            className="form-select form-select-sm"
            style={{ background: '#0d1117', border: '1px solid #30363d', color: '#e6edf3', width: 'auto' }}
            value={pageSize}
            onChange={(e) => table.setPageSize(Number(e.target.value))}
          >
            {[10, 15, 25, 50, 100].map((n) => (
              <option key={n} value={n}>{n} / page</option>
            ))}
          </select>
        </div>
      </div>

      {/* Table */}
      <div style={{ overflowX: 'auto' }}>
        <table className="table table-dark table-hover mb-0" style={{ borderColor: '#30363d', fontSize: 13 }}>
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id} style={{ borderColor: '#30363d' }}>
                {hg.headers.map((h) => (
                  <th
                    key={h.id}
                    onClick={h.column.getToggleSortingHandler()}
                    style={{
                      cursor: h.column.getCanSort() ? 'pointer' : 'default',
                      background: '#161b22',
                      borderColor: '#30363d',
                      color: '#8b949e',
                      fontWeight: 500,
                      whiteSpace: 'nowrap',
                      userSelect: 'none',
                      padding: '10px 12px',
                    }}
                  >
                    <span className="d-flex align-items-center gap-1">
                      {flexRender(h.column.columnDef.header, h.getContext())}
                      {h.column.getCanSort() && (
                        <span style={{ opacity: 0.5, fontSize: 11 }}>
                          {h.column.getIsSorted() === 'asc' ? (
                            <RiArrowUpLine />
                          ) : h.column.getIsSorted() === 'desc' ? (
                            <RiArrowDownLine />
                          ) : (
                            <RiArrowUpDownLine />
                          )}
                        </span>
                      )}
                    </span>
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: 8 }).map((_, i) => <SkeletonRow key={i} cols={columns.length} />)
              : table.getRowModel().rows.length === 0
              ? (
                <tr>
                  <td colSpan={columns.length} className="text-center text-muted py-5" style={{ borderColor: '#30363d' }}>
                    No records found
                  </td>
                </tr>
              )
              : table.getRowModel().rows.map((row) => (
                <tr key={row.id} style={{ borderColor: '#30363d' }}>
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} style={{ borderColor: '#30363d', padding: '10px 12px', verticalAlign: 'middle' }}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalRows > pageSize && (
        <div className="d-flex align-items-center justify-content-between mt-3 flex-wrap gap-2">
          <span className="text-muted" style={{ fontSize: 12 }}>
            {loading ? '—' : `Showing ${from}–${to} of ${totalRows}`}
          </span>
          <div className="d-flex gap-1">
            <button className="btn btn-sm btn-outline-secondary" disabled={!table.getCanPreviousPage()} onClick={() => table.setPageIndex(0)}>«</button>
            <button className="btn btn-sm btn-outline-secondary" disabled={!table.getCanPreviousPage()} onClick={() => table.previousPage()}>‹</button>
            <span className="btn btn-sm btn-secondary disabled" style={{ minWidth: 36 }}>{pageIndex + 1}</span>
            <button className="btn btn-sm btn-outline-secondary" disabled={!table.getCanNextPage()} onClick={() => table.nextPage()}>›</button>
            <button className="btn btn-sm btn-outline-secondary" disabled={!table.getCanNextPage()} onClick={() => table.setPageIndex(table.getPageCount() - 1)}>»</button>
          </div>
        </div>
      )}
    </>
  );
}
