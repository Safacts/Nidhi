import React from 'react';
import { Database, Shield } from 'lucide-react';
import { Logo } from '../components/Logo';
import { ThemeToggle } from '../contexts/ThemeContext';

const Login = () => {
  const handleLogin = () => {
    // In OAuth flow, we redirect to the IdP
    const clientId = process.env.REACT_APP_RUBIX_CLIENT_ID || 'nidhi_client_id_123';
    const baseUri = window.location.origin + (window.location.pathname.startsWith('/nidhi') ? '/nidhi' : '');
    const defaultCallback = `${baseUri}/auth/callback`;
    const redirectUri = encodeURIComponent(process.env.REACT_APP_RUBIX_REDIRECT_URI || defaultCallback);
    
    // Point directly to the live identity provider
    const rubixAuthUrl = `https://novamymentor.in/o/authorize/?response_type=code&client_id=${clientId}&redirect_uri=${redirectUri}`;
    
    window.location.href = rubixAuthUrl;
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen relative bg-slate-50 dark:bg-slate-900">
      <div className="absolute top-6 right-6">
        <ThemeToggle />
      </div>
      
      <div className="relative z-10 max-w-md w-full mx-4">
        <div className="w-full p-8 bg-white dark:bg-slate-800 rounded-2xl shadow-xl border border-slate-200 dark:border-slate-700">
          <div className="flex flex-col items-center mb-8">
            <Logo className="mb-4" />
            <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Sign In</h2>
            <p className="text-slate-500 dark:text-slate-400 mt-2 text-center">
              Authenticate via Rubix IT to access the Control Plane
            </p>
          </div>

          <button 
            onClick={handleLogin}
            className="w-full flex items-center justify-center gap-3 bg-slate-900 dark:bg-slate-700 hover:bg-slate-800 dark:hover:bg-slate-600 text-white py-3 px-4 rounded-xl font-medium transition-all"
          >
            <Shield className="w-5 h-5 text-[#98FF98]" />
            Login with Rubix SSO
          </button>
        </div>
      </div>
    </div>
  );
};

export default Login;
