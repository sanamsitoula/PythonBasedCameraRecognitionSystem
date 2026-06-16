import React, { useState } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import Navbar from './Navbar';

export default function Layout() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  return (
    <div className="d-flex" style={{ minHeight: '100vh', background: '#0d1117' }}>
      <Sidebar collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed((p) => !p)} />
      <div
        className="d-flex flex-column flex-grow-1"
        style={{
          marginLeft: sidebarCollapsed ? '70px' : '260px',
          transition: 'margin-left 0.25s ease',
          minWidth: 0,
        }}
      >
        <Navbar sidebarCollapsed={sidebarCollapsed} onToggleSidebar={() => setSidebarCollapsed((p) => !p)} />
        <main
          className="flex-grow-1 p-3"
          style={{ marginTop: '60px', overflowX: 'hidden' }}
        >
          <Outlet />
        </main>
      </div>
    </div>
  );
}
