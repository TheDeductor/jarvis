import React, { useState } from 'react';
import type { SimulationState, RoomId } from '../types';
import { submitOccupantFeedback } from '../api';
import { Thermometer, Droplets, Wind, ThumbsUp, ThumbsDown, CheckCircle } from 'lucide-react';
import NLPChatPanel from './NLPChatPanel';

interface OccupantViewProps {
  state: SimulationState;
  userRoom: string;
  onRefresh: () => void;
}

export default function OccupantView({ state, userRoom, onRefresh }: OccupantViewProps) {
  const [selectedRoomId, setSelectedRoomId] = useState<RoomId>((userRoom as RoomId) || 'A');
  const room = state.rooms[selectedRoomId];
  
  const [isComfortable, setIsComfortable] = useState<boolean>(true);
  const [comfortRating, setComfortRating] = useState<number>(5);
  const [reusePreference, setReusePreference] = useState<boolean>(true);
  
  const [status, setStatus] = useState<'idle' | 'submitting' | 'success' | 'error'>('idle');
  
  if (!room) {
    return (
      <div className="flex items-center justify-center h-screen bg-[#070d18] text-white">
        <p>Loading room data for {selectedRoomId}...</p>
      </div>
    );
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatus('submitting');
    try {
      await submitOccupantFeedback({
        room_id: selectedRoomId,
        requested_temp: room.setpoint_c, // Use the current setpoint since there is no slider
        actual_temp: room.temperature_c,
        humidity: room.humidity_pct,
        hvac_power: room.hvac_power_kw,
        is_comfortable: isComfortable,
        comfort_rating: comfortRating,
        reuse_preference: reusePreference,
      });
      setStatus('success');
      setTimeout(() => setStatus('idle'), 3000);
    } catch (err) {
      console.error(err);
      setStatus('error');
    }
  };

  return (
    <div className="max-w-2xl mx-auto px-6 py-8 space-y-6">
      
      {/* Room Selector */}
      <div className="flex items-center justify-center gap-4 mb-4">
        <span className="text-sm font-bold uppercase tracking-widest text-slate-400">Select Room:</span>
        <div className="flex gap-2 bg-[#09101d] p-1.5 rounded-xl border border-slate-800 shadow-inner">
          {(['A', 'B', 'C', 'D'] as RoomId[]).map((r) => (
            <button
              key={r}
              onClick={() => setSelectedRoomId(r)}
              className={`px-4 py-1.5 rounded-lg font-bold transition-all ${
                selectedRoomId === r
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              Room {r}
            </button>
          ))}
        </div>
      </div>

      <div className="bg-[#0c1424] border border-slate-800 rounded-2xl shadow-xl overflow-hidden">
        
        <div className="bg-[#09101d] px-6 py-4 border-b border-slate-800 flex items-center justify-between">
          <h2 className="text-lg font-bold text-white tracking-tight">Room {selectedRoomId} Controls</h2>
          <span className="text-xs font-semibold px-3 py-1 rounded bg-slate-800 text-slate-300 border border-slate-700">Occupant Mode</span>
        </div>

        <div className="p-6">
          {/* Telemetry Display */}
          <div className="grid grid-cols-3 gap-4 mb-6">
            <div className="bg-[#0f192b] border border-slate-800 rounded-xl p-4 flex flex-col items-center justify-center">
              <Thermometer size={24} className="text-rose-400 mb-2" />
              <span className="text-2xl font-bold text-white">{room.temperature_c.toFixed(1)}°</span>
              <span className="text-xs text-slate-400 uppercase tracking-widest mt-1">Current Temp</span>
            </div>
            <div className="bg-[#0f192b] border border-slate-800 rounded-xl p-4 flex flex-col items-center justify-center">
              <Droplets size={24} className="text-sky-400 mb-2" />
              <span className="text-2xl font-bold text-white">{room.humidity_pct.toFixed(0)}%</span>
              <span className="text-xs text-slate-400 uppercase tracking-widest mt-1">Humidity</span>
            </div>
            <div className="bg-[#0f192b] border border-slate-800 rounded-xl p-4 flex flex-col items-center justify-center">
              <Wind size={24} className="text-teal-400 mb-2" />
              <span className="text-2xl font-bold text-white">{room.airflow_lps.toFixed(0)} L/s</span>
              <span className="text-xs text-slate-400 uppercase tracking-widest mt-1">Airflow</span>
            </div>
          </div>

          {/* Chat Interface */}
          <div className="mb-8">
            <NLPChatPanel onRefresh={onRefresh} contextRoom={selectedRoomId} />
          </div>

          <hr className="border-slate-800 mb-6" />

          {/* Explicit Comfort Feedback */}
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="grid grid-cols-2 gap-6">
              <div>
                <label className="block text-sm font-semibold text-slate-300 mb-3 uppercase tracking-wide">
                  Are you comfortable?
                </label>
                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={() => setIsComfortable(true)}
                    className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg font-bold border transition-colors ${
                      isComfortable 
                      ? 'bg-emerald-500/20 border-emerald-500/50 text-emerald-400' 
                      : 'bg-slate-800/50 border-slate-700 text-slate-400 hover:bg-slate-800'
                    }`}
                  >
                    <ThumbsUp size={16} /> Yes
                  </button>
                  <button
                    type="button"
                    onClick={() => setIsComfortable(false)}
                    className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg font-bold border transition-colors ${
                      !isComfortable 
                      ? 'bg-rose-500/20 border-rose-500/50 text-rose-400' 
                      : 'bg-slate-800/50 border-slate-700 text-slate-400 hover:bg-slate-800'
                    }`}
                  >
                    <ThumbsDown size={16} /> No
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-sm font-semibold text-slate-300 mb-3 uppercase tracking-wide">
                  Comfort Rating (1-5)
                </label>
                <div className="flex gap-2">
                  {[1, 2, 3, 4, 5].map((rating) => (
                    <button
                      key={rating}
                      type="button"
                      onClick={() => setComfortRating(rating)}
                      className={`flex-1 py-2 rounded-lg font-bold border transition-colors ${
                        comfortRating === rating
                        ? 'bg-blue-500 border-blue-400 text-white shadow-sm shadow-blue-500/30'
                        : 'bg-slate-800 border-slate-700 text-slate-400 hover:bg-slate-700'
                      }`}
                    >
                      {rating}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div>
              <label className="flex items-center gap-3 cursor-pointer p-3 rounded-lg border border-slate-800 bg-slate-900/50 hover:bg-slate-800/80 transition-colors">
                <input
                  type="checkbox"
                  checked={reusePreference}
                  onChange={(e) => setReusePreference(e.target.checked)}
                  className="w-5 h-5 rounded border-slate-700 bg-slate-800 text-blue-500 focus:ring-blue-500/30 focus:ring-offset-0"
                />
                <div>
                  <div className="text-sm font-semibold text-slate-200">Remember my preference</div>
                  <div className="text-xs text-slate-400 mt-0.5">Apply these settings automatically next time.</div>
                </div>
              </label>
            </div>

            <button
              type="submit"
              disabled={status === 'submitting'}
              className="w-full py-3 px-4 bg-blue-600 hover:bg-blue-500 text-white font-bold rounded-xl shadow-lg shadow-blue-600/20 transition-all flex justify-center items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {status === 'submitting' ? (
                <span className="animate-pulse">Submitting...</span>
              ) : status === 'success' ? (
                <>
                  <CheckCircle size={18} />
                  Feedback Saved
                </>
              ) : (
                'Submit Feedback Rating'
              )}
            </button>
            
            {status === 'error' && (
              <p className="text-sm text-rose-400 text-center font-medium mt-2">Failed to submit feedback. Please try again.</p>
            )}
          </form>
        </div>
      </div>
    </div>
  );
}
