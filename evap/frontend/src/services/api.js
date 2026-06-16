import axios from 'axios';
import toast from 'react-hot-toast';

const BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
});

// Request interceptor — attach JWT
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('evap_token');
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor — handle auth errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;
    if (status === 401) {
      localStorage.removeItem('evap_token');
      localStorage.removeItem('evap_user');
      window.location.href = '/login';
    } else if (status === 403) {
      toast.error('Access denied. You do not have permission to perform this action.');
    } else if (status === 500) {
      toast.error('Server error. Please try again later.');
    }
    return Promise.reject(error);
  }
);

// Generic CRUD factory
const makeCRUD = (resource) => ({
  getAll: (params) => api.get(`/${resource}`, { params }),
  getById: (id) => api.get(`/${resource}/${id}`),
  create: (data) => api.post(`/${resource}`, data),
  update: (id, data) => api.put(`/${resource}/${id}`, data),
  delete: (id) => api.delete(`/${resource}/${id}`),
});

export const authAPI = {
  login: (data) => api.post('/auth/login', data),
  logout: () => api.post('/auth/logout'),
  refresh: () => api.post('/auth/refresh'),
  me: () => api.get('/auth/me'),
};

export const camerasAPI = {
  ...makeCRUD('cameras'),
  getStatus: () => api.get('/cameras/status'),
  getStreamHealth: (id) => api.get(`/cameras/${id}/health`),
  restartStream: (id) => api.post(`/cameras/${id}/restart`),
};

export const employeesAPI = {
  ...makeCRUD('employees'),
  uploadPhotos: (id, formData) =>
    api.post(`/employees/${id}/photos`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  deletePhoto: (id, filename) => api.delete(`/employees/${id}/photos/${filename}`),
  triggerEnrollment: (id) => api.post(`/employees/${id}/enroll`),
  getEnrollmentStatus: (id) => api.get(`/employees/${id}/enrollment-status`),
  exportCSV: (params) =>
    api.get('/employees/export/csv', { params, responseType: 'blob' }),
};

export const visitorsAPI = {
  ...makeCRUD('visitors'),
  getHistory: (id) => api.get(`/visitors/${id}/history`),
  getJourney: (id) => api.get(`/visitors/${id}/journey`),
  addToWatchlist: (id) => api.post(`/visitors/${id}/watchlist`),
};

export const vehiclesAPI = {
  ...makeCRUD('vehicles'),
  getActive: () => api.get('/vehicles/active'),
  getLicensePlateLog: (params) => api.get('/vehicles/license-plates', { params }),
  getParkingAnalytics: (params) => api.get('/vehicles/parking-analytics', { params }),
};

export const attendanceAPI = {
  ...makeCRUD('attendance'),
  getByDate: (date, params) => api.get('/attendance/by-date', { params: { date, ...params } }),
  getSummary: (params) => api.get('/attendance/summary', { params }),
  getMonthlyHeatmap: (params) => api.get('/attendance/heatmap', { params }),
  exportPDF: (params) => api.get('/attendance/export/pdf', { params, responseType: 'blob' }),
  exportExcel: (params) => api.get('/attendance/export/excel', { params, responseType: 'blob' }),
};

export const alertsAPI = {
  ...makeCRUD('alerts'),
  acknowledge: (id) => api.post(`/alerts/${id}/acknowledge`),
  acknowledgeAll: () => api.post('/alerts/acknowledge-all'),
  getStats: (params) => api.get('/alerts/stats', { params }),
  getUnreadCount: () => api.get('/alerts/unread-count'),
};

export const analyticsAPI = {
  getOccupancyTrend: (params) => api.get('/analytics/occupancy-trend', { params }),
  getHeatmap: (params) => api.get('/analytics/heatmap', { params }),
  getCrossCamera: (params) => api.get('/analytics/cross-camera', { params }),
  getBehaviorEvents: (params) => api.get('/analytics/behavior-events', { params }),
  getDepartmentAnalytics: (params) => api.get('/analytics/departments', { params }),
};

export const reportsAPI = {
  generate: (data) => api.post('/reports/generate', data),
  getStatus: (id) => api.get(`/reports/${id}/status`),
  download: (id) =>
    api.get(`/reports/${id}/download`, { responseType: 'blob' }),
  getAll: (params) => api.get('/reports', { params }),
  delete: (id) => api.delete(`/reports/${id}`),
};

export const dashboardAPI = {
  getStats: () => api.get('/dashboard/stats'),
  getOccupancyHistory: () => api.get('/dashboard/occupancy-history'),
  getRecentDetections: () => api.get('/dashboard/recent-detections'),
  getVehicleAnalytics: () => api.get('/dashboard/vehicle-analytics'),
};

export const floormapAPI = {
  getZones: (params) => api.get('/floormap/zones', { params }),
  getPersonLocations: (params) => api.get('/floormap/persons', { params }),
  getHeatmap: (params) => api.get('/floormap/heatmap', { params }),
};

export default api;
