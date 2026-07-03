import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { HardDrive, ArrowLeft, RefreshCw, File, Folder, Upload, Download, Trash2, Plus, ArrowUp } from 'lucide-react';
import { ThemeToggle } from '../contexts/ThemeContext';
import { Logo } from '../components/Logo';

const BucketStudio = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [objects, setObjects] = useState([]);
  const [bucketInfo, setBucketInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [currentPrefix, setCurrentPrefix] = useState('');
  const [selectedObject, setSelectedObject] = useState(null);
  const [uploadFile, setUploadFile] = useState(null);
  const [newFolderName, setNewFolderName] = useState('');

  useEffect(() => {
    fetchBucketInfo();
    fetchObjects();
  }, [id, currentPrefix]);

  const getHeaders = () => {
    const token = localStorage.getItem('sso_token');
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    };
  };

  const fetchBucketInfo = async () => {
    try {
      const token = localStorage.getItem('sso_token');
      const res = await fetch(`/nidhi-api/buckets/${id}/reveal/`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setBucketInfo(data);
      }
    } catch (err) {
      console.error('Failed to fetch bucket info:', err);
    }
  };

  const fetchObjects = async () => {
    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem('sso_token');
      const url = currentPrefix 
        ? `/nidhi-api/buckets/${id}/objects/?prefix=${encodeURIComponent(currentPrefix)}`
        : `/nidhi-api/buckets/${id}/objects/`;
      const res = await fetch(url, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.error || "Failed to fetch objects");
      }
      const data = await res.json();
      setObjects(data);
    } catch (err) {
      setError("Failed to fetch objects: " + err.message);
      setObjects([]);
    } finally {
      setLoading(false);
    }
  };

  const handleUpload = async (file) => {
    if (!file) return;
    
    const formData = new FormData();
    formData.append('file', file);
    formData.append('object_name', file.name);
    
    try {
      const token = localStorage.getItem('sso_token');
      const res = await fetch(`/nidhi-api/buckets/${id}/upload/`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData
      });
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.error || "Upload failed");
      }
      alert('File uploaded successfully');
      fetchObjects();
    } catch (err) {
      alert('Upload failed: ' + err.message);
    }
  };

  const handleDownload = async (objectName) => {
    try {
      const token = localStorage.getItem('sso_token');
      const res = await fetch(`/nidhi-api/buckets/${id}/reveal/`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!res.ok) throw new Error('Failed to get bucket credentials');
      const bucketInfo = await res.json();
      
      // Generate presigned URL for download (simplified - in production use backend presigned URL)
      const downloadUrl = `http://${bucketInfo.endpoint}/${bucketInfo.bucket_name}/${objectName}`;
      window.open(downloadUrl, '_blank');
    } catch (err) {
      alert('Download failed: ' + err.message);
    }
  };

  const handleDelete = async (objectName) => {
    if (!window.confirm(`Delete ${objectName}?`)) return;
    
    try {
      const token = localStorage.getItem('sso_token');
      const res = await fetch(`/nidhi-api/buckets/${id}/delete/`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ object_name: objectName })
      });
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.error || "Delete failed");
      }
      alert('Object deleted successfully');
      fetchObjects();
    } catch (err) {
      alert('Delete failed: ' + err.message);
    }
  };

  const handleCreateFolder = async (folderName) => {
    if (!folderName || !folderName.trim()) return;
    
    try {
      const token = localStorage.getItem('sso_token');
      const res = await fetch(`/nidhi-api/buckets/${id}/create-folder/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ 
          folder_name: folderName.trim(),
          prefix: currentPrefix
        })
      });
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.error || "Folder creation failed");
      }
      alert('Folder created successfully');
      fetchObjects();
    } catch (err) {
      alert('Folder creation failed: ' + err.message);
    }
  };

  const handleNavigateToFolder = (objectName) => {
    if (objectName.endsWith('/')) {
      setCurrentPrefix(objectName);
    }
  };

  const handleNavigateUp = () => {
    if (currentPrefix) {
      const parts = currentPrefix.split('/').filter(p => p);
      parts.pop();
      setCurrentPrefix(parts.length > 0 ? parts.join('/') + '/' : '');
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-slate-100 p-8 transition-colors duration-300">
      <header className="mb-8 flex justify-between items-center border-b border-slate-300 dark:border-slate-800 pb-6">
        <div className="flex items-center gap-6">
          <Logo />
          <div className="h-10 w-px bg-slate-300 dark:bg-slate-700"></div>
          <div>
            <h1 className="text-2xl font-bold text-indigo-500 flex items-center gap-3">
              <HardDrive /> Bucket Explorer
            </h1>
            <p className="text-slate-500 dark:text-slate-400">
              {bucketInfo ? bucketInfo.bucket_name : 'Loading...'}
            </p>
          </div>
        </div>
        <div className="flex gap-4 items-center">
          <ThemeToggle />
          <button 
            onClick={() => navigate('/admin')}
            className="flex items-center gap-2 bg-slate-200 dark:bg-slate-800 hover:bg-slate-300 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 px-4 py-2 rounded-lg font-medium transition"
          >
            <ArrowLeft className="w-4 h-4" /> Back to Admin
          </button>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
        {/* Bucket Info Sidebar */}
        <div className="lg:col-span-1">
          <div className="bg-white dark:bg-slate-800 p-6 rounded-xl border border-slate-300 dark:border-slate-700 shadow-xl">
            <h3 className="text-lg font-semibold mb-4">Bucket Details</h3>
            {bucketInfo ? (
              <div className="space-y-3 text-sm">
                <div>
                  <span className="text-slate-500 dark:text-slate-400">Name:</span>
                  <p className="font-medium">{bucketInfo.bucket_name}</p>
                </div>
                <div>
                  <span className="text-slate-500 dark:text-slate-400">Endpoint:</span>
                  <p className="font-medium">{bucketInfo.endpoint}</p>
                </div>
                <div>
                  <span className="text-slate-500 dark:text-slate-400">Access Key:</span>
                  <p className="font-medium font-mono text-xs">{bucketInfo.access_key}</p>
                </div>
                <div>
                  <span className="text-slate-500 dark:text-slate-400">Secret Key:</span>
                  <p className="font-medium font-mono text-xs">••••••••••••</p>
                </div>
              </div>
            ) : (
              <p className="text-slate-500 dark:text-slate-400">Loading bucket info...</p>
            )}
          </div>

          <div className="bg-white dark:bg-slate-800 p-6 rounded-xl border border-slate-300 dark:border-slate-700 shadow-xl mt-4">
            <h3 className="text-lg font-semibold mb-4">Actions</h3>
            <div className="space-y-3">
              <div>
                <label className="block text-sm text-slate-500 dark:text-slate-400 mb-2">Create Folder</label>
                <div className="flex gap-2">
                  <input 
                    type="text" 
                    value={newFolderName}
                    onChange={(e) => setNewFolderName(e.target.value)}
                    placeholder="folder-name"
                    className="flex-1 text-sm bg-slate-50 dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded px-3 py-2"
                  />
                  <button 
                    onClick={() => handleCreateFolder(newFolderName)}
                    className="px-3 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 transition text-sm"
                  >
                    <Plus className="w-4 h-4" />
                  </button>
                </div>
              </div>
              <div>
                <label className="block text-sm text-slate-500 dark:text-slate-400 mb-2">Upload File</label>
                <input 
                  type="file" 
                  onChange={(e) => setUploadFile(e.target.files[0])}
                  className="w-full text-sm text-slate-500 dark:text-slate-400 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100 dark:file:bg-indigo-900/20 dark:file:text-indigo-400"
                />
                {uploadFile && (
                  <button 
                    onClick={() => handleUpload(uploadFile)}
                    className="mt-2 w-full flex items-center justify-center gap-2 px-3 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition"
                  >
                    <Upload className="w-4 h-4" /> Upload {uploadFile.name}
                  </button>
                )}
              </div>
              <button 
                onClick={fetchObjects}
                className="w-full flex items-center gap-3 px-3 py-2 text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition"
              >
                <RefreshCw className="w-4 h-4" /> Refresh
              </button>
            </div>
          </div>
        </div>

        {/* Objects List */}
        <div className="lg:col-span-3">
          <div className="bg-white dark:bg-slate-800/40 backdrop-blur-md border border-slate-300 dark:border-slate-700 rounded-xl overflow-hidden shadow-xl">
            <div className="p-4 border-b border-slate-200 dark:border-slate-700/50 flex justify-between items-center">
              <div>
                <h2 className="text-xl font-semibold text-slate-700 dark:text-slate-300">Objects</h2>
                <p className="text-sm text-slate-500 dark:text-slate-400">
                  {currentPrefix ? `Path: /${currentPrefix}` : 'Root'}
                </p>
              </div>
              {currentPrefix && (
                <button 
                  onClick={handleNavigateUp}
                  className="flex items-center gap-2 px-3 py-2 text-sm bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded hover:bg-slate-200 dark:hover:bg-slate-600 transition"
                >
                  <ArrowUp className="w-4 h-4" /> Up
                </button>
              )}
            </div>
            
            {loading ? (
              <div className="p-8 text-center text-slate-500 dark:text-slate-400">
                Loading objects...
              </div>
            ) : error ? (
              <div className="p-8 text-center text-red-500">
                {error}
              </div>
            ) : objects.length === 0 ? (
              <div className="p-8 text-center text-slate-500 dark:text-slate-400">
                <Folder className="w-12 h-12 mx-auto mb-4 opacity-50" />
                <p>This bucket is empty</p>
                <p className="text-sm mt-2">Upload files to get started</p>
              </div>
            ) : (
              <table className="w-full text-left">
                <thead className="bg-slate-100 dark:bg-slate-800/80 text-slate-500 dark:text-slate-400 text-xs uppercase tracking-wider">
                  <tr>
                    <th className="px-6 py-4">Name</th>
                    <th className="px-6 py-4">Size</th>
                    <th className="px-6 py-4">Last Modified</th>
                    <th className="px-6 py-4">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-slate-700/50">
                  {objects.map(obj => (
                    <tr key={obj.name} className="hover:bg-slate-50 dark:hover:bg-slate-800/60 transition">
                      <td 
                        className="px-6 py-4 font-semibold flex items-center gap-2 cursor-pointer"
                        onClick={() => handleNavigateToFolder(obj.name)}
                      >
                        {obj.is_dir || obj.name.endsWith('/') ? (
                          <Folder className="w-4 h-4 text-amber-500" />
                        ) : (
                          <File className="w-4 h-4 text-indigo-500" />
                        )}
                        {obj.name.replace(currentPrefix, '')}
                      </td>
                      <td className="px-6 py-4 text-slate-500 dark:text-slate-400 text-sm">
                        {obj.size ? `${(obj.size / 1024).toFixed(2)} KB` : '-'}
                      </td>
                      <td className="px-6 py-4 text-slate-500 dark:text-slate-400 text-sm">
                        {obj.last_modified ? new Date(obj.last_modified).toLocaleString() : '-'}
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex gap-2">
                          <button 
                            onClick={() => handleDownload(obj.name)}
                            className="px-3 py-1 bg-blue-100 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-300 dark:border-blue-500/20 rounded hover:bg-blue-200 dark:hover:bg-blue-500/20 text-xs flex items-center gap-1"
                          >
                            <Download className="w-3 h-3" />
                          </button>
                          <button 
                            onClick={() => handleDelete(obj.name)}
                            className="px-3 py-1 bg-red-100 dark:bg-red-500/10 text-red-600 dark:text-red-400 border border-red-300 dark:border-red-500/20 rounded hover:bg-red-200 dark:hover:bg-red-500/20 text-xs flex items-center gap-1"
                          >
                            <Trash2 className="w-3 h-3" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default BucketStudio;
