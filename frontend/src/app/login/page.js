"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { ShieldAlert, AlertTriangle, RefreshCw, Lock, ShieldCheck, Sparkles, UserCheck } from "lucide-react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function LoginPage() {
  const router = useRouter();
  const [loginEmail, setLoginEmail] = useState("");
  const [loginError, setLoginError] = useState("");
  const [loginLoading, setLoginLoading] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("pr_triage_token");
    if (token) {
      router.replace("/home");
    }
  }, [router]);

  const handleLogin = async (e, presetEmail = null) => {
    if (e) e.preventDefault();
    const emailToUse = presetEmail || loginEmail;
    if (!emailToUse) return;

    setLoginError("");
    setLoginLoading(true);

    try {
      const res = await fetch(`${API_BASE_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: emailToUse })
      });

      if (res.ok) {
        const data = await res.json();
        localStorage.setItem("pr_triage_token", data.access_token);
        localStorage.setItem("pr_triage_user", JSON.stringify(data.user));
        router.push("/home");
      } else {
        const errData = await res.json();
        setLoginError(errData.detail || "Authentication failed. Please verify email address.");
      }
    } catch (err) {
      console.error("Login failed:", err);
      setLoginError("Login failed. Unable to reach backend server.");
    } finally {
      setLoginLoading(false);
    }
  };

  const demoUsers = [
    { name: "Analyst User", email: "analyst@test.com", badge: "Read-Only" },
    { name: "Standard Approver", email: "approver@test.com", badge: "L1 Approver" },
    { name: "VP Procurement", email: "vp@test.com", badge: "L2 VP Role" },
    { name: "CFO Executive", email: "cfo@test.com", badge: "L3 CFO Role" },
  ];

  return (
    <div className="min-h-screen ambient-liquid-bg text-white flex items-center justify-center font-72 p-6 relative overflow-hidden selection:bg-brass/20 selection:text-brass">
      {/* Background ambient lighting */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-brass/10 rounded-full blur-3xl pointer-events-none" />

      <div className="w-full max-w-lg liquid-glass p-8 sm:p-10 relative z-10 space-y-8 rounded-2xl border-white/10 shadow-[0_0_50px_rgba(0,0,0,0.5)]">
        
        {/* Header */}
        <div className="flex flex-col items-center space-y-3 text-center">
          <div className="p-3 rounded-2xl bg-brass/10 border border-brass/20 text-brass shadow-[0_0_20px_rgba(212,175,55,0.2)]">
            <Sparkles className="h-8 w-8" />
          </div>
          <div>
            <h2 className="text-2xl font-bold tracking-tight text-white">SAP PR Agent</h2>
            <p className="text-xs text-text-muted mt-1">Autonomous Triage & Compliance Console</p>
          </div>
        </div>

        {/* Login Form */}
        <form onSubmit={(e) => handleLogin(e)} className="space-y-5">
          <div className="space-y-2">
            <label className="text-xs font-semibold text-text-muted uppercase tracking-wider block">Email Address</label>
            <input
              required
              type="email"
              placeholder="email@test.com"
              value={loginEmail}
              onChange={(e) => setLoginEmail(e.target.value)}
              className="w-full px-4 py-3 liquid-input text-xs"
            />
          </div>

          {loginError && (
            <div className="p-3.5 bg-risk-critical/15 border border-risk-critical/30 rounded-xl text-risk-critical text-xs flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span>{loginError}</span>
            </div>
          )}

          <button
            type="submit"
            disabled={loginLoading}
            className="w-full py-3 bg-brass text-black font-bold text-xs rounded-xl shadow-[0_0_20px_rgba(212,175,55,0.3)] hover:shadow-[0_0_30px_rgba(212,175,55,0.5)] transition-all flex items-center justify-center gap-2 disabled:opacity-50 cursor-pointer"
          >
            {loginLoading ? (
              <>
                <RefreshCw className="h-4 w-4 animate-spin text-black" />
                <span>Authenticating...</span>
              </>
            ) : (
              <>
                <Lock className="h-4 w-4" />
                <span>Sign In to Dashboard</span>
              </>
            )}
          </button>
        </form>

        {/* Quick-Access Demo Presets */}
        <div className="pt-6 border-t border-white/10 space-y-4">
          <span className="text-[11px] font-bold text-brass uppercase tracking-wider block text-center">
            Demo Quick-Access Profiles
          </span>
          
          <div className="grid grid-cols-2 gap-3">
            {demoUsers.map((u) => (
              <button
                key={u.email}
                onClick={(e) => handleLogin(e, u.email)}
                className="p-3 text-left rounded-xl liquid-glass border border-white/10 hover:border-brass/40 hover:bg-brass/10 transition-all text-xs flex flex-col justify-between h-16 group cursor-pointer"
              >
                <span className="font-semibold text-white group-hover:text-brass transition-colors truncate">{u.name}</span>
                <span className="text-[10px] px-2 py-0.5 rounded-full liquid-pill text-text-muted self-start font-mono">{u.badge}</span>
              </button>
            ))}
          </div>

          <button
            onClick={(e) => handleLogin(e, "admin@test.com")}
            className="w-full p-3 text-center rounded-xl liquid-glass border border-brass/30 hover:border-brass hover:bg-brass/10 transition-all text-xs font-bold text-brass flex items-center justify-center gap-2 cursor-pointer"
          >
            <ShieldCheck className="h-4 w-4" />
            <span>Administrator Bypass Profile</span>
          </button>
        </div>

      </div>
    </div>
  );
}

