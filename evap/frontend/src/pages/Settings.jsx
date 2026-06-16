import React, { useState } from 'react';
import { RiSettings3Line, RiSaveLine, RiShieldCheckLine, RiBellLine, RiDatabaseLine, RiVideoLine } from 'react-icons/ri';
import toast from 'react-hot-toast';

const INPUT = { background: '#0d1117', border: '1px solid #30363d', color: '#e6edf3', borderRadius: 6 };
const CARD  = { background: '#161b22', border: '1px solid #30363d', borderRadius: 12, padding: '20px', marginBottom: 20 };

function Section({ icon: Icon, title, children }) {
  return (
    <div style={CARD}>
      <div className="d-flex align-items-center gap-2 mb-3">
        <Icon size={18} color="#58a6ff" />
        <h6 className="mb-0 fw-bold">{title}</h6>
      </div>
      {children}
    </div>
  );
}

function Field({ label, type = 'text', value, onChange, hint }) {
  return (
    <div className="mb-3">
      <label className="form-label small text-muted mb-1">{label}</label>
      {type === 'select' ? (
        <select className="form-select form-select-sm" style={INPUT} value={value} onChange={e => onChange(e.target.value)}>
          {hint && hint.map(opt => <option key={opt} value={opt}>{opt}</option>)}
        </select>
      ) : type === 'toggle' ? (
        <div className="form-check form-switch mt-1">
          <input className="form-check-input" type="checkbox" checked={value} onChange={e => onChange(e.target.checked)} />
        </div>
      ) : (
        <input type={type} className="form-control form-control-sm" style={INPUT} value={value} onChange={e => onChange(e.target.value)} />
      )}
      {typeof hint === 'string' && <div className="form-text text-muted" style={{ fontSize: 11 }}>{hint}</div>}
    </div>
  );
}

export default function SettingsPage() {
  const [general, setGeneral] = useState({
    siteName: 'EVAP Enterprise',
    timezone: 'Asia/Kathmandu',
    language: 'en',
    retentionDays: '90',
  });

  const [alerts, setAlerts] = useState({
    emailEnabled: false,
    emailTo: '',
    slackEnabled: false,
    slackWebhook: '',
    crowdThreshold: '50',
    loiterSeconds: '120',
  });

  const [camera, setCamera] = useState({
    defaultFps: '15',
    snapshotInterval: '30',
    recordOnAlert: true,
    aiAnalysisEnabled: true,
    aiIntervalSeconds: '60',
  });

  const [security, setSecurity] = useState({
    sessionTimeout: '30',
    mfaEnabled: false,
    auditLog: true,
  });

  function save(section) {
    toast.success(`${section} settings saved`);
  }

  const g = (key, val) => setGeneral(s => ({ ...s, [key]: val }));
  const a = (key, val) => setAlerts(s => ({ ...s, [key]: val }));
  const c = (key, val) => setCamera(s => ({ ...s, [key]: val }));
  const sec = (key, val) => setSecurity(s => ({ ...s, [key]: val }));

  return (
    <div style={{ padding: '24px', color: '#e6edf3', maxWidth: 800 }}>
      <div className="d-flex align-items-center gap-2 mb-4">
        <RiSettings3Line size={22} color="#58a6ff" />
        <h4 className="mb-0 fw-bold">Settings</h4>
      </div>

      <Section icon={RiSettings3Line} title="General">
        <div className="row g-3">
          <div className="col-md-6"><Field label="Site Name" value={general.siteName} onChange={v => g('siteName', v)} /></div>
          <div className="col-md-6"><Field label="Timezone" type="select" value={general.timezone} onChange={v => g('timezone', v)} hint={['Asia/Kathmandu', 'UTC', 'America/New_York', 'Europe/London', 'Asia/Kolkata']} /></div>
          <div className="col-md-6"><Field label="Language" type="select" value={general.language} onChange={v => g('language', v)} hint={['en', 'ne', 'hi']} /></div>
          <div className="col-md-6"><Field label="Data Retention (days)" type="number" value={general.retentionDays} onChange={v => g('retentionDays', v)} hint="Snapshots and logs older than this are auto-deleted." /></div>
        </div>
        <button className="btn btn-sm btn-primary" onClick={() => save('General')}><RiSaveLine className="me-1" />Save General</button>
      </Section>

      <Section icon={RiBellLine} title="Alert Notifications">
        <div className="row g-3">
          <div className="col-md-6">
            <Field label="Email Alerts" type="toggle" value={alerts.emailEnabled} onChange={v => a('emailEnabled', v)} />
            <Field label="Email Recipients" type="email" value={alerts.emailTo} onChange={v => a('emailTo', v)} hint="Comma-separated email addresses" />
          </div>
          <div className="col-md-6">
            <Field label="Slack Alerts" type="toggle" value={alerts.slackEnabled} onChange={v => a('slackEnabled', v)} />
            <Field label="Slack Webhook URL" value={alerts.slackWebhook} onChange={v => a('slackWebhook', v)} hint="https://hooks.slack.com/..." />
          </div>
          <div className="col-md-6"><Field label="Crowd Alert Threshold (persons)" type="number" value={alerts.crowdThreshold} onChange={v => a('crowdThreshold', v)} /></div>
          <div className="col-md-6"><Field label="Loitering Alert (seconds)" type="number" value={alerts.loiterSeconds} onChange={v => a('loiterSeconds', v)} /></div>
        </div>
        <button className="btn btn-sm btn-primary" onClick={() => save('Alert')}><RiSaveLine className="me-1" />Save Alerts</button>
      </Section>

      <Section icon={RiVideoLine} title="Camera & AI">
        <div className="row g-3">
          <div className="col-md-6"><Field label="Default FPS Cap" type="number" value={camera.defaultFps} onChange={v => c('defaultFps', v)} /></div>
          <div className="col-md-6"><Field label="Snapshot Interval (seconds)" type="number" value={camera.snapshotInterval} onChange={v => c('snapshotInterval', v)} /></div>
          <div className="col-md-6">
            <Field label="Record on Alert" type="toggle" value={camera.recordOnAlert} onChange={v => c('recordOnAlert', v)} />
          </div>
          <div className="col-md-6">
            <Field label="AI Scene Analysis" type="toggle" value={camera.aiAnalysisEnabled} onChange={v => c('aiAnalysisEnabled', v)} />
            <Field label="AI Analysis Interval (seconds)" type="number" value={camera.aiIntervalSeconds} onChange={v => c('aiIntervalSeconds', v)} />
          </div>
        </div>
        <button className="btn btn-sm btn-primary" onClick={() => save('Camera')}><RiSaveLine className="me-1" />Save Camera</button>
      </Section>

      <Section icon={RiShieldCheckLine} title="Security">
        <div className="row g-3">
          <div className="col-md-6"><Field label="Session Timeout (minutes)" type="number" value={security.sessionTimeout} onChange={v => sec('sessionTimeout', v)} /></div>
          <div className="col-md-6"><Field label="Multi-Factor Authentication" type="toggle" value={security.mfaEnabled} onChange={v => sec('mfaEnabled', v)} /></div>
          <div className="col-md-6"><Field label="Audit Log" type="toggle" value={security.auditLog} onChange={v => sec('auditLog', v)} hint="Record all admin actions to audit_log table." /></div>
        </div>
        <button className="btn btn-sm btn-primary" onClick={() => save('Security')}><RiSaveLine className="me-1" />Save Security</button>
      </Section>

      <Section icon={RiDatabaseLine} title="Database Info">
        <div className="row g-2" style={{ fontSize: 13 }}>
          {[
            ['CCTV Analytics DB', 'cctv_analytics @ localhost:5432', '#3fb950'],
            ['EVAP Web DB',       'evap @ localhost:5432',           '#58a6ff'],
            ['Redis Cache',       'localhost:6379',                  '#d29922'],
          ].map(([label, val, color]) => (
            <div className="col-12 d-flex justify-content-between py-1" key={label} style={{ borderBottom: '1px solid #21262d' }}>
              <span className="text-muted">{label}</span>
              <code style={{ color, fontSize: 12 }}>{val}</code>
            </div>
          ))}
        </div>
        <p className="text-muted mt-3 mb-0" style={{ fontSize: 11 }}>
          Database credentials are loaded from <code>evap/backend/.env</code>. Restart the backend after changes.
        </p>
      </Section>
    </div>
  );
}
