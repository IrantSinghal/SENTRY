"use client";

import React, { useState, useEffect } from "react";
import AuthGuard from "../components/AuthGuard";
import AppShell from "../components/AppShell";
import { 
  ShieldAlert, 
  Search, 
  RefreshCw, 
  Users, 
  AlertTriangle, 
  XCircle, 
  CheckCircle,
  FileCheck2,
  ExternalLink,
  ShieldCheck,
  Building2,
  Newspaper
} from "lucide-react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function VendorScreeningPage() {
  const [screenings, setScreenings] = useState([]);
  const [summary, setSummary] = useState({
    total_screened: 0,
    flagged_sanctions: 0,
    flagged_adverse_media: 0,
    flagged_registry_invalid: 0
  });
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedVendorId, setSelectedVendorId] = useState(null);
  const [refreshLoading, setRefreshLoading] = useState({});

  const fetchScreenings = async (token) => {
    try {
      const res = await fetch(`${API_BASE_URL}/vendors/screening`, {
        headers: { "Authorization": `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setScreenings(data);
        if (data.length > 0 && !selectedVendorId) {
          setSelectedVendorId(data[0].vendor_id);
        }
      }
    } catch (err) {
      console.error("Failed to load screenings:", err);
    }
  };

  const fetchSummary = async (token) => {
    try {
      const res = await fetch(`${API_BASE_URL}/vendors/screening-summary`, {
        headers: { "Authorization": `Bearer ${token}` }
      });
      if (res.ok) {
        setSummary(await res.json());
      }
    } catch (err) {
      console.error("Failed to load screening summary:", err);
    }
  };

  const loadAllData = async () => {
    const token = localStorage.getItem("pr_triage_token");
    if (!token) return;
    setLoading(true);
    await Promise.all([
      fetchScreenings(token),
      fetchSummary(token)
    ]);
    setLoading(false);
  };

  useEffect(() => {
    loadAllData();
  }, []);

  const handleRefresh = async (vendorId) => {
    const token = localStorage.getItem("pr_triage_token");
    if (!token) return;
    setRefreshLoading(prev => ({ ...prev, [vendorId]: true }));
    try {
      const res = await fetch(`${API_BASE_URL}/vendors/${vendorId}/screening/refresh`, {
        method: "POST",
        headers: { "Authorization": `Bearer ${token}` }
      });
      if (res.ok) {
        const updated = await res.json();
        setScreenings(prev => 
          prev.map(item => item.vendor_id === vendorId ? updated : item)
        );
        await fetchSummary(token);
      } else {
        alert("Failed to refresh screening.");
      }
    } catch (err) {
      console.error(err);
      alert("Error refreshing screening.");
    } finally {
      setRefreshLoading(prev => ({ ...prev, [vendorId]: false }));
    }
  };

  const filteredScreenings = screenings.filter(item => 
    item.vendor_id.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const selectedVendor = screenings.find(item => item.vendor_id === selectedVendorId);

  return (
    <AuthGuard>
      <AppShell pageTitle="Vendor Screening">
        <div className="h-full flex overflow-hidden font-72">
          
          {/* Left Column (4/12): Search & screening/status cards list */}
          <div className="w-4/12 border-r border-white/10 bg-surface-base relative flex flex-col overflow-hidden">
            
            {/* Search header */}
            <div className="p-4 border-b border-white/10 liquid-glass relative z-10 flex flex-col gap-3 shrink-0">
              <div className="flex items-center gap-2 text-xs font-bold text-brass uppercase tracking-wider">
                <Users className="h-4 w-4" />
                <span>Registry Index</span>
              </div>
              <div className="relative">
                <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-text-muted" />
                <input 
                  type="text" 
                  placeholder="Search Vendor ID..." 
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-9 pr-3 py-2 liquid-input text-xs w-full"
                />
              </div>
            </div>

            {/* List container */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3 relative z-10">
              {loading ? (
                <div className="flex justify-center py-12">
                  <RefreshCw className="h-6 w-6 animate-spin text-brass" />
                </div>
              ) : filteredScreenings.length === 0 ? (
                <div className="text-center py-12 text-xs text-text-muted">
                  No vendor records found.
                </div>
              ) : (
                filteredScreenings.map((v) => {
                  const isFlagged = v.sanctions_match || v.adverse_media_flagged || v.registry_verified === false;
                  const isSelected = v.vendor_id === selectedVendorId;

                  return (
                    <div
                      key={v.vendor_id}
                      onClick={() => setSelectedVendorId(v.vendor_id)}
                      className={`p-4 rounded-xl border relative hover:border-brass/50 cursor-pointer transition-all ${
                        isSelected 
                          ? "liquid-glass border-brass/50 ring-1 ring-brass/40" 
                          : "liquid-glass border-white/10"
                      }`}
                    >
                      {/* Left accent bar */}
                      <div className={`absolute left-0 top-0 bottom-0 w-1.5 rounded-l-xl ${isFlagged ? "bg-risk-critical" : "bg-risk-clear"}`} />
                      
                      <div className="flex justify-between items-start pl-2">
                        <div>
                          <span className="text-xs font-bold text-white">{v.vendor_id}</span>
                          <span className="text-[11px] text-text-muted block mt-1">Checked: {new Date(v.checked_at).toLocaleDateString()}</span>
                        </div>
                        <div>
                          <span className={`text-[10px] font-bold px-2.5 py-0.5 rounded-full border uppercase ${
                            isFlagged 
                              ? "bg-risk-critical/20 border-risk-critical/40 text-risk-critical" 
                              : "bg-risk-clear/15 border-risk-clear/30 text-risk-clear"
                          }`}>
                            {isFlagged ? "Flagged" : "Passed"}
                          </span>
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Middle Column (5/12): Intelligence Dossier details on liquid glass dark panel */}
          <div className="w-5/12 border-r border-white/10 bg-surface-panel overflow-y-auto p-6 space-y-6">
            {selectedVendor ? (
              <div className="space-y-6">
                
                {/* Header */}
                <div className="pb-3 border-b border-white/10">
                  <span className="text-xs font-bold text-brass uppercase tracking-wider block">Compliance Report</span>
                  <h3 className="text-lg font-bold text-white mt-1">
                    Intelligence Dossier: {selectedVendor.vendor_id}
                  </h3>
                </div>

                {/* Section 1: Sanctions match details */}
                <div className="space-y-2">
                  <div className="flex items-center gap-1.5 text-xs font-bold text-white uppercase tracking-wider">
                    <ShieldCheck className="h-4 w-4 text-brass" />
                    <span>1. Watchlist & Sanctions Record</span>
                  </div>
                  <div className={`p-4 rounded-xl border text-xs leading-relaxed ${
                    selectedVendor.sanctions_match 
                      ? "bg-risk-critical/15 border-risk-critical/30 text-white" 
                      : "liquid-glass text-white"
                  }`}>
                    {selectedVendor.sanctions_match ? (
                      <div className="space-y-1">
                        <span className="font-bold text-risk-critical block">CRITICAL: SANCTIONS MATCH FOUND</span>
                        <p className="text-text-muted">{selectedVendor.sanctions_match_detail}</p>
                      </div>
                    ) : (
                      <span className="text-text-muted">Passed international anti-money laundering and OFAC sanctions database checks. No matches identified.</span>
                    )}
                  </div>
                </div>

                {/* Section 2: Adverse Media Check */}
                <div className="space-y-2">
                  <div className="flex items-center gap-1.5 text-xs font-bold text-white uppercase tracking-wider">
                    <Newspaper className="h-4 w-4 text-brass" />
                    <span>2. Adverse Media Analysis</span>
                  </div>
                  
                  <div className={`p-4 rounded-xl border text-xs leading-relaxed space-y-3 ${
                    selectedVendor.adverse_media_flagged
                      ? "bg-risk-critical/15 border-risk-critical/30 text-white"
                      : "liquid-glass text-white"
                  }`}>
                    <div className="flex justify-between items-center">
                      <span className="text-text-muted">Media Sentiment Status:</span>
                      <span className={`font-bold ${selectedVendor.adverse_media_flagged ? "text-risk-critical" : "text-risk-clear"}`}>
                        {selectedVendor.adverse_media_flagged ? "FLAGGED" : "PASSED"}
                      </span>
                    </div>

                    {selectedVendor.adverse_media_evidence?.evidence && selectedVendor.adverse_media_evidence.evidence.length > 0 ? (
                      <div className="space-y-2 pt-2 border-t border-white/10">
                        <span className="text-xs font-bold text-brass block">Evidence Transcripts:</span>
                        {selectedVendor.adverse_media_evidence.evidence.map((snippet, idx) => (
                          <div key={idx} className="p-3 rounded-lg bg-black/40 border border-white/10 text-xs italic text-text-muted">
                            &ldquo;{snippet}&rdquo;
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-text-muted text-xs">No adverse press clippings, litigations, or negative media events retrieved.</p>
                    )}

                    {selectedVendor.adverse_media_evidence?.sources && selectedVendor.adverse_media_evidence.sources.length > 0 && (
                      <div className="space-y-1.5 pt-2 border-t border-white/10">
                        <span className="text-xs font-bold text-brass block">Retrieved Sources:</span>
                        <div className="flex flex-wrap gap-2">
                          {selectedVendor.adverse_media_evidence.sources.map((src, idx) => (
                            <span key={idx} className="text-[11px] px-2 py-0.5 rounded liquid-pill text-text-muted truncate max-w-xs">
                              {src}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Section 3: Business Registry Details */}
                <div className="space-y-2">
                  <div className="flex items-center gap-1.5 text-xs font-bold text-white uppercase tracking-wider">
                    <Building2 className="h-4 w-4 text-brass" />
                    <span>3. Corporate Verification Register</span>
                  </div>
                  <div className="p-4 rounded-xl liquid-glass text-xs space-y-2">
                    <div className="flex justify-between">
                      <span className="text-text-muted">Registry Status:</span>
                      <span className={`font-bold ${selectedVendor.registry_verified ? "text-risk-clear" : "text-brass"}`}>
                        {selectedVendor.registry_verified ? "VERIFIED" : "UNVERIFIED / INVALID"}
                      </span>
                    </div>
                    <p className="text-text-muted border-t border-white/10 pt-2 leading-relaxed">
                      {selectedVendor.registry_detail || "Verified corporate certificate of registration, active tax status, and address integrity confirmed."}
                    </p>
                  </div>
                </div>

              </div>
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-center text-text-muted space-y-2">
                <ShieldAlert className="h-10 w-10 text-brass opacity-40" />
                <span className="text-xs font-bold text-white">No Vendor Selected</span>
                <p className="text-xs max-w-xs">Select a vendor from the sidebar index to audit the compliance dossier.</p>
              </div>
            )}
          </div>

          {/* Right Column (3/12): Screening metadata + Refresh action button + Summary stats */}
          <div className="w-3/12 bg-surface-base overflow-y-auto p-6 flex flex-col justify-between">
            
            <div className="space-y-6">
              <div>
                <span className="text-xs font-bold text-brass uppercase tracking-wider block">Dossier Metadata</span>
                <h3 className="text-sm font-bold text-white mt-1">Compliance Stats</h3>
              </div>

              {selectedVendor && (
                <div className="liquid-glass p-4 space-y-2.5 text-xs">
                  <div className="flex justify-between">
                    <span className="text-text-muted">Vendor UUID:</span>
                    <span className="font-bold text-white">{selectedVendor.vendor_id}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-muted">Last Checked:</span>
                    <span className="text-white">{new Date(selectedVendor.checked_at).toLocaleDateString()}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-muted">Sanctions Match:</span>
                    <span className={selectedVendor.sanctions_match ? "text-risk-critical font-bold" : "text-risk-clear font-bold"}>
                      {selectedVendor.sanctions_match ? "YES" : "NO"}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-muted">Registry:</span>
                    <span className="text-white">{selectedVendor.registry_verified ? "Active Verified" : "Not Verified"}</span>
                  </div>
                </div>
              )}

              {/* Aggregated Overview */}
              <div className="liquid-glass p-4 space-y-3">
                <span className="text-xs font-bold text-brass uppercase tracking-wider block">Total Register Stats</span>
                
                <div className="grid grid-cols-2 gap-2 text-center">
                  <div className="liquid-glass p-3">
                    <span className="text-xl font-bold text-white block">{summary.total_screened}</span>
                    <span className="text-[10px] text-text-muted uppercase font-semibold">Total</span>
                  </div>
                  <div className="liquid-glass p-3">
                    <span className="text-xl font-bold text-risk-critical block">{summary.flagged_sanctions}</span>
                    <span className="text-[10px] text-text-muted uppercase font-semibold">Sanctions</span>
                  </div>
                  <div className="liquid-glass p-3">
                    <span className="text-xl font-bold text-brass block">{summary.flagged_adverse_media}</span>
                    <span className="text-[10px] text-text-muted uppercase font-semibold">Media</span>
                  </div>
                  <div className="liquid-glass p-3">
                    <span className="text-xl font-bold text-risk-critical block">{summary.flagged_registry_invalid}</span>
                    <span className="text-[10px] text-text-muted uppercase font-semibold">Invalid</span>
                  </div>
                </div>
              </div>
            </div>

            {selectedVendor && (
              <div className="pt-6 border-t border-white/10">
                <button
                  onClick={() => handleRefresh(selectedVendor.vendor_id)}
                  disabled={refreshLoading[selectedVendor.vendor_id]}
                  className="w-full py-3 bg-brass text-black font-bold text-xs rounded-xl shadow-[0_0_15px_rgba(212,175,55,0.3)] hover:shadow-[0_0_25px_rgba(212,175,55,0.5)] transition flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
                >
                  <RefreshCw className={`h-4 w-4 ${refreshLoading[selectedVendor.vendor_id] ? "animate-spin" : ""}`} />
                  <span>{refreshLoading[selectedVendor.vendor_id] ? "Refreshing..." : "Re-Screen Vendor"}</span>
                </button>
              </div>
            )}

          </div>

        </div>
      </AppShell>
    </AuthGuard>
  );
}

