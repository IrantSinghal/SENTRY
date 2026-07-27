"use client";

import React, { useState, useEffect, useCallback } from "react";
import AuthGuard from "../components/AuthGuard";
import AppShell from "../components/AppShell";
import DecisionLedger from "../components/DecisionLedger";
import { 
  Download, 
  Search, 
  ChevronLeft, 
  ChevronRight, 
  X,
  FileText,
  RefreshCw,
  ArrowRight,
  ShieldCheck,
  Zap,
  Calendar
} from "lucide-react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function AuditLogPage() {
  const [auditLog, setAuditLog] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedReqId, setSelectedReqId] = useState(null);
  const [selectedReqDetail, setSelectedReqDetail] = useState(null);
  const [token, setToken] = useState(null);

  // Search, Verdict & Date Filters State
  const [searchQuery, setSearchQuery] = useState("");
  const [verdictFilter, setVerdictFilter] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [totalItems, setTotalItems] = useState(0);
  const itemsPerPage = 10;

  useEffect(() => {
    const savedToken = localStorage.getItem("pr_triage_token");
    if (savedToken) setToken(savedToken);
  }, []);

  const fetchAuditLog = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const queryParams = new URLSearchParams({
        page: currentPage,
        limit: itemsPerPage,
      });
      if (verdictFilter) queryParams.append("verdict", verdictFilter);
      if (searchQuery) queryParams.append("search", searchQuery);
      if (startDate) queryParams.append("start_date", startDate);
      if (endDate) queryParams.append("end_date", endDate);

      const res = await fetch(`${API_BASE_URL}/audit-log?${queryParams.toString()}`, {
        headers: { "Authorization": `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setAuditLog(data.items || []);
        setTotalItems(data.total || 0);
      }
    } catch (err) {
      console.error("Failed to load audit log:", err);
    } finally {
      setLoading(false);
    }
  }, [token, currentPage, verdictFilter, searchQuery, startDate, endDate]);

  const fetchDetail = useCallback(async (id) => {
    if (!token || !id) return;
    try {
      const res = await fetch(`${API_BASE_URL}/requisitions/${id}`, {
        headers: { "Authorization": `Bearer ${token}` }
      });
      if (res.ok) {
        setSelectedReqDetail(await res.json());
      }
    } catch (err) {
      console.error("Failed to fetch detail:", err);
    }
  }, [token]);

  useEffect(() => {
    if (token) fetchAuditLog();
  }, [token, fetchAuditLog]);

  useEffect(() => {
    if (selectedReqId) {
      fetchDetail(selectedReqId);
    } else {
      setSelectedReqDetail(null);
    }
  }, [selectedReqId, fetchDetail]);

  const handleExportCSV = async () => {
    if (!token) return;
    try {
      const queryParams = new URLSearchParams();
      if (verdictFilter) queryParams.append("verdict", verdictFilter);
      if (searchQuery) queryParams.append("search", searchQuery);
      if (startDate) queryParams.append("start_date", startDate);
      if (endDate) queryParams.append("end_date", endDate);

      const res = await fetch(`${API_BASE_URL}/audit-log/export?${queryParams.toString()}`, {
        headers: { "Authorization": `Bearer ${token}` }
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.setAttribute("href", url);
        link.setAttribute("download", `pr_triage_audit_log_${new Date().toISOString().split('T')[0]}.csv`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      }
    } catch (err) {
      console.error("Failed to export CSV:", err);
    }
  };

  const handleClearFilters = () => {
    setSearchQuery("");
    setVerdictFilter("");
    setStartDate("");
    setEndDate("");
    setCurrentPage(1);
  };

  const totalPages = Math.ceil(totalItems / itemsPerPage) || 1;

  return (
    <AuthGuard>
      <AppShell pageTitle="Audit Log & History">
        <div className="h-full p-8 overflow-y-auto font-72 relative">
          
          <div className="max-w-7xl mx-auto space-y-6">
            
            {/* Header & Filter Bar */}
            <div className="liquid-glass p-6 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 text-xs font-semibold text-brass mb-1">
                  <ShieldCheck className="h-4 w-4" />
                  <span>Auditable Compliance Ledger</span>
                </div>
                <h2 className="text-xl font-bold text-white tracking-tight">
                  Transaction Audit Log
                </h2>
                <p className="text-xs text-text-muted mt-1">
                  Complete historical record of all purchase requisitions, AI risk verdicts, and human officer overrides.
                </p>
              </div>

              <div className="flex items-center gap-3 w-full md:w-auto shrink-0">
                <button
                  onClick={handleExportCSV}
                  disabled={auditLog.length === 0}
                  className="px-4 py-2 bg-brass text-black font-bold text-xs rounded-xl shadow-[0_0_15px_rgba(212,175,55,0.3)] hover:shadow-[0_0_25px_rgba(212,175,55,0.5)] transition flex items-center gap-2 cursor-pointer disabled:opacity-50"
                >
                  <Download className="h-4 w-4" />
                  <span>Export CSV Archive</span>
                </button>
              </div>
            </div>

            {/* Filter Controls Bar (Search, Verdict Dropdown & Date Range) */}
            <div className="liquid-glass p-4 flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-4">
              <div className="flex flex-wrap items-center gap-3">
                {/* Search Bar */}
                <div className="relative min-w-[220px]">
                  <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-text-muted" />
                  <input
                    type="text"
                    placeholder="Search PR ID, Creator..."
                    value={searchQuery}
                    onChange={(e) => { setSearchQuery(e.target.value); setCurrentPage(1); }}
                    className="pl-9 pr-8 py-2 liquid-input text-xs w-full"
                  />
                  {searchQuery && (
                    <button 
                      onClick={() => { setSearchQuery(""); setCurrentPage(1); }}
                      className="absolute right-3 top-2.5 text-text-muted hover:text-white"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>

                {/* Verdict Dropdown with explicit dark options styling */}
                <select
                  value={verdictFilter}
                  onChange={(e) => { setVerdictFilter(e.target.value); setCurrentPage(1); }}
                  className="px-3 py-2 liquid-input text-xs bg-[#14171C] text-[#F0F3F8] shrink-0"
                >
                  <option value="" className="bg-[#14171C] text-[#F0F3F8]">All Verdicts</option>
                  <option value="auto_approve" className="bg-[#14171C] text-[#F0F3F8]">Cleared / Approved</option>
                  <option value="escalate" className="bg-[#14171C] text-[#F0F3F8]">Escalated for Review</option>
                  <option value="reject" className="bg-[#14171C] text-[#F0F3F8]">Rejected</option>
                </select>

                {/* Date Range Picker */}
                <div className="flex items-center gap-2">
                  <div className="flex items-center gap-1.5 liquid-input px-3 py-1.5">
                    <Calendar className="h-3.5 w-3.5 text-brass" />
                    <span className="text-[11px] text-text-muted">From:</span>
                    <input
                      type="date"
                      value={startDate}
                      onChange={(e) => { setStartDate(e.target.value); setCurrentPage(1); }}
                      className="bg-transparent text-xs text-white outline-none cursor-pointer"
                    />
                  </div>

                  <div className="flex items-center gap-1.5 liquid-input px-3 py-1.5">
                    <Calendar className="h-3.5 w-3.5 text-brass" />
                    <span className="text-[11px] text-text-muted">To:</span>
                    <input
                      type="date"
                      value={endDate}
                      onChange={(e) => { setEndDate(e.target.value); setCurrentPage(1); }}
                      className="bg-transparent text-xs text-white outline-none cursor-pointer"
                    />
                  </div>
                </div>

                {(searchQuery || verdictFilter || startDate || endDate) && (
                  <button
                    onClick={handleClearFilters}
                    className="text-xs text-brass hover:underline px-2 font-semibold cursor-pointer"
                  >
                    Clear Filters
                  </button>
                )}
              </div>

              <div className="text-xs text-text-muted shrink-0">
                Showing <strong className="text-white">{auditLog.length}</strong> of <strong className="text-white">{totalItems}</strong> entries
              </div>
            </div>


            {/* Main Table View */}
            <div className="liquid-glass overflow-hidden">
              {loading ? (
                <div className="flex items-center justify-center p-12">
                  <RefreshCw className="h-6 w-6 animate-spin text-brass" />
                </div>
              ) : auditLog.length === 0 ? (
                <div className="p-12 text-center text-text-muted space-y-2">
                  <FileText className="h-8 w-8 mx-auto opacity-40" />
                  <p className="text-sm font-bold text-white">No audit records found</p>
                  <p className="text-xs">Adjust your search or filter parameters.</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="border-b border-white/10 text-text-muted font-bold uppercase text-[11px] tracking-wider">
                        <th className="p-4">Requisition ID</th>
                        <th className="p-4">Requester</th>
                        <th className="p-4">Group</th>
                        <th className="p-4">Submitted Date</th>
                        <th className="p-4">Total Amount</th>
                        <th className="p-4">Verdict Status</th>
                        <th className="p-4 text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/10">
                      {auditLog.map((req) => {
                        const isApproved = req.verdict === "auto_approve" || req.human_override === "approved";
                        const isRejected = req.verdict === "reject" || req.human_override === "rejected";

                        return (
                          <tr 
                            key={req.requisition_id}
                            onClick={() => setSelectedReqId(req.requisition_id)}
                            className="hover:bg-white/5 transition cursor-pointer group"
                          >
                            <td className="p-4 font-bold text-white">
                              {req.requisition_id}
                            </td>
                            <td className="p-4 text-text-muted">
                              {req.created_by_user || "System"}
                            </td>
                            <td className="p-4 text-text-muted font-mono">
                              {req.purchasing_group || "P01"}
                            </td>
                            <td className="p-4 text-text-muted">
                              {req.created_at ? new Date(req.created_at).toLocaleDateString() : "—"}
                            </td>
                            <td className="p-4 font-bold text-white">
                              ${(req.total_value || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
                            </td>
                            <td className="p-4">
                              <span className={`text-[10px] font-bold px-2.5 py-1 rounded-full border uppercase ${
                                isApproved ? "bg-risk-clear/15 border-risk-clear/30 text-risk-clear" :
                                isRejected ? "bg-risk-critical/15 border-risk-critical/30 text-risk-critical" :
                                "bg-brass/15 border-brass/30 text-brass"
                              }`}>
                                {isApproved ? "Cleared" : isRejected ? "Rejected" : "Escalated"}
                              </span>
                            </td>
                            <td className="p-4 text-right">
                              <span className="text-xs font-semibold text-brass group-hover:translate-x-1 transition-transform inline-flex items-center gap-1">
                                Inspect &rarr;
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Pagination footer */}
              <div className="p-4 border-t border-white/10 flex items-center justify-between text-xs text-text-muted">
                <span>Page <strong className="text-white">{currentPage}</strong> of <strong className="text-white">{totalPages}</strong></span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
                    disabled={currentPage === 1}
                    className="p-1.5 liquid-pill hover:bg-white/10 disabled:opacity-30 cursor-pointer text-white"
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))}
                    disabled={currentPage === totalPages}
                    className="p-1.5 liquid-pill hover:bg-white/10 disabled:opacity-30 cursor-pointer text-white"
                  >
                    <ChevronRight className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>

          </div>

          {/* Slide-Over Audit Dossier Drawer / Modal Backdrop */}
          {selectedReqId && (
            <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm transition-all">
              <div 
                className="w-full max-w-2xl bg-surface-base border-l border-white/10 shadow-2xl h-full flex flex-col overflow-hidden font-72 animate-in slide-in-from-right duration-300"
              >
                {/* Drawer Header */}
                <div className="p-6 border-b border-white/10 bg-surface-panel/80 backdrop-blur-xl flex items-center justify-between shrink-0">
                  <div className="flex items-center gap-3">
                    <div className="p-2 rounded-xl bg-brass/10 text-brass border border-brass/20">
                      <ShieldCheck className="h-5 w-5" />
                    </div>
                    <div>
                      <h3 className="text-base font-bold text-white">
                        Audit Dossier #{selectedReqId}
                      </h3>
                      <span className="text-xs text-text-muted">
                        LangGraph Execution & Compliance Record
                      </span>
                    </div>
                  </div>

                  <button
                    onClick={() => setSelectedReqId(null)}
                    className="p-2 rounded-xl hover:bg-white/10 text-text-muted hover:text-white transition cursor-pointer"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>

                {/* Drawer Content */}
                <div className="flex-1 overflow-y-auto p-6 space-y-6">
                  {selectedReqDetail ? (
                    <>
                      {/* Master metadata card */}
                      <div className="liquid-glass p-6 space-y-4">
                        <h4 className="text-xs font-bold text-brass uppercase tracking-wider">
                          Master Ledger Metadata
                        </h4>
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-xs">
                          <div>
                            <span className="text-text-muted block mb-1">Requester</span>
                            <span className="font-bold text-white">{selectedReqDetail.created_by_user || "System"}</span>
                          </div>
                          <div>
                            <span className="text-text-muted block mb-1">Submission Date</span>
                            <span className="font-bold text-white">{selectedReqDetail.requisition_date || "—"}</span>
                          </div>
                          <div>
                            <span className="text-text-muted block mb-1">Total Amount</span>
                            <span className="font-bold text-white">${(selectedReqDetail.total_value || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}</span>
                          </div>
                          <div>
                            <span className="text-text-muted block mb-1">Verdict Class</span>
                            <span className="font-bold text-brass uppercase">{selectedReqDetail.verdict}</span>
                          </div>
                          <div>
                            <span className="text-text-muted block mb-1">Confidence</span>
                            <span className="font-bold text-white">{Math.round((selectedReqDetail.confidence_score || 0) * 100)}%</span>
                          </div>
                        </div>

                        {/* Human override note */}
                        {selectedReqDetail.human_override ? (
                          <div className="mt-4 p-4 rounded-xl bg-brass/10 border border-brass/30 space-y-1 text-xs">
                            <span className="font-bold text-brass uppercase block">Human Override Verified</span>
                            <p className="text-white">Decision: <strong className="uppercase">{selectedReqDetail.human_override.override_decision}</strong></p>
                            <p className="text-text-muted italic">&ldquo;{selectedReqDetail.human_override.reason}&rdquo;</p>
                          </div>
                        ) : (
                          <div className="mt-4 p-3 rounded-xl bg-risk-clear/10 border border-risk-clear/30 text-risk-clear text-xs font-semibold">
                            Autonomously Cleared by AI Agent
                          </div>
                        )}
                      </div>

                      {/* Staggered Reasoning Trace */}
                      <div className="liquid-glass p-6">
                        <DecisionLedger requisition={selectedReqDetail} />
                      </div>
                    </>
                  ) : (
                    <div className="flex items-center justify-center p-12">
                      <RefreshCw className="h-6 w-6 animate-spin text-brass" />
                    </div>
                  )}
                </div>

                {/* Drawer Footer */}
                <div className="p-4 border-t border-white/10 bg-surface-panel/80 backdrop-blur-xl flex justify-end shrink-0">
                  <button
                    onClick={() => setSelectedReqId(null)}
                    className="px-5 py-2 liquid-pill hover:bg-white/10 text-white font-bold text-xs cursor-pointer"
                  >
                    Close Dossier
                  </button>
                </div>

              </div>
            </div>
          )}

        </div>
      </AppShell>
    </AuthGuard>
  );
}
