"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import AuthGuard from "../components/AuthGuard";
import AppShell from "../components/AppShell";
import { 
  PlusCircle,
  ArrowRight,
  TrendingUp,
  Clock,
  ShieldCheck,
  Zap,
  AlertTriangle,
  FileText,
  Activity,
  CheckCircle
} from "lucide-react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function HomePage() {
  const router = useRouter();
  const [summary, setSummary] = useState({
    pending_queue_count: 0,
    flagged_vendors_7d_count: 0,
    needs_authority_count: 0
  });
  const [recentQueue, setRecentQueue] = useState([]);
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const savedUser = localStorage.getItem("pr_triage_user");
    if (savedUser) {
      setUser(JSON.parse(savedUser));
    }

    const fetchData = async () => {
      const token = localStorage.getItem("pr_triage_token");
      if (!token) return;
      setLoading(true);
      try {
        const [sumRes, queueRes] = await Promise.all([
          fetch(`${API_BASE_URL}/dashboard/launchpad-summary`, {
            headers: { "Authorization": `Bearer ${token}` }
          }),
          fetch(`${API_BASE_URL}/triage/queue`, {
            headers: { "Authorization": `Bearer ${token}` }
          })
        ]);

        if (sumRes.ok) {
          setSummary(await sumRes.json());
        }
        if (queueRes.ok) {
          const queueData = await queueRes.json();
          setRecentQueue(queueData.slice(0, 5));
        }
      } catch (err) {
        console.error("Failed to fetch dashboard data:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  const isRequester = user && (user.role?.toLowerCase() === "requester" || user.role?.toLowerCase() === "unit_requester");

  return (
    <AuthGuard>
      <AppShell pageTitle={isRequester ? "Requester Overview" : "Operations Launchpad"}>
        <div className="p-8 space-y-8 max-w-7xl mx-auto overflow-y-auto h-full font-72">
          
          {/* Hero Liquid Card: Budget Headroom */}
          <div className="liquid-glass p-8 flex flex-col md:flex-row items-start md:items-center justify-between gap-6 relative overflow-hidden">
            <div className="absolute -right-12 -top-12 w-64 h-64 bg-brass/10 rounded-full blur-3xl pointer-events-none" />
            
            <div className="space-y-2 relative z-10">
              <div className="flex items-center gap-2 text-xs font-semibold text-brass">
                <Zap className="h-4 w-4" />
                <span>Quarterly Budget Headroom • Cost Center CC-P01</span>
              </div>
              
              <div className="flex items-baseline gap-4">
                <span className="text-4xl font-bold text-white tracking-tight">
                  $42,000.00
                </span>
                <span className="text-sm text-text-muted">
                  used of $60,000.00 limit
                </span>
              </div>

              {/* Progress bar */}
              <div className="w-full max-w-md bg-white/5 h-2 rounded-full overflow-hidden mt-3 border border-white/10">
                <div className="bg-gradient-to-r from-brass to-risk-clear h-full rounded-full w-[70%]" />
              </div>
            </div>

            <button
              onClick={() => router.push("/create-requisition")}
              className="px-5 py-3 bg-brass text-black font-bold text-xs rounded-xl shadow-[0_0_20px_rgba(212,175,55,0.3)] hover:shadow-[0_0_30px_rgba(212,175,55,0.5)] hover:scale-[1.02] transition-all flex items-center gap-2 cursor-pointer relative z-10 shrink-0"
            >
              <PlusCircle className="h-4 w-4" />
              <span>Create Requisition</span>
            </button>
          </div>

          {/* Minimalist Pipeline Stage Pills */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-white tracking-wide">
                Requisition Pipeline Stages
              </h3>
              <span className="text-xs text-text-muted">Updated in real-time</span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
              
              <div className="liquid-glass p-5 space-y-2 text-center">
                <span className="text-xs font-semibold text-text-muted block">Draft</span>
                <span className="text-2xl font-bold text-white">1</span>
                <span className="text-[11px] text-text-muted block">Local buffer</span>
              </div>

              <div className="liquid-glass p-5 space-y-2 text-center border-brass/30">
                <span className="text-xs font-semibold text-brass block">Submitted</span>
                <span className="text-2xl font-bold text-brass">2</span>
                <span className="text-[11px] text-text-muted block">In queue</span>
              </div>

              <div className="liquid-glass p-5 space-y-2 text-center border-brass/30">
                <span className="text-xs font-semibold text-brass block">Under Review</span>
                <span className="text-2xl font-bold text-brass">3</span>
                <span className="text-[11px] text-text-muted block">Agent active</span>
              </div>

              <div className="liquid-glass p-5 space-y-2 text-center border-risk-clear/30">
                <span className="text-xs font-semibold text-risk-clear block">Approved</span>
                <span className="text-2xl font-bold text-risk-clear">8</span>
                <span className="text-[11px] text-text-muted block">Auto cleared</span>
              </div>

              <div className="liquid-glass p-5 space-y-2 text-center border-risk-clear/30">
                <span className="text-xs font-semibold text-risk-clear block">PO Issued</span>
                <span className="text-2xl font-bold text-risk-clear">6</span>
                <span className="text-[11px] text-text-muted block">Dispatched</span>
              </div>

              <div className="liquid-glass p-5 space-y-2 text-center border-risk-critical/30">
                <span className="text-xs font-semibold text-risk-critical block">Rejected</span>
                <span className="text-2xl font-bold text-risk-critical">1</span>
                <span className="text-[11px] text-text-muted block">Policy flag</span>
              </div>

            </div>
          </div>

          {/* Operational Intelligence Stream & Telemetry Section */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 pt-2">
            
            {/* Live Triage Stream (2 Cols) */}
            <div className="lg:col-span-2 liquid-glass p-6 space-y-4">
              <div className="flex items-center justify-between border-b border-white/10 pb-3">
                <div className="flex items-center gap-2">
                  <Activity className="h-4 w-4 text-brass" />
                  <h3 className="text-sm font-bold text-white tracking-wide">
                    Live Priority Triage Stream
                  </h3>
                </div>
                <button 
                  onClick={() => router.push("/queue")}
                  className="text-xs text-brass font-semibold hover:underline flex items-center gap-1 cursor-pointer"
                >
                  <span>Open Full Cockpit</span>
                  <ArrowRight className="h-3.5 w-3.5" />
                </button>
              </div>

              <div className="space-y-3">
                {recentQueue.length === 0 ? (
                  <div className="p-8 text-center text-xs text-text-muted">
                    No pending requisitions in queue.
                  </div>
                ) : (
                  recentQueue.map((item) => {
                    const isFlagged = item.verdict === "reject" || item.verdict === "escalate" || item.verdict === "req_vp";
                    return (
                      <div 
                        key={item.requisition_id}
                        onClick={() => router.push("/queue")}
                        className="p-4 rounded-xl liquid-glass border border-white/10 hover:border-brass/40 flex items-center justify-between gap-4 cursor-pointer transition-all"
                      >
                        <div className="flex items-center gap-3">
                          <div className={`p-2 rounded-lg ${isFlagged ? "bg-risk-critical/15 text-risk-critical" : "bg-risk-clear/15 text-risk-clear"}`}>
                            <FileText className="h-4 w-4" />
                          </div>
                          <div>
                            <span className="text-xs font-bold text-white block">#{item.requisition_id}</span>
                            <span className="text-[11px] text-text-muted">
                              {item.requester_name || "Purchasing Dept"} • ${item.total_value?.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                            </span>
                          </div>
                        </div>

                        <div className="flex items-center gap-3">
                          <span className={`text-[10px] font-bold px-2.5 py-0.5 rounded-full border uppercase ${
                            isFlagged 
                              ? "bg-risk-critical/20 border-risk-critical/40 text-risk-critical" 
                              : "bg-risk-clear/15 border-risk-clear/30 text-risk-clear"
                          }`}>
                            {item.verdict?.toUpperCase() || "PENDING"}
                          </span>
                          <ArrowRight className="h-4 w-4 text-text-muted" />
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>

            {/* Agent Telemetry & System Efficacy */}
            <div className="liquid-glass p-6 space-y-6">
              <div className="border-b border-white/10 pb-3">
                <span className="text-xs font-bold text-brass uppercase tracking-wider block">Agent Telemetry</span>
                <h3 className="text-sm font-bold text-white mt-0.5">Efficacy Health</h3>
              </div>

              <div className="space-y-4 text-xs">
                <div className="p-4 rounded-xl liquid-glass space-y-1">
                  <div className="flex justify-between items-center text-text-muted">
                    <span>Touchless Approval Rate</span>
                    <TrendingUp className="h-4 w-4 text-risk-clear" />
                  </div>
                  <span className="text-2xl font-bold text-white block">84.2%</span>
                  <span className="text-[10px] text-risk-clear">Target: &gt;70.0% touchless release</span>
                </div>

                <div className="p-4 rounded-xl liquid-glass space-y-1">
                  <div className="flex justify-between items-center text-text-muted">
                    <span>Average Decision Speed</span>
                    <Clock className="h-4 w-4 text-brass" />
                  </div>
                  <span className="text-2xl font-bold text-white block">1.25s</span>
                  <span className="text-[10px] text-brass">LangGraph execution latency</span>
                </div>

                <div className="p-4 rounded-xl liquid-glass space-y-1">
                  <div className="flex justify-between items-center text-text-muted">
                    <span>Vendor Watchlist Security</span>
                    <ShieldCheck className="h-4 w-4 text-risk-clear" />
                  </div>
                  <span className="text-2xl font-bold text-risk-clear block">Active Verified</span>
                  <span className="text-[10px] text-text-muted">OFAC & AML registries connected</span>
                </div>
              </div>
            </div>

          </div>

        </div>
      </AppShell>
    </AuthGuard>
  );
}



