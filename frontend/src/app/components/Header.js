"use client";

import React, { useState, useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { ClipboardList, LogOut, ArrowLeft } from "lucide-react";

export default function Header() {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState(null);

  useEffect(() => {
    const savedUser = localStorage.getItem("pr_triage_user");
    if (savedUser) {
      setUser(JSON.parse(savedUser));
    }
  }, []);

  const handleLogout = () => {
    localStorage.removeItem("pr_triage_token");
    localStorage.removeItem("pr_triage_user");
    router.replace("/login");
  };

  const getInitials = (name) => {
    if (!name) return "?";
    return name
      .split(" ")
      .map((n) => n[0])
      .join("")
      .toUpperCase()
      .slice(0, 2);
  };

  const isLaunchpad = pathname === "/home" || pathname === "/";

  return (
    <header className="border-b border-[var(--border-glass)] bg-[var(--surface-card)] px-6 py-4 flex items-center justify-between sticky top-0 z-50">
      <div className="flex items-center gap-6">
        <div 
          onClick={() => router.push("/home")} 
          className="flex items-center gap-3 cursor-pointer group focus-ring rounded"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              router.push("/home");
            }
          }}
        >
          <div className="h-9 w-9 rounded-lg border border-[var(--border-glass)] flex items-center justify-center text-[var(--text-secondary)] group-hover:text-[var(--text-primary)] group-hover:border-[var(--accent)] transition">
            <ClipboardList className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-sm font-semibold text-[var(--text-primary)] leading-none">PR Triage Agent</h1>
            <p className="text-[10px] text-[var(--text-muted)] font-mono tracking-wider uppercase mt-1">SAP BTP Orchestrator</p>
          </div>
        </div>

        {!isLaunchpad && (
          <button 
            onClick={() => router.push("/home")}
            className="flex items-center gap-2 text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition bg-transparent hover:bg-[var(--surface-muted)] border border-[var(--border-glass)] px-3 py-1.5 rounded-md focus-ring"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>Back to Launchpad</span>
          </button>
        )}
      </div>

      {user && (
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-3 text-right">
            <div>
              <p className="text-xs font-semibold text-[var(--text-primary)] leading-none">{user.display_name}</p>
              <span className="inline-block text-[9px] font-mono font-medium uppercase tracking-wider text-[var(--text-secondary)] mt-1">
                {user.role}
              </span>
            </div>
            <div className="h-8 w-8 rounded-full border border-[var(--border-glass)] bg-[var(--surface-muted)] flex items-center justify-center text-xs font-bold text-[var(--text-primary)] font-mono">
              {getInitials(user.display_name)}
            </div>
          </div>

          <button 
            onClick={handleLogout}
            title="Log Out"
            className="p-1.5 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition hover:bg-[var(--surface-muted)] rounded focus-ring"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      )}
    </header>
  );
}
