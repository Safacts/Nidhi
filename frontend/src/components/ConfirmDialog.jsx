import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { AlertTriangle, X } from 'lucide-react';

const ConfirmContext = createContext(null);

export const useConfirm = () => useContext(ConfirmContext);

export const ConfirmProvider = ({ children }) => {
  const [state, setState] = useState({ open: false, message: '', resolve: null });

  const showConfirm = useCallback((message) => {
    return new Promise((resolve) => {
      setState({ open: true, message, resolve });
    });
  }, []);

  const handleConfirm = useCallback(() => {
    state.resolve(true);
    setState({ open: false, message: '', resolve: null });
  }, [state]);

  const handleCancel = useCallback(() => {
    state.resolve(false);
    setState({ open: false, message: '', resolve: null });
  }, [state]);

  useEffect(() => {
    if (state.open) {
      const handleKey = (e) => { if (e.key === 'Escape') handleCancel(); };
      document.addEventListener('keydown', handleKey);
      return () => document.removeEventListener('keydown', handleKey);
    }
  }, [state.open, handleCancel]);

  if (!state.open) return <ConfirmContext.Provider value={{ showConfirm }}>{children}</ConfirmContext.Provider>;

  return (
    <ConfirmContext.Provider value={{ showConfirm }}>
      {children}
      <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/40 backdrop-blur-sm">
        <div className="bg-white dark:bg-slate-800 p-6 rounded-xl border border-slate-300 dark:border-slate-700 shadow-2xl max-w-md w-full mx-4 animate-scale-in">
          <div className="flex items-start gap-4">
            <div className="p-2 rounded-full bg-amber-100 dark:bg-amber-900/30 shrink-0">
              <AlertTriangle className="w-6 h-6 text-amber-600 dark:text-amber-400" />
            </div>
            <div className="flex-1">
              <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-200 mb-2">Confirm</h3>
              <p className="text-sm text-slate-600 dark:text-slate-400 mb-6">{state.message}</p>
              <div className="flex justify-end gap-3">
                <button
                  onClick={handleCancel}
                  className="px-4 py-2 text-sm text-slate-600 dark:text-slate-400 bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 rounded-lg transition font-medium"
                >
                  Cancel
                </button>
                <button
                  onClick={handleConfirm}
                  className="px-4 py-2 text-sm text-white bg-red-600 hover:bg-red-700 rounded-lg transition font-medium"
                >
                  Confirm
                </button>
              </div>
            </div>
            <button onClick={handleCancel} className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-700 transition">
              <X className="w-5 h-5 text-slate-400" />
            </button>
          </div>
        </div>
      </div>
    </ConfirmContext.Provider>
  );
};
