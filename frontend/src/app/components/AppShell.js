"use client";

import React, { useState, useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import {
  Home,
  LayoutDashboard,
  ClipboardList,
  PlusCircle,
  ShieldAlert,
  BarChart3,
  History,
  Sliders,
  LogOut,
  User,
  Sparkles
} from "lucide-react";

export default function AppShell({ children, pageTitle = "" }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState(null);
  const [sessionId, setSessionId] = useState("");

  useEffect(() => {
    const savedUser = localStorage.getItem("pr_triage_user");
    if (savedUser) {
      setUser(JSON.parse(savedUser));
    }
    const rand = Math.floor(1000 + Math.random() * 9000);
    setSessionId(`SESS-${rand}`);
  }, []);

  const handleLogout = () => {
    localStorage.removeItem("pr_triage_token");
    localStorage.removeItem("pr_triage_user");
    router.replace("/login");
  };

  const isRequester = user && (user.role.toLowerCase() === "requester" || user.role.toLowerCase() === "unit_requester");

  const requesterNav = [
    { name: "Dashboard", path: "/home", icon: LayoutDashboard },
    { name: "New Requisition", path: "/create-requisition", icon: PlusCircle },
    { name: "My Requests", path: "/queue?filter=my_unit", icon: History },
  ];

  const procurementNav = [
    { name: "Dashboard", path: "/home", icon: LayoutDashboard },
    { name: "Triage Cockpit", path: "/queue", icon: ClipboardList },
    { name: "Create Requisition", path: "/create-requisition", icon: PlusCircle },
    { name: "Vendor Screening", path: "/vendor-screening", icon: ShieldAlert },
    { name: "Analytics", path: "/analytics", icon: BarChart3 },
    { name: "Audit Log", path: "/audit-log", icon: History },
    { name: "Settings", path: "/settings", icon: Sliders },
  ];

  const navItems = isRequester ? requesterNav : procurementNav;

  const getInitials = (name) => {
    if (!name) return "U";
    return name.split(" ").map(n => n[0]).join("").toUpperCase().slice(0, 2);
  };

  return (
    <div className="h-screen ambient-liquid-bg text-text-primary flex font-72 overflow-hidden selection:bg-brass/20 selection:text-brass">

      {/* Translucent Liquid Glass Sidebar */}
      <aside className="w-64 border-r border-white/10 bg-surface-panel backdrop-blur-2xl flex flex-col shrink-0 z-20">

        {/* Sidebar Header */}
        <div 
          onClick={() => router.push("/home")}
          className="p-6 border-b border-white/10 flex flex-col gap-1.5 cursor-pointer hover:opacity-90 transition-opacity"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-brass" />
              <span className="font-bold text-sm tracking-wide text-white">
                SAP PR Agent
              </span>
            </div>
            <span className="h-2 w-2 rounded-full bg-risk-clear shadow-[0_0_8px_rgba(100,181,135,0.8)] animate-pulse" title="Agent Status: Active" />
          </div>
          <span className="text-[11px] text-text-muted block">
            {isRequester ? "Unit Requester Portal" : "Procurement Cockpit"}
          </span>
        </div>


        {/* Navigation Items */}
        <nav className="flex-1 p-4 space-y-1.5 overflow-y-auto">
          {navItems.map((item) => {
            const isActive = pathname === item.path || (item.path.includes("?") && `${pathname}${window.location.search}` === item.path);
            const Icon = item.icon;

            return (
              <button
                key={item.path}
                onClick={() => router.push(item.path)}
                className={`w-full flex items-center gap-3 px-3.5 py-2.5 text-xs font-semibold rounded-xl transition-all text-left cursor-pointer ${
                  isActive
                    ? "bg-brass/15 text-brass border border-brass/30 shadow-[0_0_15px_rgba(212,175,55,0.15)] font-bold"
                    : "text-text-muted hover:bg-white/5 hover:text-white"
                }`}
              >
                <Icon className={`h-4 w-4 ${isActive ? "text-brass" : "text-text-muted"}`} />
                <span>{item.name}</span>
              </button>
            );
          })}
        </nav>

        {/* User Profile Badge Pinned at Bottom */}
        <div className="p-4 border-t border-white/10 bg-black/20 backdrop-blur-md flex items-center justify-between">
          <div className="flex items-center gap-3 min-w-0">
            <div className="h-8 w-8 rounded-full bg-brass/20 border border-brass/40 text-brass flex items-center justify-center font-bold text-xs shrink-0 shadow-[0_0_10px_rgba(212,175,55,0.2)]">
              {user ? getInitials(user.display_name) : <User className="h-4 w-4" />}
            </div>
            <div className="flex flex-col min-w-0">
              <span className="text-xs font-semibold text-white truncate leading-tight">
                {user ? user.display_name : "Loading..."}
              </span>
              <span className="text-[10px] text-text-muted capitalize truncate mt-0.5">
                {user ? user.role : "User"}
              </span>
            </div>
          </div>

          <button
            onClick={handleLogout}
            className="p-2 rounded-lg hover:bg-risk-critical/15 text-text-muted hover:text-risk-critical transition-colors cursor-pointer"
            title="Sign Out"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>

      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 bg-transparent relative">

        {/* Floating Top Header Bar */}
        <header className="h-16 border-b border-white/10 bg-surface-panel backdrop-blur-xl flex items-center justify-between px-8 shrink-0 z-10">
          <div className="flex items-center gap-4">
            <h1 className="text-base font-bold text-white tracking-wide">
              {pageTitle}
            </h1>
          </div>

          <div className="flex items-center gap-3">
            {/* Role Badge */}
            {user && (
              <div className="liquid-pill px-3 py-1 flex items-center gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-brass shadow-[0_0_6px_rgba(212,175,55,0.8)]" />
                <span className="text-xs font-medium text-brass capitalize">
                  {user.role}
                </span>
              </div>
            )}

            {/* Session Pill */}
            <span className="text-xs text-text-muted liquid-pill px-3 py-1 font-mono hidden sm:inline">
              {sessionId}
            </span>
          </div>
        </header>

        {/* Content Body */}
        <div className="flex-1 overflow-hidden relative">
          {children}
        </div>

      </div>

    </div>
  );
}

