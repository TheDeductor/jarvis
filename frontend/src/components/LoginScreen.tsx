import React, { useState } from 'react';
import { login } from '../api';

interface LoginScreenProps {
  onLogin: (token: string, role: string, room: string | null) => void;
  onDemo: () => void;
}

export default function LoginScreen({ onLogin, onDemo }: LoginScreenProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const data = await login(username, password);
      onLogin(data.access_token, data.role, data.room);
    } catch (err: any) {
      setError('Invalid username or password.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#070d18] flex items-center justify-center p-4">
      <div className="bg-[#0c1424] border border-slate-800 rounded-xl p-8 w-full max-w-md shadow-2xl">
        <div className="text-center mb-8">
          <div className="w-12 h-12 bg-blue-500 rounded-full mx-auto mb-4 shadow-lg shadow-blue-500/50 flex items-center justify-center">
            <span className="text-white font-bold text-xl">DT</span>
          </div>
          <h2 className="text-2xl font-bold text-white tracking-tight">Digital Twin Login</h2>
          <p className="text-sm text-slate-400 mt-2">Enter your credentials to continue</p>
        </div>

        {error && (
          <div className="mb-4 bg-rose-500/10 border border-rose-500/30 text-rose-400 text-sm p-3 rounded-md">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-bold text-slate-300 uppercase tracking-wider mb-2">
              Username
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-[#070d18] border border-slate-700 rounded-lg px-4 py-3 text-slate-200 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
              placeholder="e.g. admin or occupantA"
              required
            />
          </div>

          <div>
            <label className="block text-xs font-bold text-slate-300 uppercase tracking-wider mb-2">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-[#070d18] border border-slate-700 rounded-lg px-4 py-3 text-slate-200 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
              placeholder="••••••••"
              required
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 px-4 rounded-lg transition-colors shadow-lg shadow-blue-600/20 disabled:opacity-50"
          >
            {loading ? 'Authenticating...' : 'Sign In'}
          </button>
        </form>

        <div className="mt-4 pt-4 border-t border-slate-800">
          <button
            onClick={onDemo}
            className="w-full bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white font-semibold py-3 px-4 rounded-lg transition-colors border border-slate-700"
          >
            Continue in Demo Mode
          </button>
          <p className="text-xs text-slate-500 text-center mt-2">
            Demo mode uses static data. No backend required.
          </p>
        </div>

        <div className="mt-4 bg-slate-900/60 rounded-lg p-3 border border-slate-800">
          <p className="text-xs text-slate-400 font-semibold mb-1 uppercase tracking-wider">Default credentials (live mode)</p>
          <p className="text-xs text-slate-500">admin / admin123 &nbsp;·&nbsp; operator / op123</p>
        </div>
      </div>
    </div>
  );
}
