"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import AuthGuard from "../components/AuthGuard";
import AppShell from "../components/AppShell";
import { 
  FilePlus, 
  Trash2, 
  Plus, 
  Play, 
  CheckCircle, 
  AlertTriangle, 
  XCircle,
  FileText,
  ShieldCheck,
  RefreshCw,
  Sparkles,
  Zap
} from "lucide-react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function CreateRequisitionPage() {
  const router = useRouter();
  const [token, setToken] = useState(null);
  const [user, setUser] = useState(null);

  const [reqId, setReqId] = useState("");
  const [purchasingGroup, setPurchasingGroup] = useState("P01");
  const [createdByUser, setCreatedByUser] = useState("REQ_USER");
  const [requisitionDate, setRequisitionDate] = useState("");
  const [items, setItems] = useState([
    { material: "M001", vendor_id: "VEND001", order_quantity: 10, net_price_amount: 150.00 }
  ]);

  const [submitting, setSubmitting] = useState(false);
  const [triageOutcome, setTriageOutcome] = useState(null);
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    const savedToken = localStorage.getItem("pr_triage_token");
    const savedUser = localStorage.getItem("pr_triage_user");
    if (savedToken) setToken(savedToken);
    if (savedUser) {
      const u = JSON.parse(savedUser);
      setUser(u);
      setCreatedByUser(u.email ? u.email.split("@")[0].toUpperCase() : "REQ_USER");
    }
    
    const rand = Math.floor(100000 + Math.random() * 900000);
    setReqId(`REQ_${rand}`);
    setRequisitionDate(new Date().toISOString().split("T")[0]);
  }, []);

  const handleRegenId = () => {
    const rand = Math.floor(100000 + Math.random() * 900000);
    setReqId(`REQ_${rand}`);
  };

  const handleAddItem = () => {
    const nextIdx = items.length + 1;
    const newVendor = `VEND00${(items.length % 4) + 1}`;
    setItems([
      ...items,
      { material: `M00${nextIdx}`, vendor_id: newVendor, order_quantity: 1, net_price_amount: 100.00 }
    ]);
  };

  const handleRemoveItem = (index) => {
    if (items.length === 1) return;
    setItems(items.filter((_, idx) => idx !== index));
  };

  const handleItemChange = (index, field, value) => {
    setItems(prev => prev.map((item, idx) => {
      if (idx === index) {
        const updatedVal = field === "order_quantity" || field === "net_price_amount" ? Number(value) : value;
        return { ...item, [field]: updatedVal };
      }
      return item;
    }));
  };

  const totalValue = items.reduce((acc, item) => acc + (item.order_quantity * item.net_price_amount), 0);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!token) return;

    setSubmitting(true);
    setTriageOutcome(null);
    setErrorMsg("");

    try {
      const res = await fetch(`${API_BASE_URL}/requisitions/ingest`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({
          purchase_requisition_id: reqId,
          purchasing_group: purchasingGroup,
          created_by_user: createdByUser,
          requisition_date: requisitionDate,
          items: items
        })
      });

      if (res.ok) {
        const data = await res.json();
        setTriageOutcome(data);
      } else {
        const data = await res.json();
        setErrorMsg(data.detail || "Failed to submit requisition.");
      }
    } catch (err) {
      console.error(err);
      setErrorMsg("Network error connecting to backend service.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AppShell pageTitle="Create Requisition">
      <div className="h-full p-8 overflow-y-auto font-72 flex justify-center">
        <div className="w-full max-w-3xl space-y-8">
          
          <form onSubmit={handleSubmit} className="liquid-glass p-8 space-y-8">
            <div>
              <div className="flex items-center gap-2 text-xs font-semibold text-brass mb-1">
                <Sparkles className="h-4 w-4" />
                <span>Requisition Submission Wizard</span>
              </div>
              <h2 className="text-xl font-bold text-white tracking-tight">
                New Purchase Requisition
              </h2>
              <p className="text-xs text-text-muted mt-1 leading-relaxed">
                Draft a purchase requisition for your department. The AI triage engine evaluates line items for price anomalies and policy compliance upon submission.
              </p>
            </div>

            {/* Header fields */}
            <div className="space-y-4 pt-2">
              <h3 className="text-xs font-bold text-brass uppercase tracking-wider">
                1. Requisition Header
              </h3>
              
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-text-muted">Draft ID</label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      required
                      value={reqId}
                      onChange={(e) => setReqId(e.target.value)}
                      className="flex-1 px-3 py-2 liquid-input text-xs"
                    />
                    <button
                      type="button"
                      onClick={handleRegenId}
                      className="px-3 py-2 liquid-pill text-xs font-bold hover:bg-white/10 transition cursor-pointer text-white"
                    >
                      Gen
                    </button>
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-text-muted">Cost Center</label>
                  <select
                    value={purchasingGroup}
                    onChange={(e) => setPurchasingGroup(e.target.value)}
                    className="w-full px-3 py-2 liquid-input text-xs"
                  >
                    <option value="P01">P01 — Operations</option>
                    <option value="P02">P02 — IT & Infrastructure</option>
                    <option value="P03">P03 — Facilities</option>
                  </select>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-text-muted">Requester</label>
                  <input
                    type="text"
                    required
                    value={createdByUser}
                    onChange={(e) => setCreatedByUser(e.target.value)}
                    className="w-full px-3 py-2 liquid-input text-xs"
                  />
                </div>
              </div>
            </div>

            {/* Line items */}
            <div className="space-y-4 pt-2">
              <div className="flex justify-between items-center">
                <h3 className="text-xs font-bold text-brass uppercase tracking-wider">
                  2. Line Items
                </h3>
                <button
                  type="button"
                  onClick={handleAddItem}
                  className="text-xs font-bold text-brass hover:underline flex items-center gap-1 cursor-pointer"
                >
                  <Plus className="h-4 w-4" />
                  <span>Add Line Item</span>
                </button>
              </div>

              <div className="space-y-3">
                {items.map((item, idx) => (
                  <div key={idx} className="liquid-glass p-5 space-y-3 border-white/10">
                    <div className="flex justify-between items-center">
                      <span className="text-xs font-bold text-white">Item #{idx + 1}</span>
                      {items.length > 1 && (
                        <button
                          type="button"
                          onClick={() => handleRemoveItem(idx)}
                          className="text-risk-critical hover:underline text-xs font-semibold cursor-pointer"
                        >
                          Remove
                        </button>
                      )}
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                      <div>
                        <label className="text-[11px] font-medium text-text-muted block mb-1">Material ID</label>
                        <input
                          type="text"
                          required
                          value={item.material}
                          onChange={(e) => handleItemChange(idx, "material", e.target.value)}
                          className="w-full px-3 py-1.5 liquid-input text-xs"
                        />
                      </div>

                      <div>
                        <label className="text-[11px] font-medium text-text-muted block mb-1">Vendor ID</label>
                        <input
                          type="text"
                          required
                          value={item.vendor_id}
                          onChange={(e) => handleItemChange(idx, "vendor_id", e.target.value)}
                          className="w-full px-3 py-1.5 liquid-input text-xs"
                        />
                      </div>

                      <div>
                        <label className="text-[11px] font-medium text-text-muted block mb-1">Quantity</label>
                        <input
                          type="number"
                          required
                          min="1"
                          value={item.order_quantity}
                          onChange={(e) => handleItemChange(idx, "order_quantity", e.target.value)}
                          className="w-full px-3 py-1.5 liquid-input text-xs"
                        />
                      </div>

                      <div>
                        <label className="text-[11px] font-medium text-text-muted block mb-1">Unit Price ($)</label>
                        <input
                          type="number"
                          required
                          step="0.01"
                          min="0.01"
                          value={item.net_price_amount}
                          onChange={(e) => handleItemChange(idx, "net_price_amount", e.target.value)}
                          className="w-full px-3 py-1.5 liquid-input text-xs"
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Total value */}
            <div className="p-6 liquid-glass text-center space-y-1">
              <span className="text-xs text-text-muted uppercase tracking-wider block">Total Estimated Requisition Value</span>
              <span className="text-3xl font-bold text-white">
                ${totalValue.toLocaleString("en-US", { minimumFractionDigits: 2 })}
              </span>
            </div>

            {errorMsg && (
              <div className="p-4 bg-risk-critical/15 border border-risk-critical/30 rounded-xl text-risk-critical text-xs">
                {errorMsg}
              </div>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="w-full py-3.5 bg-brass text-black font-bold text-xs rounded-xl shadow-[0_0_20px_rgba(212,175,55,0.3)] hover:shadow-[0_0_30px_rgba(212,175,55,0.5)] transition-all flex items-center justify-center gap-2 disabled:opacity-50 cursor-pointer"
            >
              <Play className="h-4 w-4 fill-current" />
              <span>{submitting ? "Processing AI Triage..." : "Submit Requisition"}</span>
            </button>
          </form>

          {/* Outcome modal / card if complete */}
          {triageOutcome && (
            <div className="liquid-glass p-8 space-y-6 text-center border-brass/40 shadow-[0_0_30px_rgba(212,175,55,0.2)]">
              <div className="inline-flex p-3 rounded-full bg-brass/10 border border-brass/30 text-brass">
                <CheckCircle className="h-8 w-8" />
              </div>

              <div className="space-y-2">
                <h3 className="text-lg font-bold text-white">Requisition Submitted</h3>
                <p className="text-xs text-text-muted max-w-md mx-auto">
                  PR #{triageOutcome.requisition_id} evaluated with verdict: <strong className="text-brass uppercase">{triageOutcome.verdict}</strong>
                </p>
              </div>

              <button
                onClick={() => router.push("/queue")}
                className="px-6 py-2.5 bg-brass text-black font-bold text-xs rounded-xl shadow-[0_0_15px_rgba(212,175,55,0.3)] cursor-pointer"
              >
                Inspect in Triage Cockpit &rarr;
              </button>
            </div>
          )}

        </div>
      </div>
    </AppShell>
  );
}


