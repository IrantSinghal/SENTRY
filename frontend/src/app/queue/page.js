"use client";

import React, { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import AuthGuard from "../components/AuthGuard";
import AppShell from "../components/AppShell";
import DecisionLedger from "../components/DecisionLedger";
import { 
  Search, 
  RefreshCw, 
  ClipboardList, 
  ShieldAlert, 
  ArrowLeft,
  FileText,
  Check,
  X,
  Sparkles,
  ShieldCheck,
  Building2,
  AlertCircle
} from "lucide-react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const ROLE_RANK = {
  "analyst": 1,
  "approver": 2,
  "vp": 3,
  "cfo": 4,
  "admin": 5
};

function QueueContent() {
  const searchParams = useSearchParams();
  const filterParam = searchParams.get("filter");

  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [queue, setQueue] = useState([]);
  const [selectedReqId, setSelectedReqId] = useState(null);
  const [selectedReqDetail, setSelectedReqDetail] = useState(null);
  const [overrideReason, setOverrideReason] = useState("");
  const [overrideError, setOverrideError] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [groupFilter, setGroupFilter] = useState("");
  const [sortBy, setSortBy] = useState("date_desc");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const savedUser = localStorage.getItem("pr_triage_user");
    const savedToken = localStorage.getItem("pr_triage_token");
    if (savedUser && savedToken) {
      setUser(JSON.parse(savedUser));
      setToken(savedToken);
    }
  }, []);

  const getHeaders = () => {
    return {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`
    };
  };

  const fetchQueue = async () => {
    if (!token) return;
    setIsLoading(true);
    try {
      let url = `${API_BASE_URL}/requisitions/queue?sort_by=${sortBy}`;
      if (groupFilter) url += `&purchasing_group=${groupFilter}`;
      if (searchQuery) url += `&search=${searchQuery}`;
      const res = await fetch(url, { headers: getHeaders() });
      if (res.ok) {
        const data = await res.json();
        if (filterParam === "authority") {
          setQueue(data.filter(item => item.requires_named_authority));
        } else {
          setQueue(data);
        }
      }
    } catch (err) {
      console.error("Failed to load queue:", err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (token) {
      fetchQueue();
    }
  }, [token, sortBy, groupFilter, searchQuery, filterParam]);

  const fetchDetail = async (id) => {
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE_URL}/requisitions/${id}`, { headers: getHeaders() });
      if (res.ok) {
        setSelectedReqDetail(await res.json());
        setOverrideError("");
      }
    } catch (err) {
      console.error("Failed to fetch detail:", err);
    }
  };

  useEffect(() => {
    if (token && selectedReqId) {
      fetchDetail(selectedReqId);
    }
  }, [token, selectedReqId]);

  const handleDirectOverrideSubmit = async (decision) => {
    if (!selectedReqId || !token) return;
    if (!overrideReason.trim()) {
      setOverrideError("Override justification note is required.");
      return;
    }
    setOverrideError("");

    try {
      const res = await fetch(`${API_BASE_URL}/requisitions/${selectedReqId}/override`, {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify({
          override_decision: decision,
          reason: overrideReason
        })
      });

      if (res.ok) {
        setOverrideReason("");
        setSelectedReqId(null);
        setSelectedReqDetail(null);
        fetchQueue();
      } else {
        const errorData = await res.json();
        setOverrideError(errorData.detail || "Failed to submit override. Check role permissions.");
      }
    } catch (err) {
      console.error(err);
      setOverrideError("Failed to submit override. Network error.");
    }
  };

  const checkOverrideAuthorization = () => {
    if (!selectedReqDetail || !user) return { authorized: false, message: "" };

    const userRole = user.role.toLowerCase();
    const requiredRole = (selectedReqDetail.required_approver_role || "approver").toLowerCase();
    
    const userRank = ROLE_RANK[userRole] || 0;
    const requiredRank = ROLE_RANK[requiredRole] || 0;

    if (userRole === "admin") {
      return { authorized: true, message: "Authorized (Administrator Bypass)" };
    }

    if (selectedReqDetail.requires_named_authority) {
      const isAuthorized = userRank >= requiredRank;
      return {
        authorized: isAuthorized,
        message: isAuthorized 
          ? `Authorized (${userRole.toUpperCase()} meets required ${requiredRole.toUpperCase()})`
          : `Unauthorized (Requires ${requiredRole.toUpperCase()} or higher)`
      };
    } else {
      const isAuthorized = userRank >= ROLE_RANK["approver"];
      return {
        authorized: isAuthorized,
        message: isAuthorized
          ? `Authorized`
          : `Unauthorized (Requires Approver role or higher)`
      };
    }
  };

  const renderList = () => (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-transparent font-72">
      
      {/* Search & Filter Header Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-6 shrink-0 border-b border-white/10 bg-surface-panel backdrop-blur-xl">
        <div>
          <h2 className="text-base font-bold text-white tracking-wide">
            Requisition Triage Cockpit
          </h2>
          <p className="text-xs text-text-muted mt-0.5">
            Select a purchase requisition to review line items and inspect reasoning traces.
          </p>
        </div>
        
        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-text-muted" />
            <input 
              type="text" 
              placeholder="Search PR ID or Requester..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 pr-3 py-2 liquid-input text-xs w-52"
            />
          </div>
          <select
            value={groupFilter}
            onChange={(e) => setGroupFilter(e.target.value)}
            className="px-3 py-2 liquid-input text-xs"
          >
            <option value="">All Groups</option>
            <option value="P01">P01 — Operations</option>
            <option value="P02">P02 — IT & Infrastructure</option>
            <option value="P03">P03 — Facilities</option>
          </select>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="px-3 py-2 liquid-input text-xs"
          >
            <option value="date_desc">Risk Rank / Newest</option>
            <option value="date_asc">Oldest First</option>
            <option value="value_desc">Value: High → Low</option>
            <option value="value_asc">Value: Low → High</option>
          </select>
        </div>
      </div>

      {/* Main Grid: Queue Rail (Left) + Detail Panel (Center) */}
      <div className="flex-1 flex overflow-hidden w-full">
        
        {/* Left Queue Rail */}
        <div className="w-80 lg:w-96 border-r border-white/10 bg-surface-panel/40 backdrop-blur-xl flex flex-col overflow-y-auto shrink-0 p-4 space-y-3">
          <div className="flex items-center justify-between text-xs text-text-muted px-1 font-semibold">
            <span>QUEUE ({queue.length})</span>
            <span>BY RISK SCORE</span>
          </div>

          {isLoading ? (
            <div className="flex-1 flex items-center justify-center p-8">
              <RefreshCw className="h-5 w-5 animate-spin text-brass" />
            </div>
          ) : queue.length === 0 ? (
            <div className="flex-1 p-6 flex flex-col items-center justify-center text-text-muted space-y-2 text-center">
              <ClipboardList className="h-8 w-8 text-text-muted opacity-40" />
              <p className="text-sm font-bold text-white">Queue is clear</p>
              <p className="text-xs">Nothing needs your review right now.</p>
            </div>
          ) : (
            <div className="space-y-2.5">
              {queue.map((req) => {
                const isSelected = selectedReqId === req.requisition_id;
                const isApproved = req.verdict === "auto_approve" || req.human_override?.override_decision === "approved";
                const isRejected = req.verdict === "reject" || req.human_override?.override_decision === "rejected";
                
                return (
                  <button
                    key={req.requisition_id}
                    onClick={() => setSelectedReqId(req.requisition_id)}
                    className={`w-full p-4 text-left cursor-pointer transition-all rounded-2xl flex flex-col gap-2.5 border ${
                      isSelected 
                        ? "bg-brass/15 border-brass/40 shadow-[0_0_20px_rgba(212,175,55,0.15)]" 
                        : "liquid-glass-interactive border-white/10"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {!isApproved && !isRejected ? (
                          <span className="h-2 w-2 rounded-full bg-brass shadow-[0_0_6px_rgba(212,175,55,0.8)] animate-pulse" />
                        ) : isApproved ? (
                          <span className="h-2 w-2 rounded-full bg-risk-clear shadow-[0_0_6px_rgba(100,181,135,0.8)]" />
                        ) : (
                          <span className="h-2 w-2 rounded-full bg-risk-critical shadow-[0_0_6px_rgba(224,108,103,0.8)]" />
                        )}
                        <span className="text-xs font-bold text-white">{req.requisition_id}</span>
                      </div>
                      <span className="text-[11px] text-text-muted">{req.requisition_date}</span>
                    </div>

                    <div className="flex items-center justify-between text-xs">
                      <span className="text-text-muted">
                        Unit <strong className="text-white">{req.purchasing_group}</strong> ({req.created_by_user})
                      </span>
                      <span className="font-bold text-white text-xs">
                        ${req.total_value.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                      </span>
                    </div>

                    <div className="flex items-center justify-between pt-1">
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border uppercase ${
                        isApproved ? "bg-risk-clear/15 border-risk-clear/30 text-risk-clear" :
                        isRejected ? "bg-risk-critical/15 border-risk-critical/30 text-risk-critical" :
                        "bg-brass/15 border-brass/30 text-brass"
                      }`}>
                        {isApproved ? "Auto Cleared" : isRejected ? "Escalated" : "Pending Triage"}
                      </span>

                      <span className="text-xs text-brass font-semibold flex items-center gap-1">
                        Inspect &rarr;
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Center Detail & Trace Panel */}
        <div className="flex-1 flex flex-col overflow-y-auto">
          {selectedReqId ? renderDetail() : (
            <div className="flex-1 flex flex-col items-center justify-center p-12 text-center text-text-muted space-y-3">
              <FileText className="h-10 w-10 text-text-muted opacity-40" />
              <h3 className="text-sm font-bold text-white tracking-wide">
                No Requisition Selected
              </h3>
              <p className="text-xs max-w-sm">
                Select a purchase requisition from the queue rail on the left to inspect line item risks, agent reasoning trace, and vendor dossier.
              </p>
            </div>
          )}
        </div>

      </div>

    </div>
  );

  const renderDetail = () => {
    if (!selectedReqDetail) {
      return (
        <div className="flex-1 flex items-center justify-center p-12">
          <RefreshCw className="h-6 w-6 animate-spin text-brass" />
        </div>
      );
    }

    const authCheck = checkOverrideAuthorization();

    return (
      <div className="flex-1 flex flex-col h-full overflow-hidden font-72">
        
        {/* Top Detail Action Bar */}
        <div className="bg-surface-panel/60 backdrop-blur-xl border-b border-white/10 p-5 flex flex-col md:flex-row items-center justify-between gap-4 shrink-0">
          <div className="flex flex-wrap items-center gap-5 text-xs text-text-muted">
            <button 
              onClick={() => { setSelectedReqId(null); setSelectedReqDetail(null); }}
              className="px-3 py-1.5 liquid-pill hover:bg-white/10 text-white font-bold transition flex items-center gap-1.5 cursor-pointer text-xs"
            >
              <ArrowLeft className="h-4 w-4 text-brass" /> Close
            </button>

            <div>
              PR ID: <span className="font-bold text-white">{selectedReqDetail.requisition_id}</span>
            </div>
            <div>
              Requester: <span className="font-bold text-white">{selectedReqDetail.created_by_user || "N/A"}</span> ({selectedReqDetail.purchasing_group})
            </div>
            <div>
              Total: <span className="font-bold text-white">${selectedReqDetail.total_value?.toLocaleString("en-US", { minimumFractionDigits: 2 }) || "0.00"}</span>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-3 shrink-0">
            {selectedReqDetail.human_override ? (
              <div className="liquid-pill px-4 py-1.5 text-xs flex items-center gap-2">
                <span className="font-bold text-brass uppercase">Logged: {selectedReqDetail.human_override.override_decision}</span>
              </div>
            ) : (
              <div className="flex items-center gap-3">
                <input 
                  type="text" 
                  placeholder="Officer justification notes..." 
                  value={overrideReason}
                  onChange={(e) => setOverrideReason(e.target.value)}
                  disabled={!authCheck.authorized}
                  className="px-3 py-2 text-xs liquid-input w-56 disabled:opacity-40"
                />
                <button 
                  onClick={() => handleDirectOverrideSubmit("approved")}
                  disabled={!authCheck.authorized}
                  className="px-4 py-2 bg-risk-clear hover:opacity-90 text-black font-bold text-xs rounded-xl shadow-[0_0_15px_rgba(100,181,135,0.3)] transition disabled:opacity-30 cursor-pointer"
                >
                  Clear for approval
                </button>
                <button 
                  onClick={() => handleDirectOverrideSubmit("rejected")}
                  disabled={!authCheck.authorized}
                  className="px-4 py-2 bg-risk-critical hover:opacity-90 text-white font-bold text-xs rounded-xl shadow-[0_0_15px_rgba(224,108,103,0.3)] transition disabled:opacity-30 cursor-pointer"
                >
                  Escalate to finance
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Inspection Grid & Slide Drawer */}
        <div className="flex-1 flex overflow-hidden w-full">
          
          <div className="flex-1 p-8 overflow-y-auto space-y-6">
            
            {/* Master Key-Value Card */}
            <div className="liquid-glass p-6 space-y-4">
              <h3 className="text-xs font-bold text-brass tracking-wider uppercase">
                Requisition Master Fields
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-6 text-xs">
                <div>
                  <span className="text-text-muted block mb-1">Document Type</span>
                  <span className="font-bold text-white">NB (Standard PR)</span>
                </div>
                <div>
                  <span className="text-text-muted block mb-1">Cost Center</span>
                  <span className="font-bold text-white">CC-{selectedReqDetail.purchasing_group || "100"}</span>
                </div>
                <div>
                  <span className="text-text-muted block mb-1">Created Date</span>
                  <span className="font-bold text-white">{selectedReqDetail.requisition_date}</span>
                </div>
                <div>
                  <span className="text-text-muted block mb-1">Risk Score</span>
                  <span className="font-bold text-brass">{Math.round((1 - (selectedReqDetail.confidence_score || 0)) * 100)} / 100</span>
                </div>
              </div>
            </div>

            {/* Line Items Breakdown */}
            <div className="liquid-glass p-6 space-y-4">
              <h3 className="text-xs font-bold text-brass tracking-wider uppercase">
                Line Item Breakdown
              </h3>
              <div className="divide-y divide-white/10">
                {selectedReqDetail.item_results && selectedReqDetail.item_results.map((item, idx) => {
                  const isClean = !item.signals?.price_anomaly?.flagged && !item.signals?.vendor_risk?.flagged && !item.signals?.duplicate_detection?.flagged;

                  return (
                    <div key={idx} className="py-4 flex justify-between items-center text-xs">
                      <div className="space-y-1">
                        <span className="text-text-muted text-[11px]">Item #{String(item.item_id || item.purchase_requisition_item || 10).padStart(5, '0')}</span>
                        <p className="font-bold text-white text-sm">{item.material}</p>
                        <p className="text-text-muted">Vendor: {item.vendor_id}</p>
                      </div>
                      <div className="text-right space-y-1">
                        <span className="font-bold text-white text-sm block">
                          ${(item.total_value || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
                        </span>
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border uppercase inline-block ${
                          isClean ? "bg-risk-clear/15 border-risk-clear/30 text-risk-clear" : "bg-risk-critical/15 border-risk-critical/30 text-risk-critical"
                        }`}>
                          {isClean ? "Cleared" : "Flagged"}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Agent Reasoning Trace Component */}
            <div className="liquid-glass p-6">
              <DecisionLedger requisition={selectedReqDetail} />
            </div>

          </div>

          {/* Right Sliding Vendor Dossier Panel */}
          <div className="w-80 border-l border-white/10 bg-surface-panel/40 backdrop-blur-xl p-6 overflow-y-auto space-y-6 shrink-0">
            <div className="flex items-center justify-between border-b border-white/10 pb-3">
              <span className="text-xs font-bold text-white uppercase tracking-wider">
                Vendor Dossier
              </span>
              <span className="text-[10px] text-brass font-bold uppercase liquid-pill px-2 py-0.5">
                Live Screening
              </span>
            </div>

            {selectedReqDetail.signals?.vendor_risk?.details && selectedReqDetail.signals.vendor_risk.details.length > 0 ? (
              selectedReqDetail.signals.vendor_risk.details.map((v) => (
                <div key={v.vendor_id} className="space-y-5 text-xs">
                  <div className="liquid-glass p-4 space-y-1">
                    <span className="text-[11px] text-text-muted block">Vendor Name</span>
                    <strong className="text-white text-sm block">{v.vendor_name}</strong>
                    <span className="text-[11px] text-text-muted block">ID: {v.vendor_id}</span>
                  </div>

                  <div className="space-y-3">
                    <span className="text-xs font-bold text-white uppercase block">Sanctions & Registry</span>
                    <div className="flex justify-between">
                      <span className="text-text-muted">Sanctions Match:</span>
                      <span className={v.sanctions_match ? "text-risk-critical font-bold" : "text-risk-clear font-bold"}>
                        {v.sanctions_match ? "Flagged" : "Cleared"}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-text-muted">Business Registry:</span>
                      <span className={v.registry_verified ? "text-risk-clear font-bold" : "text-brass font-bold"}>
                        {v.registry_verified ? "Verified" : "Unverified"}
                      </span>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="liquid-glass p-5 text-text-muted text-xs space-y-2">
                <ShieldAlert className="h-5 w-5 text-brass" />
                <p className="font-bold text-white">First-Time Vendor</p>
                <p className="text-xs leading-relaxed">
                  No prior transactions — first-time vendor, verify manually.
                </p>
              </div>
            )}
          </div>

        </div>

      </div>
    );
  };

  return (
    <AppShell pageTitle={selectedReqId ? `Auditing Dossier: ${selectedReqId}` : "Triage Queue"}>
      {selectedReqId ? renderDetail() : renderList()}
    </AppShell>
  );
}

export default function QueuePage() {
  return (
    <AuthGuard>
      <Suspense fallback={
        <div className="min-h-screen ambient-liquid-bg flex items-center justify-center text-text-muted">
          <div className="flex flex-col items-center gap-4">
            <RefreshCw className="h-8 w-8 animate-spin text-brass" />
            <p className="text-sm font-semibold">Loading queue...</p>
          </div>
        </div>
      }>
        <QueueContent />
      </Suspense>
    </AuthGuard>
  );
}

