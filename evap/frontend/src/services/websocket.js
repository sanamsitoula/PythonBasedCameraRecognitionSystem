import { io } from 'socket.io-client';

const WS_URL = process.env.REACT_APP_WS_URL || 'http://localhost:8000';

class WebSocketService {
  constructor() {
    this.socket = null;
    this.handlers = {};
    this.clientId = `client_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 10;
    this.connected = false;
  }

  connect() {
    if (this.socket?.connected) return;

    const token = localStorage.getItem('evap_token');
    if (!token) return;

    this.socket = io(WS_URL, {
      path: '/ws',
      query: { clientId: this.clientId },
      auth: { token },
      reconnection: true,
      reconnectionAttempts: this.maxReconnectAttempts,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 30000,
      transports: ['websocket', 'polling'],
    });

    this.socket.on('connect', () => {
      this.connected = true;
      this.reconnectAttempts = 0;
      console.log('[WS] Connected:', this.clientId);
      this._emit('connection', { status: 'connected' });
    });

    this.socket.on('disconnect', (reason) => {
      this.connected = false;
      console.log('[WS] Disconnected:', reason);
      this._emit('connection', { status: 'disconnected', reason });
    });

    this.socket.on('alert', (data) => this._emit('onAlert', data));
    this.socket.on('occupancy_update', (data) => this._emit('onOccupancyUpdate', data));
    this.socket.on('camera_status', (data) => this._emit('onCameraStatus', data));
    this.socket.on('person_detected', (data) => this._emit('onPersonDetected', data));
    this.socket.on('vehicle_detected', (data) => this._emit('onVehicleDetected', data));
    this.socket.on('zone_update', (data) => this._emit('onZoneUpdate', data));

    this.socket.on('connect_error', (err) => {
      console.warn('[WS] Connection error:', err.message);
    });
  }

  _emit(eventType, data) {
    const handlers = this.handlers[eventType] || [];
    handlers.forEach((fn) => {
      try { fn(data); } catch (e) { console.error('[WS] Handler error:', e); }
    });
  }

  subscribe(eventType, handler) {
    if (!this.handlers[eventType]) this.handlers[eventType] = [];
    this.handlers[eventType].push(handler);
  }

  unsubscribe(eventType, handler) {
    if (!this.handlers[eventType]) return;
    this.handlers[eventType] = this.handlers[eventType].filter((h) => h !== handler);
  }

  disconnect() {
    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
      this.connected = false;
    }
  }

  isConnected() {
    return this.connected;
  }
}

// Singleton
const wsService = new WebSocketService();
export default wsService;
