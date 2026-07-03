import React, { createContext, useContext, useState, useCallback } from 'react';
import { CheckCircle, XCircle, AlertTriangle, X } from 'lucide-react';

const ToastContext = createContext(null);

export const useToast = () => useContext(ToastContext);

export const ToastProvider = ({ children }) => {
  const [toasts, setToasts] = useState([]);

  const showToast = useCallback((message, type = 'success', duration = 3000) => {
    const id = Date.now() + Math.random();
    setToasts(prev => [...prev, { id, message, type }]);
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), duration);
  }, []);

  const removeToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 max-w-sm">
        {toasts.map(toast => {
          const isSuccess = toast.type === 'success';
          const isError = toast.type === 'error';
          const isWarning = toast.type === 'warning';
          return (
            <div
              key={toast.id}
              className={`flex items-start gap-3 px-4 py-3 rounded-xl shadow-2xl border backdrop-blur-md animate-slide-up ${isSuccess ? 'bg-green-50 dark:bg-green-900/30 border-green-300 dark:border-green-700 text-green-800 dark:text-green-200' : isError ? 'bg-red-50 dark:bg-red-900/30 border-red-300 dark:border-red-700 text-red-800 dark:text-red-200' : 'bg-amber-50 dark:bg-amber-900/30 border-amber-300 dark:border-amber-700 text-amber-800 dark:text-amber-200'}`}
            >
              {isSuccess && <CheckCircle className="w-5 h-5 shrink-0 mt-0.5" />}
              {isError && <XCircle className="w-5 h-5 shrink-0 mt-0.5" />}
              {isWarning && <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />}
              <p className="text-sm flex-1">{toast.message}</p>
              <button onClick={() => removeToast(toast.id)} className="shrink-0 p-0.5 rounded hover:bg-black/10 dark:hover:bg-white/10 transition">
                <X className="w-4 h-4" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
};
