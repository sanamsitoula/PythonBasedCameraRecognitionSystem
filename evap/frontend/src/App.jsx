import React, { Suspense, lazy } from 'react';
import { Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { useAuth } from './context/AuthContext';
import Layout from './components/Layout/Layout';

// Lazy-loaded pages
const LoginPage = lazy(() => import('./pages/Login'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const CamerasPage = lazy(() => import('./pages/Cameras'));
const EmployeesPage = lazy(() => import('./pages/Employees'));
const EmployeeDetailPage = lazy(() => import('./pages/EmployeeDetail'));
const VisitorsPage = lazy(() => import('./pages/Visitors'));
const VehiclesPage = lazy(() => import('./pages/Vehicles'));
const AttendancePage = lazy(() => import('./pages/Attendance'));
const AlertsPage = lazy(() => import('./pages/Alerts'));
const FloorMapPage = lazy(() => import('./pages/FloorMap'));
const AnalyticsPage = lazy(() => import('./pages/Analytics'));
const ReportsPage = lazy(() => import('./pages/Reports'));
const SettingsPage = lazy(() => import('./pages/Settings'));

function PageLoader() {
  return (
    <div className="d-flex align-items-center justify-content-center" style={{ height: '60vh' }}>
      <div className="spinner-border text-primary" role="status">
        <span className="visually-hidden">Loading...</span>
      </div>
    </div>
  );
}

function ProtectedRoute() {
  const { isAuthenticated, loading } = useAuth();
  if (loading) return <PageLoader />;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <Outlet />;
}

export default function App() {
  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route element={<ProtectedRoute />}>
          <Route element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="cameras" element={<CamerasPage />} />
            <Route path="employees" element={<EmployeesPage />} />
            <Route path="employees/:employee_id" element={<EmployeeDetailPage />} />
            <Route path="visitors" element={<VisitorsPage />} />
            <Route path="vehicles" element={<VehiclesPage />} />
            <Route path="attendance" element={<AttendancePage />} />
            <Route path="alerts" element={<AlertsPage />} />
            <Route path="floor-map" element={<FloorMapPage />} />
            <Route path="analytics" element={<AnalyticsPage />} />
            <Route path="reports" element={<ReportsPage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
