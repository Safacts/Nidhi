import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { jwtDecode } from 'jwt-decode';
import './App.css';
import logo from './logo.png';

/**
 * NIDHI - SANCTUARY EDITION
 * -------------------------
 * A premium self-service DBaaS portal.
 */

// --- API CLIENT CONFIGURATION ---
const nidhiApi = axios.create({ baseURL: '/nidhi/api' });
const authApi = axios.create({ baseURL: '/aacharya/api/v1' });

nidhiApi.interceptors.request.use((config) => {
  const token = localStorage.getItem('nidhi_token');
  if (token) {
    try {
      const decoded = jwtDecode(token);
      config.headers['Authorization'] = `Bearer ${token}`;
      config.headers['X-User-Id'] = decoded.user_id;
      config.headers['X-User-Name'] = decoded.username;
      config.headers['X-User-Role'] = decoded.role;
      config.headers['X-User-College-Id'] = decoded.subdomain;
    } catch (e) { console.error("Session sync error", e); }
  }
  return config;
});

// --- UI COMPONENTS ---

const IconLeaf = ({ size = 20, className = "" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.5 21 2c-2.5 4-3 5.5-4.1 11.2A7 7 0 0 1 11 20z"></path>
    <path d="M11 20v-5"></path>
  </svg>
);

const Notification = ({ notification, onClear }) => {
  useEffect(() => {
    if (notification.message) {
      const t = setTimeout(onClear, 4000);
      return () => clearTimeout(t);
    }
  }, [notification, onClear]);

  if (!notification.message) return null;
  return (
    <div className={`notification glass fixed top-6 left-1/2 -translate-x-1/2 z-[1000] px-8 py-3.5 rounded-full shadow-2xl border-white/60 animate-slide-down flex items-center gap-3`}>
      <div className={`w-2 h-2 rounded-full ${notification.type === 'success' ? 'bg-sage-500' : 'bg-red-500'} animate-pulse`}></div>
      <span className="text-sm font-bold tracking-tight text-ocean-900">{notification.message}</span>
    </div>
  );
};

function App() {
  const [user, setUser] = useState(null);
  const [isLoggedIn, setIsLoggedIn] = useState(!!localStorage.getItem('nidhi_token'));
  const [theme, setTheme] = useState(localStorage.getItem('nidhi_theme') || 'light');
  const [notif, setNotif] = useState({ message: '', type: '' });

  useEffect(() => {
    const stored = localStorage.getItem('nidhi_user');
    if (stored && isLoggedIn && stored !== 'undefined') setUser(JSON.parse(stored));
  }, [isLoggedIn]);

  useEffect(() => {
    document.body.className = `${theme}-mode`;
    localStorage.setItem('nidhi_theme', theme);
  }, [theme]);

  const showNotif = (message, type = 'error') => setNotif({ message, type });
  
  const handleLogin = (userData, tokenData) => {
    setUser(userData);
    setIsLoggedIn(true);
    localStorage.setItem('nidhi_user', JSON.stringify(userData));
    localStorage.setItem('nidhi_token', tokenData.access);
  };

  const handleLogout = () => {
    setUser(null);
    setIsLoggedIn(false);
    localStorage.clear();
  };

  return (
    <div className="App min-h-screen flex flex-col">
      <Notification notification={notif} onClear={() => setNotif({ message: '', type: '' })} />
      
      {!isLoggedIn || !user ? (
        <Login onLogin={handleLogin} showNotif={showNotif} />
      ) : (
        <div className="flex flex-col flex-1">
          <nav className="dashboard-header glass">
            <div className="flex items-center gap-4">
              <img src={logo} alt="Nidhi" className="h-10 md:h-12 w-auto" />
              <div className="h-8 w-[1px] bg-white/20 hidden md:block"></div>
              <h1 className="text-lg font-bold tracking-tight hidden md:block opacity-80 uppercase text-[10px]">Managed Sanctuary</h1>
            </div>
            
            <div className="flex items-center gap-6">
              <button onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')} className="p-2 bg-transparent shadow-none hover:scale-110">
                {theme === 'light' ? '🌙' : '☀️'}
              </button>
              <div className="text-right hidden sm:block">
                <p className="text-[9px] font-black uppercase tracking-[0.2em] opacity-40">{user.role}</p>
                <p className="text-sm font-bold text-ocean-800">{user.username}</p>
              </div>
              <button onClick={handleLogout} className="action-button-danger text-[10px] uppercase font-bold tracking-widest px-5 py-2.5">Logout</button>
            </div>
          </nav>

          <main className="main-container flex-1 animate-fade-in py-12">
            {user.role.includes('admin') ? (
              <AdminDashboard showNotif={showNotif} />
            ) : (
              <StudentDashboard user={user} showNotif={showNotif} />
            )}
          </main>

          <footer className="py-12 text-center opacity-30 text-[10px] font-bold uppercase tracking-[0.3em]">
            &copy; 2026 Nidhi DBaaS • Built for Excellence
          </footer>
        </div>
      )}
    </div>
  );
}

// --- VIEWS ---

const Login = ({ onLogin, showNotif }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await nidhiApi.post('/login/', { username, password });
      onLogin(res.data.user, res.data.tokens);
    } catch (err) {
      showNotif('Access denied. Please check your credentials.');
    } finally { setLoading(false); }
  };

  return (
    <div className="flex-1 flex items-center justify-center p-6 bg-gradient-to-br from-sage-50 to-lavender-50">
      <div className="glass p-12 rounded-[4rem] w-full max-w-md animate-slide-up shadow-2xl">
        <div className="text-center mb-12">
          <div className="w-20 h-20 bg-white/50 rounded-[2.5rem] flex items-center justify-center mx-auto mb-6 shadow-sm border-white">
            <img src={logo} alt="Logo" className="h-10" />
          </div>
          <h2 className="text-2xl font-bold tracking-tight text-ocean-900">Welcome Back</h2>
          <p className="text-xs text-ocean-500 mt-3 font-medium uppercase tracking-widest opacity-60">Database-as-a-Service</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-8">
          <div className="form-group">
            <label>College Identity</label>
            <input placeholder="Email or Roll No" value={username} onChange={(e) => setUsername(e.target.value)} required />
          </div>
          <div className="form-group">
            <label>Security Key</label>
            <input type="password" placeholder="••••••••" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </div>
          <button type="submit" disabled={loading} className="w-full py-4.5 rounded-[1.5rem] font-bold text-xs uppercase tracking-[0.2em] shadow-xl">
            {loading ? 'Authenticating...' : 'Enter Platform'}
          </button>
        </form>
      </div>
    </div>
  );
};

const SQLShell = ({ db, onClose, showNotif }) => {
  const [password, setPassword] = useState('');
  const [query, setQuery] = useState('SELECT * FROM pg_catalog.pg_tables;');
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleRun = async () => {
    setLoading(true);
    try {
      const res = await nidhiApi.post(`/requests/shell/${db.id}/`, { password, query });
      setResults(res.data);
    } catch (e) { showNotif(e.response?.data?.error || "Execution failed."); }
    finally { setLoading(false); }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content glass p-8 rounded-[3rem]" onClick={e => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-bold">SQL Shell: {db.db_name}</h2>
          <button onClick={onClose} className="p-2 bg-transparent text-ocean-900 text-xl">&times;</button>
        </div>
        <div className="space-y-4">
          <div className="form-group">
            <label>Database Password</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Enter your DB password" />
          </div>
          <div className="form-group">
            <label>SQL Query</label>
            <textarea 
              className="w-full p-4 rounded-2xl bg-white/50 border border-white/50 font-mono text-sm min-h-[100px]"
              value={query} 
              onChange={e => setQuery(e.target.value)} 
            />
          </div>
          <button onClick={handleRun} disabled={loading} className="w-full">
            {loading ? 'Running...' : 'Execute Query'}
          </button>
        </div>
        
        {results && (
          <div className="mt-8 overflow-x-auto">
            <h3 className="font-bold mb-4">Results</h3>
            {results.results ? (
              <table className="sql-results-table">
                <thead>
                  <tr>{results.columns.map(c => <th key={c}>{c}</th>)}</tr>
                </thead>
                <tbody>
                  {results.results.map((row, i) => (
                    <tr key={i}>{results.columns.map(c => <td key={c}>{String(row[c])}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            ) : <p className="text-sage-600 font-bold">{results.message}</p>}
          </div>
        )}
      </div>
    </div>
  );
};

const StudentDashboard = ({ showNotif }) => {
  const [requests, setRequests] = useState([]);
  const [dbName, setDbName] = useState('');
  const [loading, setLoading] = useState(false);
  const [activeShell, setActiveShell] = useState(null);

  const fetch = useCallback(async () => {
    try {
      const res = await nidhiApi.get('/requests/my/');
      setRequests(res.data);
    } catch (e) { showNotif("Resource sync failed."); }
  }, [showNotif]);

  useEffect(() => { fetch(); }, [fetch]);

  const handleRequest = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await nidhiApi.post('/requests/create/', { db_name: dbName });
      setDbName('');
      showNotif("Provisioning request logged.", "success");
      fetch();
    } catch (e) { showNotif(e.response?.data?.error || "Provisioning error."); }
    finally { setLoading(false); }
  };

  const handleBackup = async (db) => {
    const password = prompt(`Enter password for ${db.db_name} to generate backup:`);
    if (!password) return;
    try {
      const res = await nidhiApi.post(`/requests/backup/${db.id}/`, { password });
      const blob = new Blob([res.data.sql_content], { type: 'text/plain' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${db.db_name}_backup.sql`;
      a.click();
      showNotif("Backup downloaded successfully.", "success");
    } catch (e) { showNotif(e.response?.data?.error || "Backup failed."); }
  };

  return (
    <div className="max-w-5xl mx-auto space-y-16">
      {activeShell && <SQLShell db={activeShell} onClose={() => setActiveShell(null)} showNotif={showNotif} />}
      
      <section className="glass p-12 rounded-[3.5rem] border-white/60 relative overflow-hidden group">
        <div className="absolute top-0 right-0 p-12 opacity-5 pointer-events-none group-hover:opacity-10 transition-opacity">
          <IconLeaf size={120} />
        </div>
        <div className="relative z-10">
          <h2 className="text-xl font-bold mb-8 flex items-center gap-3">
            <IconLeaf size={22} className="text-sage-500" /> 
            <span>Provision Resource</span>
          </h2>
          <form onSubmit={handleRequest} className="flex flex-col md:flex-row gap-6 items-end">
            <div className="flex-1 form-group mb-0 w-full">
              <label>Database Instance Name</label>
              <input 
                placeholder="e.g. ecommerce-lab"
                value={dbName} 
                onChange={e => setDbName(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))} 
                required 
              />
            </div>
            <button type="submit" disabled={loading} className="h-[58px] whitespace-nowrap px-10 rounded-[1.4rem]">
              {loading ? 'Processing...' : 'Request Instance'}
            </button>
          </form>
        </div>
      </section>

      <section>
        <div className="flex justify-between items-center mb-10 px-4">
          <h2 className="text-2xl font-bold tracking-tight">Your Managed Instances</h2>
          <div className="px-6 py-2.5 glass rounded-full border-white/40">
            <span className="text-[10px] font-bold uppercase tracking-widest text-sage-600">{requests.length} / 5 Resources</span>
          </div>
        </div>
        
        <div className="database-card-container">
          {requests.map(req => (
            <div key={req.id} className="database-card glass p-8 rounded-[2.8rem] hover:-translate-y-2 transition-all duration-300 border-white/80">
              <div className="flex justify-between items-start mb-8">
                <div className="max-w-[70%]">
                  <h3 className="font-bold text-lg text-ocean-900" title={req.db_name}>{req.db_name}</h3>
                  <p className="text-[10px] opacity-40 font-mono">{req.db_user}</p>
                </div>
                <span className={`status status-${req.status} px-4 py-1.5 rounded-full text-[9px] font-black uppercase tracking-widest`}>{req.status}</span>
              </div>
              
              {req.status === 'approved' && (
                <div className="space-y-4 mb-8 text-[12px] font-medium opacity-70 bg-white/40 p-6 rounded-[1.8rem] border border-white/50">
                  <div className="flex justify-between"><span className="opacity-50">Host</span><span>117.244.0.71</span></div>
                  <div className="flex justify-between"><span className="opacity-50">Port</span><span>5435</span></div>
                  <div className="flex justify-between"><span className="opacity-50">Database</span><span>{req.db_name}</span></div>
                  <div className="flex justify-between"><span className="opacity-50">User</span><span>{req.db_user}</span></div>
                </div>
              )}

              <div className="flex flex-wrap gap-2">
                {req.status === 'approved' && req.db_password_temp && (
                  <button className="text-[10px] font-bold uppercase tracking-widest flex-1 py-3" onClick={async () => {
                    const res = await nidhiApi.post(`/requests/reveal/${req.id}/`);
                    alert(`ACCESS KEY: ${res.data.db_password}\n(This will never be shown again.)`);
                    fetch();
                  }}>Reveal</button>
                )}
                {req.status === 'approved' && (
                  <>
                    <button className="action-button-secondary text-[10px] font-bold uppercase tracking-widest px-4 py-3" onClick={() => setActiveShell(req)}>Shell</button>
                    <button className="action-button-secondary text-[10px] font-bold uppercase tracking-widest px-4 py-3" onClick={() => handleBackup(req)}>Backup</button>
                    <button className="action-button-danger text-[10px] font-bold uppercase tracking-widest px-4 py-3" onClick={async () => {
                      if(window.confirm(`Permanently delete ${req.db_name}?`)) {
                        await nidhiApi.post(`/requests/delete/${req.id}/`);
                        showNotif("Instance deleted.", "success");
                        fetch();
                      }
                    }}>Delete</button>
                  </>
                )}
              </div>
            </div>
          ))}
          {requests.length === 0 && (
            <div className="col-span-full py-24 text-center glass rounded-[4rem] opacity-40 border-dashed border-2">
              <p className="text-sm font-medium tracking-widest uppercase">No active instances in your workspace</p>
            </div>
          )}
        </div>
      </section>
    </div>
  );
};

const AdminDashboard = ({ showNotif }) => {
  const [pending, setPending] = useState([]);
  const fetch = useCallback(async () => {
    try {
      const res = await nidhiApi.get('/admin/requests/pending/');
      setPending(res.data);
    } catch (e) { showNotif("Admin sync failed."); }
  }, [showNotif]);

  useEffect(() => { fetch(); }, [fetch]);

  const handleApprove = async (id) => {
    try {
      await nidhiApi.post(`/admin/requests/approve/${id}/`);
      showNotif("Resource approved and active.", "success");
      fetch();
    } catch (e) { showNotif("Approval failed."); }
  };

  return (
    <div className="max-w-4xl mx-auto">
      <div className="glass p-12 rounded-[4rem] border-white/60">
        <h2 className="text-2xl font-bold mb-12 tracking-tight">Access Control & Oversight</h2>
        <div className="space-y-6">
          {pending.map(req => (
            <div key={req.id} className="flex justify-between items-center p-8 bg-white/40 rounded-[2.5rem] border border-white/80 hover:bg-white/60 transition-colors">
              <div>
                <p className="font-bold text-lg text-ocean-900">{req.db_name}</p>
                <p className="text-[10px] font-bold uppercase tracking-widest opacity-40 mt-1">Requester: {req.student_username}</p>
              </div>
              <button onClick={() => handleApprove(req.id)} className="text-[10px] font-black uppercase tracking-[0.2em] px-8 py-3.5 shadow-xl">Approve</button>
            </div>
          ))}
          {pending.length === 0 && (
            <div className="py-20 text-center opacity-30 italic font-medium tracking-widest uppercase text-sm">
              No pending oversight actions.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default App;
