"use client";
 
import React from "react";
import { Lock } from "lucide-react";
 
export default function Tile({ 
  icon: Icon, 
  title, 
  subtitle, 
  onClick, 
  variant = "default", 
  disabled = false, 
  disabledReason = "",
  size = "normal",
  hasWarning = false
}) {
  const isLarge = size === "large";
  const isAuthorityWarning = variant === "authority" && hasWarning;
 
  if (disabled) {
    return (
      <div 
        className={`flex flex-col justify-between p-5 rounded-xl bg-[var(--surface-muted)] border border-[var(--border-glass)] opacity-30 cursor-not-allowed select-none transition-all ${
          isLarge ? "h-52" : "h-36"
        }`}
      >
        <div className="flex justify-between items-start">
          <div className="text-[var(--text-muted)]">
            {Icon && <Icon className="h-5 w-5" />}
          </div>
          <div className="flex items-center gap-1 bg-[var(--surface-card)] border border-[var(--border-glass)] text-[9px] text-[var(--text-muted)] font-mono uppercase px-2 py-0.5 rounded">
            <Lock className="h-2.5 w-2.5" />
            <span>{disabledReason || "Locked"}</span>
          </div>
        </div>
 
        <div>
          <h3 className="text-xs font-semibold text-[var(--text-muted)]">{title}</h3>
          {subtitle !== undefined && (
            <p className="text-xl font-medium font-mono text-[var(--text-muted)] mt-0.5">{subtitle}</p>
          )}
        </div>
      </div>
    );
  }
 
  // Active States
  let borderClass = isAuthorityWarning 
    ? "border-[var(--risk-authority)]/35" 
    : "border-[var(--border-glass)]";
  let bgClass = isAuthorityWarning
    ? "bg-[var(--bg-authority)]"
    : "bg-[var(--surface-card)]";
  let subtitleColor = "text-[var(--text-primary)]";
  let iconColor = isAuthorityWarning
    ? "text-[var(--risk-authority)]"
    : "text-[var(--text-secondary)]";
 
  return (
    <div 
      onClick={onClick}
      className={`group flex flex-col justify-between p-5 rounded-xl cursor-pointer ${bgClass} hover:bg-[var(--surface-muted)] border ${borderClass} hover:border-[var(--accent)] transition-all duration-200 focus-ring ${
        isLarge ? "h-52" : "h-36"
      }`}
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
    >
      <div className="flex justify-between items-start">
        <div className={`${iconColor} group-hover:text-[var(--text-primary)] transition-colors duration-200`}>
          {Icon && <Icon className={isLarge ? "h-6 w-6" : "h-5 w-5"} />}
        </div>
        {isAuthorityWarning && (
          <span className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-[var(--bg-authority)] border border-[var(--risk-authority)]/20 text-[9px] text-[var(--risk-authority)] font-mono uppercase tracking-wider">
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--risk-authority)] animate-pulse" />
            <span>Action Required</span>
          </span>
        )}
      </div>
 
      <div>
        <h3 className={`font-semibold text-[var(--text-secondary)] group-hover:text-[var(--text-primary)] transition-colors duration-200 ${isLarge ? "text-sm" : "text-xs"}`}>{title}</h3>
        {subtitle !== undefined && (
          <div className={`mt-1 transition-colors duration-200 ${subtitleColor}`}>
            {subtitle}
          </div>
        )}
      </div>
    </div>
  );
}
