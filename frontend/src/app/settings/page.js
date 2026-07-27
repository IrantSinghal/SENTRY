"use client";

import React, { useState, useEffect } from "react";
import AuthGuard from "../components/AuthGuard";
import AppShell from "../components/AppShell";
import { 
  Sliders, 
  ShieldAlert, 
  ShieldCheck, 
  DollarSign, 
  Percent,
  RefreshCw,
  Sparkles,
  Save,
  CheckCircle2
} from "lucide-react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function SettingsPage() {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [activeTab, setActiveTab] = useState("triage");
  const [settings, setSettings] = useState({
    auto_approval_ceiling: 5000,
    confidence_threshold: 0.85,
    price_deviation_threshold: 0.15,
    new_vendor_threshold_days: 90,
    duplicate_window_days: 30,
    contract_expiry_warning_days: 30,
    vendor_screening_staleness_days: 30,
    sanctions_match_threshold: 90
  });
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState(false);
  const [successMsg, setSuccessMsg] = useState("");
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    const savedUser = localStorage.getItem("pr_triage_user");
    const savedToken = localStorage.getItem("pr_triage_token");
    if (savedUser && savedToken) {
      setUser(JSON.parse(savedUser));
      setToken(savedToken);
    }
  }, []);

  useEffect(() => {
    if (!token) return;
    const fetchSettings = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/settings`, {
          headers: { "Authorization": `Bearer ${token}` }
        });
        if (res.ok) {
          const data = await res.json();
          setSettings({
            auto_approval_ceiling: data.auto_approval_ceiling ?? 5000,
            confidence_threshold: data.confidence_threshold ?? 0.85,
            price_deviation_threshold: data.price_deviation_threshold ?? 0.15,
            new_vendor_threshold_days: data.new_vendor_threshold_days ?? 90,
            duplicate_window_days: data.duplicate_window_days ?? 30,
            contract_expiry_warning_days: data.contract_expiry_warning_days ?? 30,
            vendor_screening_staleness_days: data.vendor_screening_staleness_days ?? 30,
            sanctions_match_threshold: data.sanctions_match_threshold ?? 90
          });
        }
      } catch (err) {
        console.error("Failed to load settings:", err);
      } finally {
        setLoading(false);
      }
    };
    fetchSettings();
  }, [token]);

  const isAdmin = user?.role === "admin";

  const handleChange = (key, value) => {
    setSettings(prev => ({
      ...prev,
      [key]: value
    }));
  };

  const handleSave = async (e) => {
    e.preventDefault();
    if (!isAdmin || !token) return;

    setUpdating(true);
    setSuccessMsg("");
    setErrorMsg("");

    try {
      const res = await fetch(`${API_BASE_URL}/settings`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({
          auto_approval_ceiling: Number(settings.auto_approval_ceiling),
          confidence_threshold: Number(settings.confidence_threshold),
          price_deviation_threshold: Number(settings.price_deviation_threshold),
          new_vendor_threshold_days: Number(settings.new_vendor_threshold_days),
          duplicate_window_days: Number(settings.duplicate_window_days),
          contract_expiry_warning_days: Number(settings.contract_expiry_warning_days),
          vendor_screening_staleness_days: Number(settings.vendor_screening_staleness_days),
          sanctions_match_threshold: Number(settings.sanctions_match_threshold)
        })
      });

      if (res.ok) {
        setSuccessMsg("System configuration updated successfully.");
      } else {
        const data = await res.json();
        setErrorMsg(data.detail || "Failed to update configurations.");
      }
    } catch (err) {
      console.error(err);
      setErrorMsg("Failed to update configurations due to a network error.");
    } finally {
      setUpdating(false);
    }
  };

  return (
    <AuthGuard>
      <AppShell pageTitle="Settings & Rules">
        <div className="h-full p-8 overflow-y-auto font-72 flex justify-center">
          <div className="w-full max-w-4xl space-y-6">
            
            {/* Header Card */}
            <div className="liquid-glass p-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 text-xs font-semibold text-brass mb-1">
                  <Sliders className="h-4 w-4" />
                  <span>Agent Configuration Hub</span>
                </div>
                <h2 className="text-xl font-bold text-white tracking-tight">
                  System Settings & Rules
                </h2>
                <p className="text-xs text-text-muted mt-1">
                  Adjust release ceilings, AI confidence criteria, and vendor risk thresholds.
                </p>
              </div>

              <div>
                {isAdmin ? (
                  <span className="px-3 py-1 rounded-full text-xs font-semibold bg-risk-clear/15 border border-risk-clear/30 text-risk-clear flex items-center gap-1.5">
                    <ShieldCheck className="h-3.5 w-3.5" />
                    Admin Clearance
                  </span>
                ) : (
                  <span className="px-3 py-1 rounded-full text-xs font-semibold bg-brass/15 border border-brass/30 text-brass flex items-center gap-1.5">
                    <ShieldAlert className="h-3.5 w-3.5" />
                    Read-Only Mode
                  </span>
                )}
              </div>
            </div>

            {/* Category Navigation Pills */}
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => setActiveTab("triage")}
                className={`px-4 py-2 text-xs font-bold rounded-xl transition cursor-pointer ${
                  activeTab === "triage"
                    ? "bg-brass text-black shadow-[0_0_15px_rgba(212,175,55,0.3)]"
                    : "liquid-pill text-text-muted hover:text-white"
                }`}
              >
                Triage & Pricing Rules
              </button>

              <button
                type="button"
                onClick={() => setActiveTab("compliance")}
                className={`px-4 py-2 text-xs font-bold rounded-xl transition cursor-pointer ${
                  activeTab === "compliance"
                    ? "bg-brass text-black shadow-[0_0_15px_rgba(212,175,55,0.3)]"
                    : "liquid-pill text-text-muted hover:text-white"
                }`}
              >
                Vendor Compliance Thresholds
              </button>
            </div>

            {loading ? (
              <div className="flex items-center justify-center p-16">
                <RefreshCw className="h-6 w-6 animate-spin text-brass" />
              </div>
            ) : (
              <form onSubmit={handleSave} className="space-y-6">
                
                {/* Triage & Pricing Rules Tab */}
                {activeTab === "triage" && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                    <div className="liquid-glass p-6 space-y-2">
                      <label className="text-xs font-bold text-white block">Auto-Approval Ceiling ($)</label>
                      <input
                        disabled={!isAdmin}
                        type="number"
                        value={settings.auto_approval_ceiling}
                        onChange={(e) => handleChange("auto_approval_ceiling", e.target.value)}
                        className="w-full px-4 py-2.5 liquid-input text-xs font-bold"
                      />
                      <p className="text-[11px] text-text-muted leading-relaxed pt-1">
                        PRs above this limit are routed to named executive reviewers regardless of confidence score.
                      </p>
                    </div>

                    <div className="liquid-glass p-6 space-y-2">
                      <label className="text-xs font-bold text-white block">AI Confidence Score Threshold (0.0 – 1.0)</label>
                      <input
                        disabled={!isAdmin}
                        type="number"
                        step="0.01"
                        min="0"
                        max="1"
                        value={settings.confidence_threshold}
                        onChange={(e) => handleChange("confidence_threshold", e.target.value)}
                        className="w-full px-4 py-2.5 liquid-input text-xs font-bold"
                      />
                      <p className="text-[11px] text-text-muted leading-relaxed pt-1">
                        Minimum score required to autonomously approve purchase requisitions.
                      </p>
                    </div>

                    <div className="liquid-glass p-6 space-y-2">
                      <label className="text-xs font-bold text-white block">Price Deviation Tolerance (e.g. 0.15 = 15%)</label>
                      <input
                        disabled={!isAdmin}
                        type="number"
                        step="0.01"
                        min="0"
                        max="1"
                        value={settings.price_deviation_threshold}
                        onChange={(e) => handleChange("price_deviation_threshold", e.target.value)}
                        className="w-full px-4 py-2.5 liquid-input text-xs font-bold"
                      />
                      <p className="text-[11px] text-text-muted leading-relaxed pt-1">
                        Price variation versus historical baselines that flags an item as an anomaly.
                      </p>
                    </div>

                    <div className="liquid-glass p-6 space-y-2">
                      <label className="text-xs font-bold text-white block">Duplicate Check Window (Days)</label>
                      <input
                        disabled={!isAdmin}
                        type="number"
                        value={settings.duplicate_window_days}
                        onChange={(e) => handleChange("duplicate_window_days", e.target.value)}
                        className="w-full px-4 py-2.5 liquid-input text-xs font-bold"
                      />
                      <p className="text-[11px] text-text-muted leading-relaxed pt-1">
                        Historical window used to cross-reference identical material purchases.
                      </p>
                    </div>
                  </div>
                )}

                {/* Vendor Compliance Tab */}
                {activeTab === "compliance" && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                    <div className="liquid-glass p-6 space-y-2">
                      <label className="text-xs font-bold text-white block">New Vendor Flag Threshold (Days)</label>
                      <input
                        disabled={!isAdmin}
                        type="number"
                        value={settings.new_vendor_threshold_days}
                        onChange={(e) => handleChange("new_vendor_threshold_days", e.target.value)}
                        className="w-full px-4 py-2.5 liquid-input text-xs font-bold"
                      />
                      <p className="text-[11px] text-text-muted leading-relaxed pt-1">
                        Vendors onboarded within this timeframe receive heightened compliance audits.
                      </p>
                    </div>

                    <div className="liquid-glass p-6 space-y-2">
                      <label className="text-xs font-bold text-white block">Contract Expiry Warning Window (Days)</label>
                      <input
                        disabled={!isAdmin}
                        type="number"
                        value={settings.contract_expiry_warning_days}
                        onChange={(e) => handleChange("contract_expiry_warning_days", e.target.value)}
                        className="w-full px-4 py-2.5 liquid-input text-xs font-bold"
                      />
                      <p className="text-[11px] text-text-muted leading-relaxed pt-1">
                        Warning window prior to vendor contract expiration date.
                      </p>
                    </div>

                    <div className="liquid-glass p-6 space-y-2">
                      <label className="text-xs font-bold text-white block">Sanctions Fuzzy Match Threshold (%)</label>
                      <input
                        disabled={!isAdmin}
                        type="number"
                        min="0"
                        max="100"
                        value={settings.sanctions_match_threshold}
                        onChange={(e) => handleChange("sanctions_match_threshold", e.target.value)}
                        className="w-full px-4 py-2.5 liquid-input text-xs font-bold"
                      />
                      <p className="text-[11px] text-text-muted leading-relaxed pt-1">
                        Name similarity percentage to trigger mandatory sanctions review.
                      </p>
                    </div>

                    <div className="liquid-glass p-6 space-y-2">
                      <label className="text-xs font-bold text-white block">Screening Cache Staleness (Days)</label>
                      <input
                        disabled={!isAdmin}
                        type="number"
                        value={settings.vendor_screening_staleness_days}
                        onChange={(e) => handleChange("vendor_screening_staleness_days", e.target.value)}
                        className="w-full px-4 py-2.5 liquid-input text-xs font-bold"
                      />
                      <p className="text-[11px] text-text-muted leading-relaxed pt-1">
                        Validity period of vendor screening records before fresh lookup is forced.
                      </p>
                    </div>
                  </div>
                )}

                {successMsg && (
                  <div className="p-4 bg-risk-clear/15 border border-risk-clear/30 rounded-xl text-risk-clear text-xs font-semibold flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4" />
                    <span>{successMsg}</span>
                  </div>
                )}

                {errorMsg && (
                  <div className="p-4 bg-risk-critical/15 border border-risk-critical/30 rounded-xl text-risk-critical text-xs font-semibold">
                    {errorMsg}
                  </div>
                )}

                {isAdmin && (
                  <button
                    type="submit"
                    disabled={updating}
                    className="w-full py-3.5 bg-brass text-black font-bold text-xs rounded-xl shadow-[0_0_20px_rgba(212,175,55,0.3)] hover:shadow-[0_0_30px_rgba(212,175,55,0.5)] transition flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
                  >
                    <Save className="h-4 w-4" />
                    <span>{updating ? "Saving Changes..." : "Save System Configurations"}</span>
                  </button>
                )}
              </form>
            )}

          </div>
        </div>
      </AppShell>
    </AuthGuard>
  );
}

