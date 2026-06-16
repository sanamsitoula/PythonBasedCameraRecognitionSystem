import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';

const AuthContext = createContext(null);

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem('evap_token'));
  const [loading, setLoading] = useState(true);

  const logout = useCallback(() => {
    localStorage.removeItem('evap_token');
    localStorage.removeItem('evap_user');
    setToken(null);
    setUser(null);
    window.location.href = '/login';
  }, []);

  // Validate token on mount
  useEffect(() => {
    const storedToken = localStorage.getItem('evap_token');
    const storedUser = localStorage.getItem('evap_user');
    if (storedToken && storedUser) {
      try {
        setToken(storedToken);
        setUser(JSON.parse(storedUser));
      } catch {
        logout();
      }
    }
    setLoading(false);
  }, [logout]);

  // Token refresh every 25 minutes
  useEffect(() => {
    if (!token) return;
    const interval = setInterval(async () => {
      try {
        const res = await axios.post(
          `${API_BASE}/api/v1/auth/refresh`,
          {},
          { headers: { Authorization: `Bearer ${token}` } }
        );
        const newToken = res.data.access_token;
        localStorage.setItem('evap_token', newToken);
        setToken(newToken);
      } catch {
        logout();
      }
    }, 25 * 60 * 1000);
    return () => clearInterval(interval);
  }, [token, logout]);

  const login = async (username, password, mfaCode = null) => {
    // OAuth2PasswordRequestForm requires application/x-www-form-urlencoded
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);
    if (mfaCode) formData.append('mfa_code', mfaCode);

    const res = await axios.post(`${API_BASE}/api/v1/auth/login`, formData, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });

    const { access_token, mfa_required } = res.data;
    if (mfa_required) return { mfa_required: true };

    // Fetch user profile with the new token
    const meRes = await axios.get(`${API_BASE}/api/v1/auth/me`, {
      headers: { Authorization: `Bearer ${access_token}` },
    });
    const userData = meRes.data;

    localStorage.setItem('evap_token', access_token);
    localStorage.setItem('evap_user', JSON.stringify(userData));
    setToken(access_token);
    setUser(userData);
    toast.success(`Welcome back, ${userData.full_name || userData.username}!`);
    return { success: true };
  };

  return (
    <AuthContext.Provider value={{ user, token, login, logout, loading, isAuthenticated: !!token }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

export default AuthContext;
