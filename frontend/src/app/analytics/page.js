"use client";

import React, { useState, useEffect } from "react";
import AuthGuard from "../components/AuthGuard";
import AppShell from "../components/AppShell";
import { 
  TrendingUp, 
  Clock, 
  FileText, 
  ShieldAlert,
  CheckCircle,
  AlertTriangle,
  XCircle,
  RefreshCw,
  BarChart3,
  Sparkles
} from "lucide-react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function AnalyticsPage() {
  const [range, setRange] = useState("30d");
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [hoveredDay, setHoveredDay] = useState(null);

  useEffect(() => {
    const fetchAnalytics = async () => {
      const token = localStorage.getItem("pr_triage_token");
      if (!token) return;
      setLoading(true);
      try {
        const res = await fetch(`${API_BASE_URL}/analytics/summary?range=${range}`, {
          headers: { "Authorization": `Bearer ${token}` }
        });
        if (res.ok) {
          setAnalytics(await res.json());
        }
      } catch (err) {
        console.error("Failed to load analytics:", err);
      } finally {
        setLoading(false);
      }
    };
    fetchAnalytics();
  }, [range]);

  const dailyData = analytics?.daily_volume || [];
  const maxDailyTotal = dailyData.reduce((max, day) => {
    const total = (day.approved || 0) + (day.escalated || 0) + (day.rejected || 0);
    return total > max ? total : max;
  }, 0) || 10;

  return (
    <AuthGuard>
      <AppShell pageTitle="Agent Analytics">
        <div className="h-full p-8 overflow-y-auto font-72 relative">
          
          <div className="max-w-7xl mx-auto space-y-6">
            
            {/* Header & Range Control */}
            <div className="liquid-glass p-6 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
              <div>
                <div className="flex items-center gap-2 text-xs font-semibold text-brass mb-1">
                  <BarChart3 className="h-4 w-4" />
                  <span>Performance Efficacy System</span>
                </div>
                <h2 className="text-xl font-bold text-white tracking-tight">
                  Agent Performance Analytics
                </h2>
                <p className="text-xs text-text-muted mt-1">
                  Efficacy audit metrics, throughput latency, and decision volume classifications.
                </p>
              </div>
              
              {/* Range Toggle */}
              <div className="flex items-center gap-2 p-1.5 liquid-glass rounded-xl">
                {["7d", "30d", "90d"].map((r) => (
                  <button
                    key={r}
                    onClick={() => setRange(r)}
                    className={`px-3.5 py-1.5 text-xs font-bold rounded-lg transition-all duration-200 cursor-pointer ${
                      range === r 
                        ? "bg-brass text-black shadow-[0_0_12px_rgba(212,175,55,0.4)]" 
                        : "text-text-muted hover:text-white"
                    }`}
                  >
                    {r.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>

            {loading ? (
              <div className="flex items-center justify-center p-16">
                <RefreshCw className="h-6 w-6 animate-spin text-brass" />
              </div>
            ) : analytics ? (
              <div className="space-y-6">
                
                {/* KPI metric tiles */}
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
                  
                  <div className="liquid-glass p-6 space-y-2 relative overflow-hidden">
                    <div className="flex items-center justify-between text-text-muted">
                      <span className="text-xs font-semibold text-text-muted uppercase tracking-wider">Auto-Approval Rate</span>
                      <TrendingUp className="h-4 w-4 text-risk-clear" />
                    </div>
                    <div className="text-3xl font-bold text-white">
                      {Math.round(analytics.auto_approval_rate * 100)}%
                    </div>
                    <span className="text-xs text-risk-clear font-medium block">Target: &gt;70% touchless release</span>
                  </div>

                  <div className="liquid-glass p-6 space-y-2 relative overflow-hidden">
                    <div className="flex items-center justify-between text-text-muted">
                      <span className="text-xs font-semibold text-text-muted uppercase tracking-wider">Avg Triage Speed</span>
                      <Clock className="h-4 w-4 text-brass" />
                    </div>
                    <div className="text-3xl font-bold text-white">
                      {analytics.avg_time_to_decision_seconds.toFixed(2)}s
                    </div>
                    <span className="text-xs text-brass font-medium block">LangGraph decision latency</span>
                  </div>

                  <div className="liquid-glass p-6 space-y-2 relative overflow-hidden">
                    <div className="flex items-center justify-between text-text-muted">
                      <span className="text-xs font-semibold text-text-muted uppercase tracking-wider">Total PRs Processed</span>
                      <FileText className="h-4 w-4 text-white" />
                    </div>
                    <div className="text-3xl font-bold text-white">
                      {analytics.total_processed}
                    </div>
                    <span className="text-xs text-text-muted font-medium block">Total requisitions triaged</span>
                  </div>

                  <div className="liquid-glass p-6 space-y-2 relative overflow-hidden">
                    <div className="flex items-center justify-between text-text-muted">
                      <span className="text-xs font-semibold text-text-muted uppercase tracking-wider">Escalated Requests</span>
                      <ShieldAlert className="h-4 w-4 text-risk-critical" />
                    </div>
                    <div className="text-3xl font-bold text-risk-critical">
                      {analytics.total_escalated}
                    </div>
                    <span className="text-xs text-risk-critical font-medium block">Routed to officer review</span>
                  </div>

                </div>

                {/* Main Daily Volume Timeline Chart */}
                <div className="liquid-glass p-6 space-y-6">
                  <div>
                    <h3 className="text-sm font-bold text-white tracking-wide uppercase">
                      Decision Timeline Classification
                    </h3>
                    <p className="text-xs text-text-muted mt-1">
                      Daily volume breakdown: Cleared (emerald), Escalated (brass), and Rejected (soft clay).
                    </p>
                  </div>

                  {dailyData.length === 0 ? (
                    <div className="h-64 flex items-center justify-center border border-dashed border-white/10 rounded-2xl text-text-muted text-xs">
                      No historical timeline data recorded for this window.
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {/* Bar Chart */}
                      <div className="h-64 flex items-end gap-3 border-b border-white/10 pb-3 overflow-x-auto pt-8">
                        {dailyData.map((day) => {
                          const total = (day.approved || 0) + (day.escalated || 0) + (day.rejected || 0);
                          const appHeight = total > 0 ? (day.approved / maxDailyTotal) * 100 : 0;
                          const escHeight = total > 0 ? (day.escalated / maxDailyTotal) * 100 : 0;
                          const rejHeight = total > 0 ? (day.rejected / maxDailyTotal) * 100 : 0;

                          return (
                            <div 
                              key={day.date} 
                              className="flex-1 min-w-[28px] max-w-[60px] flex flex-col items-center group relative cursor-pointer"
                              onMouseEnter={() => setHoveredDay(day)}
                              onMouseLeave={() => setHoveredDay(null)}
                            >
                              {/* Stacked Bar */}
                              <div className="w-full bg-white/5 border border-white/10 rounded-t-lg flex flex-col justify-end h-48 overflow-hidden transition-all group-hover:border-brass/50">
                                <div style={{ height: `${rejHeight}%` }} className="bg-risk-critical w-full transition-all duration-200" title="Rejected" />
                                <div style={{ height: `${escHeight}%` }} className="bg-brass w-full transition-all duration-200" title="Escalated" />
                                <div style={{ height: `${appHeight}%` }} className="bg-risk-clear w-full transition-all duration-200" title="Approved" />
                              </div>
                              
                              <span className="text-[10px] text-text-muted mt-2 truncate max-w-full font-mono">
                                {day.date.substring(5)}
                              </span>
                            </div>
                          );
                        })}
                      </div>

                      {/* Interactive Tooltip Area */}
                      <div className="p-4 rounded-xl liquid-glass flex items-center justify-between">
                        {hoveredDay ? (
                          <>
                            <div>
                              <span className="text-xs font-bold text-brass uppercase block">Date: {hoveredDay.date}</span>
                              <span className="text-xs text-white">Total Processed: {hoveredDay.approved + hoveredDay.escalated + hoveredDay.rejected} PRs</span>
                            </div>
                            <div className="flex gap-4 text-xs">
                              <span className="text-risk-clear font-bold">Approved: {hoveredDay.approved}</span>
                              <span className="text-brass font-bold">Escalated: {hoveredDay.escalated}</span>
                              <span className="text-risk-critical font-bold">Rejected: {hoveredDay.rejected}</span>
                            </div>
                          </>
                        ) : (
                          <div className="text-xs text-text-muted italic">
                            Hover over any bar in the chart to inspect detailed daily breakdown metrics.
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Legend */}
                  <div className="flex justify-center gap-6 text-xs pt-2">
                    <div className="flex items-center gap-2">
                      <div className="h-3 w-3 rounded-full bg-risk-clear" />
                      <span className="text-text-muted">Auto-Approved (Cleared)</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="h-3 w-3 rounded-full bg-brass" />
                      <span className="text-text-muted">Escalated (Under Review)</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="h-3 w-3 rounded-full bg-risk-critical" />
                      <span className="text-text-muted">Hard Reject (Flagged)</span>
                    </div>
                  </div>
                </div>

                {/* Ratio & Signal Drivers Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  
                  {/* Volume Ratio Classification */}
                  <div className="liquid-glass p-6 space-y-4">
                    <h3 className="text-xs font-bold text-brass uppercase tracking-wider">
                      Volume Ratio Classifications
                    </h3>
                    <div className="space-y-4 pt-1 text-xs">
                      <div>
                        <div className="flex justify-between mb-1 text-text-muted">
                          <span>Auto-Approved</span>
                          <span className="font-bold text-risk-clear">{analytics.total_approved} ({analytics.total_processed ? Math.round((analytics.total_approved/analytics.total_processed)*100) : 0}%)</span>
                        </div>
                        <div className="h-2 bg-white/5 border border-white/10 rounded-full overflow-hidden">
                          <div className="bg-risk-clear h-full rounded-full" style={{ width: `${analytics.total_processed ? (analytics.total_approved/analytics.total_processed)*100 : 0}%` }} />
                        </div>
                      </div>

                      <div>
                        <div className="flex justify-between mb-1 text-text-muted">
                          <span>Escalated</span>
                          <span className="font-bold text-brass">{analytics.total_escalated} ({analytics.total_processed ? Math.round((analytics.total_escalated/analytics.total_processed)*100) : 0}%)</span>
                        </div>
                        <div className="h-2 bg-white/5 border border-white/10 rounded-full overflow-hidden">
                          <div className="bg-brass h-full rounded-full" style={{ width: `${analytics.total_processed ? (analytics.total_escalated/analytics.total_processed)*100 : 0}%` }} />
                        </div>
                      </div>

                      <div>
                        <div className="flex justify-between mb-1 text-text-muted">
                          <span>Hard Reject</span>
                          <span className="font-bold text-risk-critical">{analytics.total_rejected} ({analytics.total_processed ? Math.round((analytics.total_rejected/analytics.total_processed)*100) : 0}%)</span>
                        </div>
                        <div className="h-2 bg-white/5 border border-white/10 rounded-full overflow-hidden">
                          <div className="bg-risk-critical h-full rounded-full" style={{ width: `${analytics.total_processed ? (analytics.total_rejected/analytics.total_processed)*100 : 0}%` }} />
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Escalation Drivers */}
                  <div className="liquid-glass p-6 space-y-4">
                    <h3 className="text-xs font-bold text-brass uppercase tracking-wider">
                      Escalation Signal Drivers
                    </h3>
                    <p className="text-xs text-text-muted">Primary trigger metrics driving AI model manual review routing.</p>
                    <div className="space-y-3 text-xs pt-1">
                      {Object.entries(analytics.escalation_reason_breakdown).map(([reason, count]) => (
                        <div key={reason} className="flex items-center justify-between border-b border-white/10 py-1.5 last:border-b-0">
                          <span className="capitalize text-white">{reason.replace("_", " ")}</span>
                          <div className="flex items-center space-x-3">
                            <span className="font-bold text-brass">{count}</span>
                            <div className="w-24 bg-white/5 border border-white/10 h-2 rounded-full overflow-hidden">
                              <div 
                                className="bg-brass h-full rounded-full" 
                                style={{ 
                                  width: `${analytics.total_escalated ? (count / analytics.total_escalated) * 100 : 0}%` 
                                }}
                              />
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                </div>

              </div>
            ) : (
              <div className="p-16 text-center text-text-muted">
                No analytics summary available.
              </div>
            )}

          </div>
        </div>
      </AppShell>
    </AuthGuard>
  );
}
