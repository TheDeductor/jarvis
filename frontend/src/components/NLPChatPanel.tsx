// NLPChatPanel.tsx — AI Feedback Assistant panel (in-memory chat, no persistence).
// Groq LLM parses complaints → structured HVAC constraints → applied immediately.

import React, { useState, useRef, useEffect, useCallback } from 'react';
import type { ChatMessage, FeedbackConstraint } from '../types';
import { submitFeedback } from '../api';

// ── helpers ───────────────────────────────────────────────────────────────────

function uid() {
  return Math.random().toString(36).slice(2, 10);
}

function formatTime(d: Date) {
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

const ACTION_LABELS: Record<string, string> = {
  increase_temp: '↑ Temperature',
  decrease_temp: '↓ Temperature',
  increase_airflow: '↑ Airflow',
  decrease_airflow: '↓ Airflow',
  set_setpoint: 'Set Setpoint',
  none: 'No Action',
};

const ACTION_COLORS: Record<string, string> = {
  increase_temp: 'text-orange-400 border-orange-500/40 bg-orange-500/10',
  decrease_temp: 'text-sky-400 border-sky-500/40 bg-sky-500/10',
  increase_airflow: 'text-teal-400 border-teal-500/40 bg-teal-500/10',
  decrease_airflow: 'text-purple-400 border-purple-500/40 bg-purple-500/10',
  set_setpoint: 'text-amber-400 border-amber-500/40 bg-amber-500/10',
  none: 'text-slate-400 border-slate-500/40 bg-slate-500/10',
};

const URGENCY_CONFIG: Record<string, any> = {
  high: { dot: 'bg-red-500', label: 'HIGH', cls: 'text-red-400' },
  medium: { dot: 'bg-amber-400', label: 'MED', cls: 'text-amber-400' },
  low: { dot: 'bg-emerald-400', label: 'LOW', cls: 'text-emerald-400' },
};

const QUICK_COMPLAINTS = [
  "I'm freezing in Room A!",
  'Room B is way too hot',
  'Too much draft in Room C',
  'Room D feels stuffy',
];

// ── sub-components ────────────────────────────────────────────────────────────

function ConstraintCard({ c, action_taken }: { c: FeedbackConstraint; action_taken?: string }) {
  const actionCls = ACTION_COLORS[c.action] ?? ACTION_COLORS.none;
  const urgency = URGENCY_CONFIG[c.urgency] ?? URGENCY_CONFIG.medium;
  const confidencePct = Math.round(c.confidence * 100);

  return (
    <div className="mt-2 rounded-lg border border-white/10 bg-slate-800/70 p-3 space-y-2.5 text-xs">
      {/* Row 1: Room + Action + Urgency */}
      <div className="flex flex-wrap items-center gap-2">
        {c.room_id ? (
          <span className="px-2 py-0.5 rounded-md bg-blue-500/20 border border-blue-500/40 text-blue-300 font-bold tracking-wide">
            Room {c.room_id}
          </span>
        ) : (
          <span className="px-2 py-0.5 rounded-md bg-slate-600/40 border border-slate-500/30 text-slate-400 font-bold">
            All Rooms
          </span>
        )}

        <span className={`px-2 py-0.5 rounded-md border font-semibold ${actionCls}`}>
          {ACTION_LABELS[c.action] ?? c.action}
          {c.action !== 'none' && c.setpoint_delta_c !== 0 && (
            <span className="ml-1 opacity-80">
              {c.action === 'set_setpoint'
                ? `→ ${c.setpoint_delta_c.toFixed(1)}°C`
                : `${c.setpoint_delta_c > 0 ? '+' : ''}${c.setpoint_delta_c.toFixed(1)}${
                    c.action.includes('airflow') ? ' L/s' : '°C'
                  }`}
            </span>
          )}
        </span>

        <span className={`flex items-center gap-1 font-bold ${urgency.cls}`}>
          <span className={`w-1.5 h-1.5 rounded-full ${urgency.dot}`} />
          {urgency.label}
        </span>
      </div>

      {/* Row 2: Confidence bar */}
      <div className="flex items-center gap-2">
        <span className="text-slate-500 shrink-0">Confidence</span>
        <div className="flex-1 h-1 rounded-full bg-slate-700 overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-blue-500 to-violet-500 transition-all duration-500"
            style={{ width: `${confidencePct}%` }}
          />
        </div>
        <span className="text-slate-400 shrink-0 font-mono">{confidencePct}%</span>
      </div>

      {/* Row 3: Action taken */}
      {action_taken && action_taken !== 'No action taken.' && (
        <div className="flex items-start gap-1.5 text-emerald-400/90">
          <span className="mt-0.5 shrink-0">✓</span>
          <span>{action_taken}</span>
        </div>
      )}
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-2 px-3 py-2 max-w-[160px] rounded-2xl rounded-tl-sm bg-slate-700/60 border border-white/10">
      <span className="text-xs text-slate-400 font-medium">AI thinking</span>
      <span className="flex gap-1">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-bounce"
            style={{ animationDelay: `${i * 0.18}s` }}
          />
        ))}
      </span>
    </div>
  );
}

// ── main component ────────────────────────────────────────────────────────────

interface Props {
  onRefresh: () => void;
}

export default function NLPChatPanel({ onRefresh }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: uid(),
      role: 'assistant',
      text: 'Hi! I\'m your AI Building Assistant. Tell me how you\'re feeling — I\'ll adjust the HVAC system automatically.',
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const send = useCallback(
    async (text: string) => {
      const complaint = text.trim();
      if (!complaint || loading) return;

      // Add user message
      const userMsg: ChatMessage = {
        id: uid(),
        role: 'user',
        text: complaint,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setInput('');
      setLoading(true);

      try {
        const res = await submitFeedback(complaint);
        const aiMsg: ChatMessage = {
          id: uid(),
          role: 'assistant',
          text: res.constraint.rationale,
          constraint: res.constraint,
          action_taken: res.action_taken,
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, aiMsg]);
        // Refresh simulation state so dashboard reflects new setpoints instantly
        onRefresh();
      } catch (err: any) {
        const errMsg: ChatMessage = {
          id: uid(),
          role: 'assistant',
          text:
            err?.response?.data?.detail ??
            'Failed to connect to the AI backend. Is FastAPI running?',
          timestamp: new Date(),
          error: true,
        };
        setMessages((prev) => [...prev, errMsg]);
      } finally {
        setLoading(false);
        textareaRef.current?.focus();
      }
    },
    [loading, onRefresh]
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  };

  return (
    <div
      id="nlp-chat-panel"
      className="flex flex-col rounded-xl border border-slate-800 bg-[#0c1424] backdrop-blur-sm overflow-hidden mt-4 shadow-sm"
      style={{ height: '420px' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800 bg-[#09101d] shrink-0">
        <div className="flex items-center gap-3">
          {/* Animated AI icon */}
          <div className="relative w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center shadow-md shadow-blue-500/20">
            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15M14.25 3.104c.251.023.501.05.75.082M19.8 15l-1.575 1.575a3.75 3.75 0 01-2.651 1.097H8.426c-.995 0-1.95-.394-2.651-1.097L4.2 15m15.6 0l-5.37-5.37m0 0L9.75 14.5M19.8 15L14.25 9.63m-4.5 4.87L4.2 15" />
            </svg>
            {loading && (
              <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-blue-400 animate-ping" />
            )}
          </div>
          <div>
            <h3 className="text-sm font-bold text-white">AI Feedback Assistant</h3>
            <p className="text-xs text-slate-300">Natural language complaint parsing</p>
          </div>
        </div>
        <span className={`text-xs font-bold px-2.5 py-0.5 rounded border ${
          loading
            ? 'text-blue-300 border-blue-500/40 bg-blue-500/15 animate-pulse'
            : 'text-emerald-300 border-emerald-500/40 bg-emerald-500/15'
        }`}>
          {loading ? 'Processing…' : 'Ready'}
        </span>
      </div>

      {/* Messages list */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                msg.role === 'user'
                  ? 'rounded-tr-sm bg-blue-600 text-white shadow-sm'
                  : msg.error
                  ? 'rounded-tl-sm bg-rose-950/80 text-rose-200 border border-rose-800/60'
                  : 'rounded-tl-sm bg-[#131d31] text-slate-100 border border-slate-700/60'
              }`}
            >
              {msg.text}

              {/* Constraint card beneath AI message */}
              {msg.role === 'assistant' && msg.constraint && msg.constraint.action !== 'none' && (
                <ConstraintCard c={msg.constraint} action_taken={msg.action_taken} />
              )}
            </div>
            <span className="text-xs text-slate-400 px-1 mt-1 font-medium">{formatTime(msg.timestamp)}</span>
          </div>
        ))}

        {loading && (
          <div className="flex items-start">
            <TypingIndicator />
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Quick complaint chips */}
      <div className="px-4 py-2 flex gap-2 flex-wrap border-t border-slate-800 shrink-0 bg-[#09101d]">
        {QUICK_COMPLAINTS.map((q) => (
          <button
            key={q}
            id={`quick-complaint-${q.replace(/\s+/g, '-').replace(/[^a-zA-Z0-9-]/g, '').toLowerCase()}`}
            onClick={() => send(q)}
            disabled={loading}
            className="text-xs px-3 py-1 rounded-full border border-slate-700 bg-slate-800 text-slate-200 hover:border-blue-500 hover:text-white hover:bg-blue-600/20 transition-all font-medium disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {q}
          </button>
        ))}
      </div>

      {/* Input */}
      <div className="px-4 pb-4 pt-2.5 flex gap-2 shrink-0 border-t border-slate-800 bg-[#0c1424]">
        <textarea
          ref={textareaRef}
          id="nlp-chat-input"
          rows={1}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
          placeholder="Describe how you feel… (Enter to send)"
          className="flex-1 resize-none bg-[#080e1b] border border-slate-700 rounded-xl px-3.5 py-2 text-sm text-white placeholder-slate-400 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all disabled:opacity-50"
          style={{ minHeight: '42px', maxHeight: '100px' }}
        />
        <button
          id="nlp-send-btn"
          onClick={() => send(input)}
          disabled={loading || !input.trim()}
          className="shrink-0 w-10 h-10 self-end rounded-xl bg-blue-600 hover:bg-blue-500 text-white flex items-center justify-center shadow-md transition-all disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {loading ? (
            <svg className="w-4 h-4 text-white animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
            </svg>
          ) : (
            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
            </svg>
          )}
        </button>
      </div>
    </div>
  );
}
