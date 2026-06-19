import React, { useState, useEffect } from 'react';
import { Database, Plus, RefreshCw, X, Key, Trash2, LogOut, User, Settings, CreditCard, ChevronDown } from 'lucide-react';
import { Logo } from '../components/Logo';
import { ThemeToggle } from '../contexts/ThemeContext';
import { useNavigate } from 'react-router-dom';

const EmployeeDashboard = () => {
  const [instances, setInstances] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showProvisionModal, setShowProvisionModal] = useState(false);
  const [showProfileMenu, setShowProfileMenu] = useState(false);
  const navigate = useNavigate();
  const [servers, setServers] = useState([]);
  const [products, setProducts] = useState([]);
  const [newDbForm, setNewDbForm] = useState({ db_name: '', server_id: '', product_id: '' });

  useEffect(() => {
    fetchInstances();
  }, []);

  const fetchInstances = async () => {
    try {
      const token = localStorage.getItem('sso_token');
      const response = await fetch(`http://${window.location.hostname}:8001/api/instances/`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await response.json();
      setInstances(Array.isArray(data) ? data : []);
      
      const servRes = await fetch(`http://${window.location.hostname}:8001/api/servers/`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const servData = await servRes.json();
      setServers(Array.isArray(servData) ? servData : []);

      const prodRes = await fetch(`http://${window.location.hostname}:8001/api/products/`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const prodData = await prodRes.json();
      setProducts(Array.isArray(prodData) ? prodData : []);

      setLoading(false);
    } catch (error) {
      console.error("Failed to fetch data", error);
      setLoading(false);
    }
  };

  const handleProvision = async (e) => {
    e.preventDefault();
    try {
      const token = localStorage.getItem('sso_token');
      const response = await fetch(`http://${window.location.hostname}:8001/api/instances/`, {
        method: 'POST',
        headers: { 
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          db_name: newDbForm.db_name,
          server_id: newDbForm.server_id,
          product_id: newDbForm.product_id
        })
      });
      
      if (response.ok) {
        setShowProvisionModal(false);
        setNewDbForm({ db_name: '', server_id: '', product_id: '' });
        fetchInstances();
      } else {
        const errorData = await response.json();
        alert("Failed: " + JSON.stringify(errorData));
      }
    } catch (error) {
      alert("Error provisioning database");
    }
  };

  const requestSoftDelete = async (id) => {
    if (!window.confirm("Are you sure you want to request soft-delete? This will revoke access immediately.")) return;
    try {
      const token = localStorage.getItem('sso_token');
      await fetch(`http://${window.location.hostname}:8001/api/instances/${id}/delete/`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      fetchInstances();
    } catch (err) {
      alert("Soft delete failed");
    }
  };

  if (loading) {
    return <div className="min-h-screen bg-slate-900 text-slate-100 flex items-center justify-center">Loading Workspace...</div>;
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-slate-100 p-8 transition-colors duration-300">
      <header className="mb-10 flex justify-between items-center border-b border-slate-300 dark:border-slate-800 pb-6">
        <div className="flex items-center gap-6">
          <Logo />
          <div className="h-10 w-px bg-slate-300 dark:bg-slate-700"></div>
          <div>
            <h1 className="text-3xl font-bold mb-2 text-slate-800 dark:text-white">My Workspace</h1>
            <p className="text-slate-500 dark:text-slate-400">Manage databases for your assigned products.</p>
          </div>
        </div>
        <div className="flex gap-4 items-center">
          <ThemeToggle />
          {localStorage.getItem('user_role') === 'founding_engineer' && (
            <button 
              onClick={() => navigate('/admin')}
              className="flex items-center gap-2 bg-slate-200 dark:bg-slate-800 hover:bg-slate-300 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 px-4 py-2 rounded-lg font-medium transition"
            >
              Admin Panel
            </button>
          )}
          <button 
            onClick={() => setShowProvisionModal(true)}
            className="flex items-center gap-2 bg-[#4ade80] hover:bg-[#22c55e] text-slate-900 px-4 py-2 rounded-lg font-medium transition"
          >
            <Plus className="w-5 h-5" /> Provision Database
          </button>
          <div className="relative">
            <button 
              onClick={() => setShowProfileMenu(!showProfileMenu)}
              className="flex items-center gap-2 bg-slate-200 dark:bg-slate-800 hover:bg-slate-300 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 px-4 py-2 rounded-lg font-medium transition"
            >
              <User className="w-5 h-5" /> Profile <ChevronDown className="w-4 h-4" />
            </button>
            {showProfileMenu && (
              <div className="absolute right-0 mt-2 w-56 bg-white dark:bg-slate-800 rounded-xl shadow-xl border border-slate-200 dark:border-slate-700 overflow-hidden z-50">
                <div className="p-3 border-b border-slate-200 dark:border-slate-700">
                  <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">{localStorage.getItem('sso_username') || 'Aadi Sheshu'}</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400 capitalize">{localStorage.getItem('user_role')?.replace('_', ' ') || 'Employee'}</p>
                </div>
                <div className="p-2 space-y-1">
                  <button className="w-full flex items-center gap-3 px-3 py-2 text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition">
                    <Settings className="w-4 h-4" /> Account Settings
                  </button>
                  <button className="w-full flex items-center gap-3 px-3 py-2 text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition">
                    <CreditCard className="w-4 h-4" /> Billing & Usage
                  </button>
                </div>
                <div className="p-2 border-t border-slate-200 dark:border-slate-700">
                  <button 
                    onClick={() => {
                      localStorage.removeItem('sso_token');
                      localStorage.removeItem('user_role');
                      localStorage.removeItem('sso_username');
                      navigate('/login');
                    }}
                    className="w-full flex items-center gap-3 px-3 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg transition"
                  >
                    <LogOut className="w-4 h-4" /> Logout
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </header>

      {showProvisionModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-slate-800 border border-slate-700 p-8 rounded-xl w-full max-w-md shadow-2xl relative">
            <h2 className="text-xl font-bold mb-6 text-[#98FF98]">Provision New Database</h2>
            <form onSubmit={handleProvision} className="space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-1">Database Name</label>
                <input 
                  required
                  type="text" 
                  value={newDbForm.db_name}
                  onChange={(e) => setNewDbForm({...newDbForm, db_name: e.target.value})}
                  className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 text-white"
                  placeholder="e.g., hr-prod-db"
                />
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">Select Product</label>
                <select 
                  required
                  value={newDbForm.product_id}
                  onChange={(e) => setNewDbForm({...newDbForm, product_id: e.target.value})}
                  className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 text-white"
                >
                  <option value="">-- Choose Product --</option>
                  {products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">Target Server</label>
                <select 
                  required
                  value={newDbForm.server_id}
                  onChange={(e) => setNewDbForm({...newDbForm, server_id: e.target.value})}
                  className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 text-white"
                >
                  <option value="">-- Choose Server --</option>
                  {servers.map(s => <option key={s.id} value={s.id}>{s.name} ({s.environment_type})</option>)}
                </select>
              </div>
              <div className="flex gap-4 pt-4">
                <button type="button" onClick={() => setShowProvisionModal(false)} className="flex-1 px-4 py-2 bg-slate-700 text-white rounded hover:bg-slate-600 transition">Cancel</button>
                <button type="submit" className="flex-1 px-4 py-2 bg-[#98FF98] text-slate-900 font-bold rounded hover:bg-[#86e086] transition">Provision</button>
              </div>
            </form>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {instances.length === 0 ? (
          <div className="col-span-full text-center text-slate-500 py-12">No databases provisioned yet.</div>
        ) : (
          instances.map(db => (
            <div key={db.id} className="bg-slate-800/40 backdrop-blur-md border border-slate-700/50 rounded-xl p-6 shadow-xl relative overflow-hidden group">
              <div className={`absolute top-0 right-0 w-32 h-32 bg-[#98FF98] mix-blend-overlay filter blur-[64px] opacity-10 group-hover:opacity-20 transition-opacity duration-500`}></div>
              
              <div className="flex justify-between items-start mb-4 relative z-10">
                <div className="flex items-center gap-3">
                  <div className="p-3 bg-slate-900/80 rounded-lg text-[#98FF98]">
                    <Database className="w-6 h-6" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-lg">{db.db_name}</h3>
                    <span className="text-xs text-slate-400 bg-slate-900/50 px-2 py-1 rounded-full">{db.product_name || 'Nidhi Service'}</span>
                  </div>
                </div>
                <span className={`text-xs px-2 py-1 rounded-full border ${
                  db.status === 'available' ? 'bg-[#98FF98]/10 text-[#98FF98] border-[#98FF98]/20' : 
                  db.status === 'provisioning' ? 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20' :
                  'bg-red-500/10 text-red-400 border-red-500/20'
                }`}>
                  {db.status.toUpperCase()}
                </span>
              </div>
              
              <div className="space-y-2 text-sm text-slate-400 mb-6 relative z-10">
                <p>Node: <span className="text-slate-200">{db.server_name}</span></p>
                <p>User: <span className="text-slate-200 font-mono">{db.db_user}</span></p>
              </div>

              <div className="flex gap-2 relative z-10">
                <button className="flex-1 px-3 py-2 bg-slate-700/50 text-slate-200 rounded-lg hover:bg-slate-600/50 transition flex items-center justify-center gap-2">
                  <Key className="w-4 h-4" /> View Credentials
                </button>
                <button 
                  onClick={() => requestSoftDelete(db.id)}
                  className="px-3 py-2 bg-red-500/10 text-red-400 rounded-lg border border-red-500/20 hover:bg-red-500/20 transition"
                  title="Soft Delete"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default EmployeeDashboard;
