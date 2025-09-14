// frontend/src/App.js
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './App.css';

// --- API Configuration ---
const API_URL = 'http://localhost:8001/api';
// const API_URL = 'https://sunbeam-smiling-trout.ngrok-free.app/api/';
const apiClient = axios.create({
  baseURL: API_URL,
});

// --- Main App Component ---
function App() {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem('nidhi_token'));

  // This effect runs on app load to check if we have a stored user
  useEffect(() => {
    const storedUser = localStorage.getItem('nidhi_user');
    if (storedUser && token) {
      setUser(JSON.parse(storedUser));
    }
  }, [token]);

  const handleLogin = (userData, tokenData) => {
    setUser(userData);
    setToken(tokenData.access);
    localStorage.setItem('nidhi_user', JSON.stringify(userData));
    localStorage.setItem('nidhi_token', tokenData.access);
  };

  const handleLogout = () => {
    setUser(null);
    setToken(null);
    localStorage.removeItem('nidhi_user');
    localStorage.removeItem('nidhi_token');
  };

  if (!user) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <div className="App">
      <DashboardHeader user={user} onLogout={handleLogout} />
      {user.role === 'admin' ? <AdminDashboard token={token} user={user} /> : <StudentDashboard token={token} user={user} />}
    </div>
  );
}

// --- Header Component ---
const DashboardHeader = ({ user, onLogout }) => (
  <header className="dashboard-header">
    <h1>Nidhi Dashboard</h1>
    <div>
      <span>Welcome, {user.username} ({user.role})</span>
      <button onClick={onLogout} className="logout-button">Logout</button>
    </div>
  </header>
);

// --- Login Component ---
const Login = ({ onLogin }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const response = await apiClient.post('/login/', { username, password });
      onLogin(response.data.user, response.data.tokens);
    } catch (err) {
      setError('Login failed. Please check your credentials.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container">
      <h2>Nidhi Login</h2>
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label>Username</label>
          <input type="text" value={username} onChange={(e) => setUsername(e.target.value)} required />
        </div>
        <div className="form-group">
          <label>Password</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </div>
        <button type="submit" disabled={loading}>{loading ? 'Logging in...' : 'Login'}</button>
        {error && <p className="error-message">{error}</p>}
      </form>
    </div>
  );
};


// --- Student Dashboard ---
const StudentDashboard = ({ token, user }) => {
  const [requests, setRequests] = useState([]);
  const [dbName, setDbName] = useState('');
  const [loading, setLoading] = useState(false);

  const fetchRequests = React.useCallback(async () => {
      const headers = { 'X-User-Id': user.id, 'X-User-Role': user.role };
      const response = await apiClient.get('/requests/my/', { headers });
      setRequests(response.data);
  }, [user.id, user.role]);

  useEffect(() => {
      fetchRequests();
  }, [fetchRequests]);

  const handleRequestSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const headers = { 'X-User-Id': user.id, 'X-User-Name': user.username, 'X-User-Role': user.role };
      await apiClient.post('/requests/create/', { db_name: dbName }, { headers });
      setDbName('');
      fetchRequests(); // Refresh the list
    } catch (error) {
      alert('Failed to create request. Is the name already taken?');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div className="dashboard-section">
        <h2>Request a New Database</h2>
        <form onSubmit={handleRequestSubmit}>
          <div className="form-group">
            <label>New Database Name (e.g., my-project-name)</label>
            <input type="text" value={dbName} onChange={(e) => setDbName(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))} required />
          </div>
          <button type="submit" disabled={loading}>{loading ? 'Requesting...' : 'Submit Request'}</button>
        </form>
      </div>
      <div className="dashboard-section">
        <h2>My Database Requests</h2>
        <ul className="request-list">
          {requests.map(req => (
            <li key={req.id} className="request-item">
              <span>{req.db_name}</span>
              <span className={`status status-${req.status}`}>{req.status}</span>
            </li>
          ))}
        </ul>
      </div>
    </>
  );
};

// --- Admin Dashboard ---
const AdminDashboard = ({ token, user }) => {
  const [pendingRequests, setPendingRequests] = useState([]);
  const [approvedCredentials, setApprovedCredentials] = useState(null);

  const fetchPending = React.useCallback(async () => {
      const headers = { 'X-User-Id': user.id, 'X-User-Name': user.username, 'X-User-Role': user.role };
      const response = await apiClient.get('/admin/requests/pending/', { headers });
      setPendingRequests(response.data);
  }, [user.id, user.username, user.role]);

  useEffect(() => {
      fetchPending();
  }, [fetchPending]);

  const handleApprove = async (requestId) => {
    try {
      const headers = { 'X-User-Id': user.id, 'X-User-Name': user.username, 'X-User-Role': user.role };
      const response = await apiClient.post(`/admin/requests/approve/${requestId}/`, {}, { headers });
      setApprovedCredentials(response.data);
      fetchPending(); // Refresh the list
    } catch (error) {
      alert('Failed to approve request.');
      console.error(error);
    }
  };

  return (
    <>
      <div className="dashboard-section">
        <h2>Pending Approval Requests</h2>
        <ul className="pending-list">
          {pendingRequests.map(req => (
            <li key={req.id} className="pending-item">
              <div>
                <strong>{req.db_name}</strong>
                <br />
                <small>Requested by: {req.student_username}</small>
              </div>
              <button onClick={() => handleApprove(req.id)} className="approve-button">Approve</button>
            </li>
          ))}
        </ul>
      </div>
      {approvedCredentials && (
        <CredentialsModal credentials={approvedCredentials} onClose={() => setApprovedCredentials(null)} />
      )}
    </>
  );
};

// --- Credentials Modal ---
const CredentialsModal = ({ credentials, onClose }) => (
  <div className="credentials-modal">
    <div className="credentials-content">
      <h2>Database Created!</h2>
      <p><strong>Please copy these credentials now. You will not be able to see the password again.</strong></p>
      <div className="form-group">
        <label>Database Name</label>
        <p>{credentials.db_name}</p>
      </div>
      <div className="form-group">
        <label>Username</label>
        <p>{credentials.db_user}</p>
      </div>
      <div className="form-group">
        <label>Password</label>
        <p>{credentials.db_password}</p>
      </div>
      <button onClick={onClose}>Close</button>
    </div>
  </div>
);


export default App;