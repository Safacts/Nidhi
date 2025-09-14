// frontend/src/App.js --- FINAL FEATURE-COMPLETE VERSION ---
import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import './App.css';
import logo from './logo.png'; // Make sure logo.png is in your src folder

const API_URL = 'http://localhost:8001/api';
const apiClient = axios.create({ baseURL: API_URL });

function App() {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem('nidhi_token'));
  const [theme, setTheme] = useState(localStorage.getItem('nidhi_theme') || 'light');
  const [notification, setNotification] = useState({ message: '', type: '' });

  useEffect(() => {
    const storedUser = localStorage.getItem('nidhi_user');
    if (storedUser && token) setUser(JSON.parse(storedUser));
  }, [token]);

  useEffect(() => {
    document.body.className = `${theme}-mode`;
    localStorage.setItem('nidhi_theme', theme);
  }, [theme]);

  const toggleTheme = () => setTheme(theme === 'light' ? 'dark' : 'light');

  const showNotification = (message, type = 'error') => {
    setNotification({ message, type });
    setTimeout(() => setNotification({ message: '', type: '' }), 5000);
  };

  const handleLogin = (userData, tokenData) => {
    setUser(userData);
    setToken(tokenData.access);
    localStorage.setItem('nidhi_user', JSON.stringify(userData));
    localStorage.setItem('nidhi_token', tokenData.access);
  };

  const handleLogout = () => {
    setUser(null);
    setToken(null);
    localStorage.clear();
    setTheme(localStorage.getItem('nidhi_theme') || 'light');
  };

  return (
    <div className="App">
      <div className="theme-toggle" onClick={toggleTheme} title="Toggle Theme">
        {theme === 'light' ? '🌙' : '☀️'}
      </div>
      <Notification notification={notification} />
      {!user ? (
        <Login onLogin={handleLogin} showNotification={showNotification} />
      ) : (
        <>
          <DashboardHeader user={user} onLogout={handleLogout} />
          {user.role === 'admin' || user.role === 'superuser' ? (
            <AdminDashboard user={user} showNotification={showNotification} />
          ) : (
            <StudentDashboard user={user} showNotification={showNotification} />
          )}
        </>
      )}
    </div>
  );
}

const Notification = ({ notification }) => {
  if (!notification.message) return null;
  return <div className={`notification ${notification.type}`}>{notification.message}</div>;
};

const DashboardHeader = ({ user, onLogout }) => (
  <header className="dashboard-header">
    <img src={logo} alt="Nidhi Logo" className="header-logo" />
    <div>
      <span>Welcome, {user.username} ({user.role})</span>
      <button onClick={onLogout} className="logout-button">Logout</button>
    </div>
  </header>
);

const CredentialsModal = ({ credentials, onClose }) => (
  <div className="credentials-modal">
    <div className="credentials-content">
      <h2>Database Credentials</h2>
      <p><strong>Please copy these now. You will not be able to see the password again.</strong></p>
      <div className="form-group"><label>Database Name</label><p>{credentials.db_name}</p></div>
      <div className="form-group"><label>Username</label><p>{credentials.db_user}</p></div>
      <div className="form-group"><label>Password</label><p>{credentials.db_password}</p></div>
      <button onClick={onClose}>Close & Acknowledge</button>
    </div>
  </div>
);

const DeleteConfirmationModal = ({ request, onConfirm, onCancel }) => {
  const [confirmationName, setConfirmationName] = useState('');
  return (
    <div className="credentials-modal">
      <div className="credentials-content">
        <h2>Delete Database</h2>
        <p>This action is irreversible and will permanently delete the database and its user. To confirm, please type the database name: <strong>{request.db_name}</strong></p>
        <div className="form-group">
          <input type="text" value={confirmationName} onChange={(e) => setConfirmationName(e.target.value)} placeholder="Type database name here" />
        </div>
        <div className="modal-actions">
          <button onClick={onCancel} className="action-button-secondary">Cancel</button>
          <button onClick={() => onConfirm(request.db_name)} disabled={confirmationName !== request.db_name} className="action-button-danger">Delete Permanently</button>
        </div>
      </div>
    </div>
  );
};

const ChangePasswordModal = ({ request, onConfirm, onCancel }) => {
  const [newPassword, setNewPassword] = useState('');
  return (
    <div className="credentials-modal">
      <div className="credentials-content">
        <h2>Change Password for {request.db_user}</h2>
        <div className="form-group">
          <label>New Password (min 8 characters)</label>
          <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
        </div>
        <div className="modal-actions">
          <button onClick={onCancel} className="action-button-secondary">Cancel</button>
          <button onClick={() => onConfirm(newPassword)} disabled={newPassword.length < 8}>Confirm Change</button>
        </div>
      </div>
    </div>
  );
};

const Login = ({ onLogin, showNotification }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const response = await apiClient.post('/login/', { username, password });
      onLogin(response.data.user, response.data.tokens);
    } catch (err) {
      showNotification('Login failed. Please check your credentials or account status.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container">
      <img src={logo} alt="Nidhi Logo" className="login-logo" />
      <h2>Treasure Your Data, Effortlessly.</h2>
      <form onSubmit={handleSubmit}>
        <div className="form-group"><label>Email or Roll Number</label><input type="text" value={username} onChange={(e) => setUsername(e.target.value)} required /></div>
        <div className="form-group"><label>Password</label><input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required /></div>
        <div className="form-links"><a href="https://sunbeam-smiling-trout.ngrok-free.app/college/password_reset/" target="_blank" rel="noopener noreferrer">Forgot Password?</a></div>
        <button type="submit" disabled={loading}>{loading ? 'Logging in...' : 'Login'}</button>
      </form>
    </div>
  );
};

const StudentDashboard = ({ user, showNotification }) => {
  const [requests, setRequests] = useState([]);
  const [dbName, setDbName] = useState('');
  const [loading, setLoading] = useState(false);
  const [revealedCreds, setRevealedCreds] = useState(null);
  const [selectedRequest, setSelectedRequest] = useState(null);
  const [isDeleteModalOpen, setDeleteModalOpen] = useState(false);
  const [isChangePassModalOpen, setChangePassModalOpen] = useState(false);

  const getHeaders = useCallback(() => ({
    'X-User-Id': user.id, 'X-User-Name': user.username,
    'X-User-Role': user.role, 'X-User-College-Id': user.college_id
  }), [user]);

  const fetchRequests = useCallback(async () => {
    try {
      const response = await apiClient.get('/requests/my/', { headers: getHeaders() });
      setRequests(response.data);
    } catch (error) { showNotification('Could not fetch your requests.'); }
  }, [getHeaders, showNotification]);

  useEffect(() => { fetchRequests(); }, [fetchRequests]);

  const handleRequestSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await apiClient.post('/requests/create/', { db_name: dbName }, { headers: getHeaders() });
      setDbName('');
      showNotification('Request submitted successfully!', 'success');
      fetchRequests();
    } catch (error) { showNotification('Failed to create request. Is the name already taken?'); } finally { setLoading(false); }
  };

  const handleReveal = async (requestId) => {
    try {
      const response = await apiClient.post(`/requests/reveal/${requestId}/`, {}, { headers: getHeaders() });
      setRevealedCreds(response.data);
      fetchRequests();
    } catch (error) { showNotification('Credentials have already been viewed and were deleted.'); }
  };

  const handleDeleteRequest = async () => {
    if (!selectedRequest) return;
    try {
      await apiClient.post(`/requests/delete/${selectedRequest.id}/`, {}, { headers: getHeaders() });
      showNotification(`Database '${selectedRequest.db_name}' deleted successfully!`, 'success');
      fetchRequests();
      setDeleteModalOpen(false);
      setSelectedRequest(null);
    } catch (error) { showNotification('Failed to delete database.'); }
  };

  const handleChangePassword = async (newPassword) => {
    if (!selectedRequest) return;
    try {
      await apiClient.post(`/requests/change-password/${selectedRequest.id}/`, { password: newPassword }, { headers: getHeaders() });
      showNotification('Password changed successfully!', 'success');
      setChangePassModalOpen(false);
      setSelectedRequest(null);
    } catch (error) { showNotification(error.response?.data?.error || 'Failed to change password.'); }
  };

  return (
    <>
      <div className="dashboard-section">
        <h2>Request a New Database</h2>
        <form onSubmit={handleRequestSubmit}>
          <div className="form-group"><label>New Database Name (e.g., my-project-name)</label><input type="text" value={dbName} onChange={(e) => setDbName(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))} required /></div>
          <button type="submit" disabled={loading}>{loading ? 'Requesting...' : 'Submit Request'}</button>
        </form>
      </div>
      <div className="dashboard-section">
        <h2>My Databases</h2>
        <div className="database-card-container">
          {requests.length === 0 && <p>You have no active or pending database requests.</p>}
          {requests.map(req => (
            <div key={req.id} className="database-card">
              <div className="card-header">
                <h3>{req.db_name}</h3>
                <span className={`status status-${req.status}`}>{req.status}</span>
              </div>
              {req.status === 'approved' && (
                <div className="card-body">
                  <h4>Connection Info</h4>
                  <p><strong>Host:</strong> localhost</p>
                  <p><strong>Port:</strong> 5435</p>
                  <p><strong>Username:</strong> {req.db_user}</p>
                </div>
              )}
              <div className="card-actions">
                {req.status === 'approved' && req.db_password_temp !== null && (
                  <button onClick={() => handleReveal(req.id)}>View Password</button>
                )}
                {req.status === 'approved' && (
                  <>
                    <button onClick={() => { setSelectedRequest(req); setChangePassModalOpen(true); }} className="action-button-secondary">Change Password</button>
                    <button onClick={() => { setSelectedRequest(req); setDeleteModalOpen(true); }} className="action-button-danger">Delete</button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
      {revealedCreds && <CredentialsModal credentials={revealedCreds} onClose={() => setRevealedCreds(null)} />}
      {isDeleteModalOpen && <DeleteConfirmationModal request={selectedRequest} onConfirm={handleDeleteRequest} onCancel={() => setDeleteModalOpen(false)} />}
      {isChangePassModalOpen && <ChangePasswordModal request={selectedRequest} onConfirm={handleChangePassword} onCancel={() => setChangePassModalOpen(false)} />}
    </>
  );
};

const AdminDashboard = ({ user, showNotification }) => {
  const [pendingRequests, setPendingRequests] = useState([]);

  const getHeaders = useCallback(() => ({
    'X-User-Id': user.id, 'X-User-Name': user.username,
    'X-User-Role': user.role, 'X-User-College-Id': user.college_id
  }), [user]);

  const fetchPending = useCallback(async () => {
    try {
      const response = await apiClient.get('/admin/requests/pending/', { headers: getHeaders() });
      setPendingRequests(response.data);
    } catch (error) { showNotification('Could not fetch pending requests.'); }
  }, [getHeaders, showNotification]);

  useEffect(() => { fetchPending(); }, [fetchPending]);

  const handleApprove = async (requestId) => {
    try {
      await apiClient.post(`/admin/requests/approve/${requestId}/`, {}, { headers: getHeaders() });
      showNotification('Request approved successfully!', 'success');
      fetchPending();
    } catch (error) { showNotification('Failed to approve request.'); }
  };

  return (
    <div className="dashboard-section">
      <h2>Pending Approval Requests</h2>
      <ul className="pending-list">
        {pendingRequests.length === 0 && <li>No pending requests.</li>}
        {pendingRequests.map(req => (
          <li key={req.id} className="pending-item">
            <div><strong>{req.db_name}</strong><br /><small>Requested by: {req.student_username}</small></div>
            <button onClick={() => handleApprove(req.id)} className="approve-button">Approve</button>
          </li>
        ))}
      </ul>
    </div>
  );
};

export default App;