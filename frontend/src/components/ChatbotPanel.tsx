import React, { useState, useRef, useEffect } from 'react';
import { Send, Bot, User } from 'lucide-react';
import { submitFeedback } from '../api';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

export default function ChatbotPanel({ onRefresh }: { onRefresh: () => void }) {
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: 'Hi! I am the NLP Constraint Engine. Tell me if any zone feels too hot or cold, and I will force the AI to adjust.' }
  ]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || busy) return;

    const userMsg = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setBusy(true);

    try {
      const res = await submitFeedback(userMsg);
      const reply = res.constraint?.rationale ?? res.action_taken ?? 'Action applied.';
      setMessages(prev => [...prev, { role: 'assistant', content: reply }]);
      onRefresh(); // Refresh the UI to show the new constraint
    } catch (e: any) {
      const errorMsg = e.response?.data?.detail ?? 'Failed to connect to the NLP engine.';
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${errorMsg}` }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl flex flex-col overflow-hidden h-[400px]">
      <div className="px-4 py-3 bg-slate-800/80 border-b border-slate-700/50 flex items-center gap-2">
        <Bot size={16} className="text-sky-400" />
        <h2 className="text-xs font-bold uppercase tracking-widest text-slate-300">
          NLP Feedback
        </h2>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg, i) => (
          <div key={i} className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
            <div className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 ${
              msg.role === 'user' ? 'bg-slate-600 text-slate-300' : 'bg-sky-500/20 text-sky-400'
            }`}>
              {msg.role === 'user' ? <User size={12} /> : <Bot size={12} />}
            </div>
            <div className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
              msg.role === 'user' 
                ? 'bg-slate-600 text-white rounded-tr-none' 
                : 'bg-slate-700/50 text-slate-200 rounded-tl-none border border-slate-600/50'
            }`}>
              {msg.content}
            </div>
          </div>
        ))}
        {busy && (
          <div className="flex gap-3">
            <div className="w-6 h-6 rounded-full bg-sky-500/20 text-sky-400 flex items-center justify-center shrink-0">
              <Bot size={12} />
            </div>
            <div className="bg-slate-700/50 rounded-lg rounded-tl-none border border-slate-600/50 px-3 py-2 text-sm text-slate-400 flex items-center gap-1">
              <span className="w-1.5 h-1.5 bg-slate-500 rounded-full animate-bounce" />
              <span className="w-1.5 h-1.5 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-1.5 h-1.5 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="p-3 border-t border-slate-700/50 bg-slate-800/50 flex gap-2">
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="e.g. It is freezing in Zone A..."
          disabled={busy}
          className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-sky-500/50 transition-colors disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={!input.trim() || busy}
          className="bg-sky-500 hover:bg-sky-400 text-white rounded-lg px-3 py-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Send size={16} />
        </button>
      </form>
    </div>
  );
}
