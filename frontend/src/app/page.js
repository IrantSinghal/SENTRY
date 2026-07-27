"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function RootPage() {
  const router = useRouter();

  useEffect(() => {
    const token = localStorage.getItem("pr_triage_token");
    if (token) {
      router.replace("/home");
    } else {
      router.replace("/login");
    }
  }, [router]);

  return (
    <div className="min-h-screen bg-[var(--bg-base)] flex items-center justify-center font-sans">
      <div className="flex flex-col items-center space-y-3">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-[var(--border-glass)] border-t-[var(--accent)]" />
        <p className="text-xs text-[var(--text-secondary)] font-mono">Redirecting...</p>
      </div>
    </div>
  );
}
