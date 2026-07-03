import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { HardDrive, ArrowLeft, RefreshCw, File, Folder, Upload, Download, Trash2, Plus, ArrowUp, ChevronRight, ChevronDown, Edit3, Check, X } from 'lucide-react';
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
  const [newFolderName, setNewFolderName] = useState('');
  const [treeData, setTreeData] = useState(null);
  const [treeLoading, setTreeLoading] = useState(false);
  const [expandedFolders, setExpandedFolders] = useState(new Set());
  const [renamingItem, setRenamingItem] = useState(null);
  const [renameValue, setRenameValue] = useState('');
  const [selectedItems, setSelectedItems] = useState(new Set());
  const [contextMenu, setContextMenu] = useState(null);

  useEffect(() => {
    fetchBucketInfo();
    fetchObjects();
  }, [id, currentPrefix]);

  useEffect(() => {
    fetchTree();
  }, [id]);

  useEffect(() => {
    if (treeData && expandedFolders.size === 0) {
      const firstLevel = treeData.children || [];
      if (firstLevel.length > 0) {
        const autoExpand = new Set();
        firstLevel.forEach(child => {
          if (child.type === 'directory') autoExpand.add(child.name);
        });
        setExpandedFolders(autoExpand);
      }
    }
  }, [treeData]);

  useEffect(() => {
    if (contextMenu) {
      const close = () => setContextMenu(null);
      document.addEventListener('click', close);
      return () => document.removeEventListener('click', close);
    }
  }, [contextMenu]);

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
      fetchObjects();
      fetchTree();
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
      fetchObjects();
      fetchTree();
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
      fetchObjects();
      fetchTree();
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

  const handleRename = async (oldName, newName) => {
    if (!newName || newName === oldName) { setRenamingItem(null); return; }
    const token = localStorage.getItem('sso_token');
    try {
      const res = await fetch(`/nidhi-api/buckets/${id}/rename/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ object_name: oldName, new_object_name: newName })
      });
      if (!res.ok) { const d = await res.json(); throw new Error(d.error); }
      setRenamingItem(null);
      fetchObjects();
      fetchTree();
    } catch (err) {
      alert('Rename failed: ' + err.message);
    }
  };

  const handleMultiDelete = async () => {
    if (selectedItems.size === 0) return;
    if (!window.confirm(`Delete ${selectedItems.size} selected item(s)?`)) return;
    const token = localStorage.getItem('sso_token');
    try {
      const res = await fetch(`/nidhi-api/buckets/${id}/delete-multiple/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ object_names: Array.from(selectedItems) })
      });
      if (!res.ok) { const d = await res.json(); throw new Error(d.error); }
      setSelectedItems(new Set());
      fetchObjects();
      fetchTree();
    } catch (err) {
      alert('Delete failed: ' + err.message);
    }
  };

  const toggleSelection = (path, e) => {
    e.stopPropagation();
    setSelectedItems(prev => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path); else next.add(path);
      return next;
    });
  };

  const startRename = (currentName) => {
    setRenamingItem(currentName);
    setRenameValue(currentName);
    setContextMenu(null);
  };

  const fetchTree = async () => {
    setTreeLoading(true);
    try {
      const token = localStorage.getItem('sso_token');
      const res = await fetch(`/nidhi-api/buckets/${id}/objects/?recursive=true`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setTreeData(data);
      }
    } catch (err) {
      console.error('Failed to fetch tree:', err);
    } finally {
      setTreeLoading(false);
    }
  };

  const toggleFolder = (name) => {
    setExpandedFolders(prev => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  };

  const handleTreeFolderClick = (prefix) => {
    setCurrentPrefix(prefix);
  };

  const handleContextMenu = (e, path) => {
    e.preventDefault();
    e.stopPropagation();
    setContextMenu({ x: e.clientX, y: e.clientY, path });
  };

  const TreeView = ({ node, depth = 0 }) => {
    return (
      <div>
        {node.children && node.children.map((child, idx) => {
          const isDir = child.type === 'directory';
          const isExpanded = expandedFolders.has(child.name);
          const childPrefix = child.name.endsWith('/') ? child.name : `${child.name}/`;
          const isActive = isDir && currentPrefix === childPrefix;
          const isRenaming = renamingItem === (isDir ? childPrefix : child.path);
          const childPath = isDir ? childPrefix : child.path;
          const isSelected = selectedItems.has(childPath);

          if (isRenaming) {
            return (
              <div key={idx} style={{ paddingLeft: `${depth * 16 + 8}px` }} className="flex items-center gap-1 px-2 py-1">
                <input
                  autoFocus
                  value={renameValue}
                  onChange={(e) => setRenameValue(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleRename(renamingItem, renameValue); if (e.key === 'Escape') setRenamingItem(null); }}
                  onBlur={() => handleRename(renamingItem, renameValue)}
                  className="flex-1 text-xs bg-slate-50 dark:bg-slate-900 border border-indigo-500 rounded px-2 py-1 outline-none"
                />
                <button onClick={() => handleRename(renamingItem, renameValue)} className="p-0.5 text-green-600 hover:text-green-500"><Check className="w-3.5 h-3.5" /></button>
                <button onClick={() => setRenamingItem(null)} className="p-0.5 text-red-600 hover:text-red-500"><X className="w-3.5 h-3.5" /></button>
              </div>
            );
          }

          if (isDir) {
            return (
              <div key={idx}>
                <div
                  className={`flex items-center gap-1 px-2 py-1 cursor-pointer rounded text-sm transition-colors ${isSelected ? 'bg-indigo-50 dark:bg-indigo-900/20' : isActive ? 'bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300' : 'text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700/50'}`}
                  style={{ paddingLeft: `${depth * 16 + 8}px` }}
                  onContextMenu={(e) => handleContextMenu(e, childPath)}
                  onClick={() => { toggleFolder(child.name); handleTreeFolderClick(childPrefix); }}
                >
                  <div className="flex items-center gap-0.5 shrink-0" onClick={(e) => e.stopPropagation()}>
                    <div className={`w-3.5 h-3.5 flex items-center justify-center rounded border cursor-pointer transition-colors ${isSelected ? 'bg-indigo-600 border-indigo-600 text-white' : 'border-slate-400 dark:border-slate-500 hover:border-indigo-500'}`} onClick={(e) => toggleSelection(childPath, e)}>
                      {isSelected && <Check className="w-3 h-3" />}
                    </div>
                  </div>
                  <span className="shrink-0" onClick={(e) => e.stopPropagation()}>
                    {isExpanded ? <ChevronDown className="w-3.5 h-3.5 text-slate-400" /> : <ChevronRight className="w-3.5 h-3.5 text-slate-400" />}
                  </span>
                  <Folder className={`w-4 h-4 shrink-0 ${isActive ? 'text-indigo-500' : 'text-amber-500'}`} />
                  <span className="truncate ml-1">{child.name.replace('/', '')}</span>
                </div>
                {isExpanded && child.children && (
                  <TreeView node={child} depth={depth + 1} />
                )}
              </div>
            );
          }
          return (
            <div
              key={idx}
              className={`flex items-center gap-1 px-2 py-1 rounded text-sm transition-colors ${isSelected ? 'bg-indigo-50 dark:bg-indigo-900/20' : 'text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800/40'}`}
              style={{ paddingLeft: `${depth * 16 + 8}px` }}
              onContextMenu={(e) => handleContextMenu(e, childPath)}
            >
              <div className={`w-3.5 h-3.5 flex items-center justify-center rounded border cursor-pointer transition-colors shrink-0 ${isSelected ? 'bg-indigo-600 border-indigo-600 text-white' : 'border-slate-400 dark:border-slate-500 hover:border-indigo-500'}`} onClick={(e) => toggleSelection(childPath, e)}>
                {isSelected && <Check className="w-3 h-3" />}
              </div>
              <File className="w-4 h-4 shrink-0 text-indigo-500/70 ml-5" />
              <span className="truncate ml-1">{child.name}</span>
            </div>
          );
        })}
      </div>
    );
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
        {/* Tree Explorer Sidebar */}
        <div className="lg:col-span-1">
          <div className="bg-white dark:bg-slate-800 p-4 rounded-xl border border-slate-300 dark:border-slate-700 shadow-xl">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-lg font-semibold">Files</h3>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => document.getElementById('folder-input').focus()}
                  className="p-1.5 rounded hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors text-slate-500 dark:text-slate-400"
                  title="Create folder"
                >
                  <Plus className="w-4 h-4" />
                </button>
                <label className="p-1.5 rounded hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors text-slate-500 dark:text-slate-400 cursor-pointer" title="Upload file">
                  <Upload className="w-4 h-4" />
                  <input type="file" onChange={(e) => { const f = e.target.files[0]; if (f) handleUpload(f); e.target.value = ''; }} className="hidden" />
                </label>
                <button
                  onClick={fetchTree}
                  className="p-1.5 rounded hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors text-slate-500 dark:text-slate-400"
                  title="Refresh"
                >
                  <RefreshCw className={`w-4 h-4 ${treeLoading ? 'animate-spin' : ''}`} />
                </button>
              </div>
            </div>

            <div className="flex gap-1 mb-3">
              <input
                id="folder-input"
                type="text"
                value={newFolderName}
                onChange={(e) => setNewFolderName(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && newFolderName.trim()) { handleCreateFolder(newFolderName); setNewFolderName(''); } }}
                placeholder="New folder..."
                className="flex-1 text-xs bg-slate-50 dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded px-2 py-1.5 outline-none focus:border-indigo-500 transition"
              />
              <button
                onClick={() => { if (newFolderName.trim()) { handleCreateFolder(newFolderName); setNewFolderName(''); } }}
                className="px-2 py-1.5 bg-indigo-600 text-white rounded hover:bg-indigo-700 transition text-xs font-medium"
              >
                Add
              </button>
            </div>

            <div className="max-h-[300px] overflow-y-auto space-y-0.5">
              {treeLoading && !treeData ? (
                <p className="text-sm text-slate-500 dark:text-slate-400 p-2">Loading...</p>
              ) : treeData && treeData.children && treeData.children.length > 0 ? (
                <TreeView node={treeData} depth={0} />
              ) : (
                <p className="text-sm text-slate-500 dark:text-slate-400 p-2">Empty bucket</p>
              )}
            </div>

            {selectedItems.size > 0 && (
              <div className="mt-3 pt-3 border-t border-slate-200 dark:border-slate-700 flex items-center justify-between">
                <span className="text-xs text-slate-500 dark:text-slate-400">{selectedItems.size} selected</span>
                <div className="flex gap-1">
                  <button onClick={() => setSelectedItems(new Set())} className="px-2 py-1 text-xs text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-700 rounded transition">Clear</button>
                  <button onClick={handleMultiDelete} className="px-2 py-1 text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 hover:bg-red-100 dark:hover:bg-red-900/30 rounded flex items-center gap-1 transition">
                    <Trash2 className="w-3 h-3" /> Delete
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Bucket Info Sidebar */}
          <div className="bg-white dark:bg-slate-800 p-6 rounded-xl border border-slate-300 dark:border-slate-700 shadow-xl mt-4">
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

      {contextMenu && (
        <div
          className="fixed z-50 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg shadow-xl py-1 min-w-[140px]"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          {!contextMenu.path.endsWith('/') && (
            <button
              onClick={() => { handleDownload(contextMenu.path); setContextMenu(null); }}
              className="w-full flex items-center gap-3 px-3 py-2 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
            >
              <Download className="w-4 h-4" /> Download
            </button>
          )}
          <button
            onClick={() => startRename(contextMenu.path)}
            className="w-full flex items-center gap-3 px-3 py-2 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
          >
            <Edit3 className="w-4 h-4" /> Rename
          </button>
          <button
            onClick={() => { setContextMenu(null); handleDelete(contextMenu.path); }}
            className="w-full flex items-center gap-3 px-3 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
          >
            <Trash2 className="w-4 h-4" /> Delete
          </button>
        </div>
      )}
    </div>
  );
};

export default BucketStudio;
