import React, { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Loader2 } from 'lucide-react';

const AuthCallback = () => {
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const code = params.get('code');

    const errorParam = params.get('error');

    if (code) {
      exchangeCodeForToken(code);
    } else if (errorParam) {
      setError(`OAuth Error: ${errorParam} (Full search: ${location.search})`);
      setTimeout(() => navigate('/login'), 5000);
    } else {
      setError(`No authorization code found. URL search params: ${location.search || 'None'}`);
      setTimeout(() => navigate('/login'), 5000);
    }
  }, [location, navigate]);

  const exchangeCodeForToken = async (code) => {
    try {
      const backendUrl = `/api/sso/callback/`;
      const baseUri = window.location.origin + (window.location.pathname.startsWith('/nidhi') ? '/nidhi' : '');
      const redirectUri = process.env.REACT_APP_RUBIX_REDIRECT_URI || `${baseUri}/auth/callback`;
      const response = await fetch(backendUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, redirect_uri: redirectUri })
      });

      const data = await response.json();
      
      if (response.ok && data.token) {
        localStorage.setItem('sso_token', data.token);
        
        // Fetch user profile info
        try {
          const profileResp = await fetch(`/api/me/`, {
            headers: { 'Authorization': `Bearer ${data.token}` }
          });
          if (profileResp.ok) {
            const profileData = await profileResp.json();
            localStorage.setItem('user_role', profileData.role);
          }
        } catch (e) {
          console.error("Failed to fetch profile info", e);
        }
        
        navigate('/dashboard');
      } else {
        setError(data.error || 'Authentication failed');
        setTimeout(() => navigate('/login'), 3000);
      }
    } catch (err) {
      setError('Network error during authentication.');
      setTimeout(() => navigate('/login'), 3000);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-900">
      <div className="bg-slate-800/50 backdrop-blur-xl border border-slate-700 p-8 rounded-2xl shadow-2xl flex flex-col items-center">
        {error ? (
          <div className="text-red-400 text-center">
            <p className="font-bold mb-2">Login Failed</p>
            <p>{error}</p>
            <p className="text-sm mt-4 text-slate-500">Redirecting to login...</p>
          </div>
        ) : (
          <div className="flex flex-col items-center text-[#98FF98]">
            <Loader2 className="w-12 h-12 animate-spin mb-4" />
            <p className="font-semibold tracking-wide">Authenticating with Rubix IT...</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default AuthCallback;
