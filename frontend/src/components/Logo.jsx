import React from 'react';
import { Database } from 'lucide-react';

export const Logo = ({ className = "" }) => {
  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <div className="p-2 bg-gradient-to-br from-[#98FF98] to-[#4ade80] rounded-xl shadow-lg">
        <Database className="w-6 h-6 text-slate-900" />
      </div>
      <div>
        <h1 className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-slate-900 to-slate-700 dark:from-[#98FF98] dark:to-[#4ade80]">
          Nidhi
        </h1>
        <p className="text-[10px] uppercase tracking-widest font-semibold text-slate-500 dark:text-slate-400 -mt-1">
          Control Plane
        </p>
      </div>
    </div>
  );
};
