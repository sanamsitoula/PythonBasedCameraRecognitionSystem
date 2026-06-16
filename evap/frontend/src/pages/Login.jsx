import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { RiShieldCheckLine, RiEyeLine, RiEyeOffLine, RiLockLine, RiUserLine } from 'react-icons/ri';

export default function LoginPage() {
  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [mfaCode, setMfaCode] = useState('');
  const [showMfa, setShowMfa] = useState(false);
  const [showPwd, setShowPwd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  if (isAuthenticated) { navigate('/'); return null; }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const result = await login(username, password, showMfa ? mfaCode : undefined);
      if (result?.mfa_required) {
        setShowMfa(true);
      } else if (result?.success) {
        navigate('/');
      }
    } catch (err) {
      const detail = err?.response?.data?.detail;
      const msg = Array.isArray(detail)
        ? detail.map((d) => d.msg).join('; ')
        : (typeof detail === 'string' ? detail : err?.response?.data?.message || 'Invalid credentials. Please try again.');
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      className="min-vh-100 d-flex align-items-center justify-content-center"
      style={{ background: '#0d1117', padding: '20px' }}
    >
      {/* Background pattern */}
      <div style={{
        position: 'fixed', inset: 0, zIndex: 0,
        backgroundImage: 'radial-gradient(ellipse at 20% 50%, rgba(31,111,235,0.08) 0%, transparent 60%), radial-gradient(ellipse at 80% 20%, rgba(63,185,80,0.05) 0%, transparent 50%)',
        pointerEvents: 'none',
      }} />

      <div style={{ width: '100%', maxWidth: 420, position: 'relative', zIndex: 1 }}>
        {/* Logo */}
        <div className="text-center mb-4">
          <div
            className="d-inline-flex align-items-center justify-content-center rounded-3 mb-3"
            style={{ width: 64, height: 64, background: 'linear-gradient(135deg, #1f6feb, #0d419d)' }}
          >
            <RiShieldCheckLine size={32} color="#fff" />
          </div>
          <h3 className="text-white fw-bold mb-1">EVAP</h3>
          <p className="text-muted" style={{ fontSize: 14 }}>Enterprise Video Analytics Platform</p>
        </div>

        {/* Card */}
        <div style={{
          background: '#161b22',
          border: '1px solid #30363d',
          borderRadius: 12,
          padding: 32,
        }}>
          <h5 className="text-white fw-semibold mb-4" style={{ fontSize: 16 }}>
            {showMfa ? 'Two-Factor Authentication' : 'Sign in to your account'}
          </h5>

          {error && (
            <div className="alert py-2 mb-3" style={{
              background: 'rgba(248,81,73,0.1)',
              border: '1px solid rgba(248,81,73,0.3)',
              color: '#f85149',
              borderRadius: 8,
              fontSize: 13,
            }}>
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} autoComplete="on">
            {!showMfa ? (
              <>
                <div className="mb-3">
                  <label className="form-label text-muted" style={{ fontSize: 13 }}>Username</label>
                  <div className="position-relative">
                    <RiUserLine
                      size={16}
                      style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#8b949e', zIndex: 1 }}
                    />
                    <input
                      type="text"
                      className="form-control"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      placeholder="Enter username"
                      required
                      autoComplete="username"
                      style={{
                        background: '#0d1117', border: '1px solid #30363d', color: '#e6edf3',
                        paddingLeft: 36, borderRadius: 8,
                      }}
                    />
                  </div>
                </div>
                <div className="mb-4">
                  <label className="form-label text-muted" style={{ fontSize: 13 }}>Password</label>
                  <div className="position-relative">
                    <RiLockLine
                      size={16}
                      style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#8b949e', zIndex: 1 }}
                    />
                    <input
                      type={showPwd ? 'text' : 'password'}
                      className="form-control"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="Enter password"
                      required
                      autoComplete="current-password"
                      style={{
                        background: '#0d1117', border: '1px solid #30363d', color: '#e6edf3',
                        paddingLeft: 36, paddingRight: 40, borderRadius: 8,
                      }}
                    />
                    <button
                      type="button"
                      className="btn btn-link p-0"
                      style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', color: '#8b949e' }}
                      onClick={() => setShowPwd((p) => !p)}
                    >
                      {showPwd ? <RiEyeOffLine size={16} /> : <RiEyeLine size={16} />}
                    </button>
                  </div>
                </div>
              </>
            ) : (
              <div className="mb-4">
                <p className="text-muted mb-3" style={{ fontSize: 13 }}>
                  Enter the 6-digit code from your authenticator app.
                </p>
                <label className="form-label text-muted" style={{ fontSize: 13 }}>MFA Code</label>
                <input
                  type="text"
                  className="form-control text-center"
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  placeholder="000000"
                  maxLength={6}
                  pattern="\d{6}"
                  required
                  style={{
                    background: '#0d1117', border: '1px solid #30363d', color: '#e6edf3',
                    letterSpacing: '0.3em', fontSize: 20, borderRadius: 8,
                  }}
                />
              </div>
            )}

            <button
              type="submit"
              className="btn w-100 fw-semibold"
              disabled={loading}
              style={{
                background: loading ? '#1f6feb88' : 'linear-gradient(135deg, #1f6feb, #0d419d)',
                color: '#fff',
                border: 'none',
                borderRadius: 8,
                padding: '10px 0',
                fontSize: 14,
              }}
            >
              {loading ? (
                <span className="d-flex align-items-center justify-content-center gap-2">
                  <span className="spinner-border spinner-border-sm" />
                  Signing in…
                </span>
              ) : showMfa ? 'Verify Code' : 'Sign In'}
            </button>

            {showMfa && (
              <button type="button" className="btn btn-link w-100 mt-2 text-muted" style={{ fontSize: 13 }}
                onClick={() => setShowMfa(false)}>
                Back to login
              </button>
            )}
          </form>
        </div>

        <p className="text-center text-muted mt-4" style={{ fontSize: 12 }}>
          EVAP v4.0 · Secured with AES-256
        </p>
      </div>
    </div>
  );
}
