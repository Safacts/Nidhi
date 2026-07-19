import React, { useState, useEffect, useRef } from 'react';
import { Bell, Check, X, AlertTriangle, Info, AlertCircle } from 'lucide-react';

export const NotificationBell = () => {
  const [alerts, setAlerts] = useState([]);
  const [isOpen, setIsOpen] = useState(false);
  const [knownAlertIds, setKnownAlertIds] = useState(new Set());
  const dropdownRef = useRef(null);

  // Request Notification permission on mount
  useEffect(() => {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }
  }, []);

  const fetchAlerts = async () => {
    try {
      const token = localStorage.getItem('sso_token');
      if (!token) return;
      const response = await fetch('/nidhi-api/alerts/', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setAlerts(data);
        
        // Trigger browser notifications for new unread alerts
        if ('Notification' in window && Notification.permission === 'granted') {
          const incomingUnreadIds = data.filter(a => !a.is_read).map(a => a.id);
          
          setKnownAlertIds(prev => {
            const newIds = new Set(prev);
            let hasNew = false;
            
            incomingUnreadIds.forEach(id => {
              if (!newIds.has(id)) {
                // We found a completely new unread alert
                const alertItem = data.find(a => a.id === id);
                if (alertItem) {
                  new Notification('Nidhi Alert: ' + alertItem.title, {
                    body: alertItem.message,
                    icon: '/favicon.ico' // Or any suitable icon
                  });
                }
                newIds.add(id);
                hasNew = true;
              }
            });
            
            return hasNew ? newIds : prev;
          });
        }
      }
    } catch (err) {
      console.error('Failed to fetch alerts:', err);
    }
  };

  useEffect(() => {
    fetchAlerts();
    const interval = setInterval(fetchAlerts, 30000); // poll every 30 seconds
    return () => clearInterval(interval);
  }, []);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const markAsRead = async (id, e) => {
    e.stopPropagation();
    try {
      const token = localStorage.getItem('sso_token');
      await fetch(`/nidhi-api/alerts/${id}/read/`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      setAlerts(alerts.map(a => a.id === id ? { ...a, is_read: true } : a));
    } catch (err) {
      console.error('Failed to mark read:', err);
    }
  };

  const markAllAsRead = async () => {
    try {
      const token = localStorage.getItem('sso_token');
      await fetch('/nidhi-api/alerts/read-all/', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      setAlerts(alerts.map(a => ({ ...a, is_read: true })));
    } catch (err) {
      console.error('Failed to mark all read:', err);
    }
  };

  const unreadCount = alerts.filter(a => !a.is_read).length;

  return (
    <div className="relative" ref={dropdownRef}>
      <button 
        onClick={() => setIsOpen(!isOpen)}
        className="relative p-2 rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors focus:outline-none focus:ring-2 focus:ring-red-500"
        aria-label="Notifications"
      >
        <Bell className="w-5 h-5" />
        {unreadCount > 0 && (
          <span className="absolute top-1 right-1.5 flex h-3 w-3 items-center justify-center rounded-full bg-red-500 text-[10px] text-white ring-2 ring-white dark:ring-slate-900">
            {unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-80 sm:w-96 bg-white dark:bg-slate-800 rounded-xl shadow-xl border border-slate-200 dark:border-slate-700 z-50 overflow-hidden flex flex-col max-h-[32rem]">
          <div className="p-4 border-b border-slate-200 dark:border-slate-700 flex justify-between items-center bg-slate-50 dark:bg-slate-800/50">
            <h3 className="font-semibold text-slate-800 dark:text-slate-100">Notifications</h3>
            {unreadCount > 0 && (
              <button 
                onClick={markAllAsRead}
                className="text-xs text-blue-500 hover:text-blue-600 dark:text-blue-400 font-medium"
              >
                Mark all as read
              </button>
            )}
          </div>
          
          <div className="overflow-y-auto flex-1">
            {alerts.length === 0 ? (
              <div className="p-8 text-center text-slate-500 dark:text-slate-400">
                <Bell className="w-8 h-8 mx-auto mb-3 opacity-20" />
                <p>No notifications yet</p>
              </div>
            ) : (
              <ul className="divide-y divide-slate-100 dark:divide-slate-700">
                {alerts.map((alert) => (
                  <li 
                    key={alert.id} 
                    className={`p-4 hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors flex gap-3 ${!alert.is_read ? 'bg-blue-50/30 dark:bg-blue-900/10' : ''}`}
                  >
                    <div className="flex-shrink-0 mt-1">
                      {alert.level === 'error' && <AlertCircle className="w-5 h-5 text-red-500" />}
                      {alert.level === 'warning' && <AlertTriangle className="w-5 h-5 text-amber-500" />}
                      {alert.level === 'info' && <Info className="w-5 h-5 text-blue-500" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex justify-between items-start mb-1">
                        <p className={`text-sm font-medium ${!alert.is_read ? 'text-slate-900 dark:text-white' : 'text-slate-700 dark:text-slate-300'}`}>
                          {alert.title}
                        </p>
                        <span className="text-[10px] text-slate-400 whitespace-nowrap ml-2">
                          {new Date(alert.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
                        {alert.message}
                      </p>
                    </div>
                    {!alert.is_read && (
                      <button 
                        onClick={(e) => markAsRead(alert.id, e)}
                        className="flex-shrink-0 w-6 h-6 rounded-full hover:bg-slate-200 dark:hover:bg-slate-600 flex items-center justify-center text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors mt-0.5"
                        title="Mark as read"
                      >
                        <Check className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
