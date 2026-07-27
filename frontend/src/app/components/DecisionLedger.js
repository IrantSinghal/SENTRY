"use client";

import React, { useState, useEffect } from "react";
import { 
  CheckCircle, 
  AlertTriangle, 
  Cpu, 
  ChevronDown, 
  ChevronUp, 
  Info,
  DollarSign,
  ShieldAlert,
  Copy,
  Layers,
  Sparkles
} from "lucide-react";

export default function DecisionLedger({ requisition }) {
  const [visibleStepCount, setVisibleStepCount] = useState(0);
  const [expandedStepId, setExpandedStepId] = useState(null);

  useEffect(() => {
    if (!requisition) return;
    setVisibleStepCount(0);
    setExpandedStepId(null);
    
    const interval = setInterval(() => {
      setVisibleStepCount((prev) => {
        if (prev >= 7) {
          clearInterval(interval);
          return 7;
        }
        return prev + 1;
      });
    }, 150);

    return () => clearInterval(interval);
  }, [requisition?.requisition_id]);

  if (!requisition) return null;

  const {
    requisition_id,
    created_at,
    verdict,
    confidence_score,
    rationale,
    total_value,
    signals = {},
    intra_pr_material_overlap = [],
    items = []
  } = requisition;

  const toggleExpand = (stepId) => {
    setExpandedStepId((prev) => (prev === stepId ? null : stepId));
  };

  const steps = [
    {
      id: "ingest",
      title: "1. Intake & Schema Parsing",
      status: "Validated",
      isFlagged: false,
      details: `Parsed purchase requisition #${requisition_id} from SAP ERP buffer cleanly.`,
      why: "Initial payload structure validated against RFC-4180 / SAP PR JSON schema.",
      cause: [
        { label: "Draft Requisition ID", value: requisition_id },
        { label: "Line Item Count", value: `${items.length} items` },
        { label: "Payload Status", value: "Schema Clean" }
      ]
    },
    {
      id: "duplicate",
      title: "2. Historical Duplicate Check",
      status: signals.duplicate_detection?.flagged || signals.duplicate_detection?.is_duplicate ? "Duplicate Flagged" : "Cleared",
      isFlagged: signals.duplicate_detection?.flagged || signals.duplicate_detection?.is_duplicate,
      details: (signals.duplicate_detection?.flagged || signals.duplicate_detection?.is_duplicate)
        ? "Identical material line items submitted within rolling 30-day window."
        : "Zero duplicate purchase requisitions detected in 30-day index.",
      why: (signals.duplicate_detection?.flagged || signals.duplicate_detection?.is_duplicate)
        ? "Cross-referenced open PR ledger for identical material requirements within the configured 30-day window."
        : "No open PR contains matching material line items within the 30-day duplicate check window.",
      causeData: signals.duplicate_detection?.details || [],
      causeReasons: signals.duplicate_detection?.reasons || []
    },
    {
      id: "vendor",
      title: "3. Vendor Risk & Sanctions Screening",
      status: signals.vendor_risk?.flagged || signals.vendor_risk?.is_risky ? "Risk Flagged" : "Verified",
      isFlagged: signals.vendor_risk?.flagged || signals.vendor_risk?.is_risky,
      details: (signals.vendor_risk?.flagged || signals.vendor_risk?.is_risky)
        ? "Vendor tax ID or watchlist screening flagged for compliance review."
        : "Vendor identity verified against active master registry with zero watchlist hits.",
      why: (signals.vendor_risk?.flagged || signals.vendor_risk?.is_risky)
        ? "Third-party registry, fuzzy sanctions screening, or vendor onboarding age triggered compliance risk flags."
        : "Vendor onboarded > 90 days ago with verified business registration and zero sanctions watchlist matches.",
      causeData: signals.vendor_risk?.details || [],
      causeReasons: signals.vendor_risk?.reasons || []
    },
    {
      id: "price",
      title: "4. Price Anomaly & Baseline Check",
      status: signals.price_anomaly?.flagged || signals.price_anomaly?.has_anomaly ? "Price Anomaly" : "Cleared",
      isFlagged: signals.price_anomaly?.flagged || signals.price_anomaly?.has_anomaly,
      details: (signals.price_anomaly?.flagged || signals.price_anomaly?.has_anomaly)
        ? "Price deviation exceeds historical baseline threshold."
        : "Line item unit prices fall within standard procurement variance limits.",
      why: (signals.price_anomaly?.flagged || signals.price_anomaly?.has_anomaly)
        ? "Line item unit prices exceed historical material/vendor baseline pricing by more than the 15% tolerance cap."
        : "All line item unit prices fall within expected 15% historical average pricing variance.",
      causeData: signals.price_anomaly?.details || [],
      causeReasons: signals.price_anomaly?.reasons || []
    },
    {
      id: "policy",
      title: "5. Corporate Spending Policy Gate",
      status: signals.policy_compliance?.violates_policy ? "Policy Flag" : "Compliant",
      isFlagged: signals.policy_compliance?.violates_policy,
      details: signals.policy_compliance?.violates_policy
        ? "Requisition violates corporate procurement spending threshold or authorization cap."
        : "Fully compliant with corporate purchasing policies and limit rules.",
      why: signals.policy_compliance?.violates_policy
        ? "Total estimated requisition value exceeds the $5,000 auto-approval ceiling or contains restricted material/sanctioned vendor flags."
        : "Total requisition value falls within the standard unit operating threshold ($5,000).",
      causeReasons: signals.policy_compliance?.reasons || [
        `Requisition total ($${(total_value || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}) evaluated against $5,000 ceiling.`
      ]
    },
    {
      id: "overlap",
      title: "6. Intra-PR Line Item Scan",
      status: intra_pr_material_overlap?.length > 0 ? "Overlap Flagged" : "Cleared",
      isFlagged: intra_pr_material_overlap?.length > 0,
      details: intra_pr_material_overlap?.length > 0
        ? "Multiple line items request identical material across vendor accounts."
        : "Line items contain clean vendor-to-material mappings.",
      why: intra_pr_material_overlap?.length > 0
        ? "Identical material IDs requested across multiple line items inside the same purchase requisition."
        : "Each line item requests a distinct material ID.",
      causeOverlap: intra_pr_material_overlap
    },
    {
      id: "synthesis",
      title: "7. Autonomous Verdict Synthesis",
      status: verdict === "auto_approve" ? "Auto Approved" : (verdict?.toUpperCase() || "Review Required"),
      isFlagged: verdict === "reject" || verdict === "escalate" || verdict === "req_vp",
      details: `Confidence: ${Math.round((confidence_score || 0) * 100)}% — ${rationale || "Requisition evaluated by LangGraph decision pipeline."}`,
      why: "Final reasoning synthesis compiled from node evaluation matrix.",
      cause: [
        { label: "Verdict Class", value: verdict?.toUpperCase() || "N/A" },
        { label: "AI Confidence", value: `${Math.round((confidence_score || 0) * 100)}%` },
        { label: "Action Path", value: verdict === "auto_approve" ? "Autonomous Release" : "Escalation Queue" }
      ]
    }
  ];

  return (
    <div className="space-y-4 font-72">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/10 pb-3">
        <div className="flex items-center gap-2">
          <Cpu className="h-4 w-4 text-brass" />
          <span className="text-sm font-bold text-white tracking-wide">
            Agent Reasoning Trace
          </span>
        </div>
        <span className="liquid-pill px-3 py-1 text-[11px] font-semibold text-brass">
          Click Node to Inspect
        </span>
      </div>

      {/* Staggered Vertical Timeline */}
      <div className="space-y-3 pt-1">
        {steps.map((step, idx) => {
          const isVisible = idx < visibleStepCount;
          if (!isVisible) return null;
          const isExpanded = expandedStepId === step.id;

          return (
            <div 
              key={step.id}
              onClick={() => toggleExpand(step.id)}
              className={`p-4 rounded-xl transition-all duration-300 transform cursor-pointer border ${
                step.isFlagged 
                  ? "bg-risk-critical/10 border-risk-critical/40 text-white shadow-[0_0_15px_rgba(224,108,103,0.15)] hover:border-risk-critical" 
                  : "liquid-glass hover:border-brass/40"
              }`}
            >
              <div className="flex items-center justify-between gap-3 mb-1">
                <div className="flex items-center gap-2">
                  {step.isFlagged ? (
                    <AlertTriangle className="h-4 w-4 text-risk-critical shrink-0 animate-pulse" />
                  ) : (
                    <CheckCircle className="h-4 w-4 text-risk-clear shrink-0" />
                  )}
                  <span className="text-xs font-bold text-white">
                    {step.title}
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <span className={`text-[10px] font-bold px-2.5 py-0.5 rounded-full border uppercase ${
                    step.isFlagged 
                      ? "bg-risk-critical/20 border-risk-critical/40 text-risk-critical" 
                      : "bg-risk-clear/15 border-risk-clear/30 text-risk-clear"
                  }`}>
                    {step.status}
                  </span>
                  {isExpanded ? (
                    <ChevronUp className="h-4 w-4 text-text-muted" />
                  ) : (
                    <ChevronDown className="h-4 w-4 text-text-muted" />
                  )}
                </div>
              </div>

              <p className={`text-xs leading-relaxed pl-6 ${
                step.isFlagged ? "text-white font-medium" : "text-text-muted"
              }`}>
                {step.details}
              </p>

              {/* Expanded Anomaly Insight Details Card */}
              {isExpanded && (
                <div 
                  onClick={(e) => e.stopPropagation()} 
                  className="mt-4 ml-6 p-4 rounded-xl bg-black/40 border border-white/15 space-y-3 font-72 animate-in fade-in slide-in-from-top-2 duration-200"
                >
                  {/* Why it was flagged */}
                  <div className="space-y-1">
                    <div className="flex items-center gap-1.5 text-xs font-bold text-brass uppercase tracking-wider">
                      <Info className="h-3.5 w-3.5" />
                      <span>Why it was evaluated</span>
                    </div>
                    <p className="text-xs text-white leading-relaxed bg-white/5 p-2.5 rounded-lg border border-white/10">
                      {step.why}
                    </p>
                  </div>

                  {/* What caused the anomaly */}
                  <div className="space-y-2 pt-1 border-t border-white/10">
                    <div className="flex items-center gap-1.5 text-xs font-bold text-brass uppercase tracking-wider">
                      <Sparkles className="h-3.5 w-3.5" />
                      <span>Anomaly Root-Cause Breakdown</span>
                    </div>

                    {/* Simple Cause Key-Values */}
                    {step.cause && (
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        {step.cause.map((c, i) => (
                          <div key={i} className="p-2 rounded bg-white/5 border border-white/10">
                            <span className="text-text-muted block text-[10px]">{c.label}</span>
                            <span className="font-bold text-white">{c.value}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Specific Reasons text list */}
                    {step.causeReasons && step.causeReasons.length > 0 && (
                      <div className="space-y-1.5">
                        {step.causeReasons.map((reason, i) => (
                          <div key={i} className="p-2.5 rounded bg-risk-critical/10 border border-risk-critical/30 text-xs text-white flex items-start gap-2">
                            <AlertTriangle className="h-3.5 w-3.5 text-risk-critical shrink-0 mt-0.5" />
                            <span>{reason}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Price Anomaly Item breakdown table */}
                    {step.id === "price" && step.causeData && step.causeData.length > 0 && (
                      <div className="overflow-x-auto">
                        <table className="w-full text-left text-[11px] border-collapse">
                          <thead>
                            <tr className="border-b border-white/10 text-text-muted font-bold">
                              <th className="p-1.5">Material</th>
                              <th className="p-1.5">Vendor</th>
                              <th className="p-1.5">Current Price</th>
                              <th className="p-1.5">Hist. Avg</th>
                              <th className="p-1.5">Deviation</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-white/10">
                            {step.causeData.map((item, i) => (
                              <tr key={i} className={item.is_anomaly ? "text-risk-critical font-bold" : "text-white"}>
                                <td className="p-1.5">{item.material}</td>
                                <td className="p-1.5">{item.vendor_id}</td>
                                <td className="p-1.5">${(item.current_price || 0).toFixed(2)}</td>
                                <td className="p-1.5">${(item.historical_avg_price || 0).toFixed(2)}</td>
                                <td className="p-1.5">+{Math.round((item.deviation_percentage || 0) * 100)}%</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}

                    {/* Vendor Risk breakdown details */}
                    {step.id === "vendor" && step.causeData && step.causeData.length > 0 && (
                      <div className="space-y-2">
                        {step.causeData.map((v, i) => (
                          <div key={i} className="p-2.5 rounded bg-white/5 border border-white/10 space-y-1 text-xs">
                            <div className="flex justify-between font-bold text-white">
                              <span>{v.vendor_name} ({v.vendor_id})</span>
                              <span>Age: {v.onboarded_days_ago} days</span>
                            </div>
                            {v.sanctions_match && (
                              <div className="text-risk-critical font-bold text-[11px]">
                                Sanctions Match: {v.sanctions_match_detail}
                              </div>
                            )}
                            {v.registry_detail && (
                              <div className="text-text-muted text-[11px]">
                                Registry: {v.registry_detail}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Duplicate breakdown */}
                    {step.id === "duplicate" && step.causeData && step.causeData.length > 0 && (
                      <div className="space-y-1.5">
                        {step.causeData.map((d, i) => (
                          <div key={i} className="p-2 rounded bg-brass/10 border border-brass/30 text-xs text-white">
                            Matching PR: <strong className="text-brass">#{d.matching_requisition_id}</strong> (Material: {d.material}, Group: {d.purchasing_group})
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Intra-PR Overlap breakdown */}
                    {step.causeOverlap && step.causeOverlap.length > 0 && (
                      <div className="space-y-1.5">
                        {step.causeOverlap.map((o, i) => (
                          <div key={i} className="p-2 rounded bg-brass/10 border border-brass/30 text-xs text-white">
                            Material <strong className="text-brass">{o.material}</strong> requested across vendors: {o.vendor_ids?.join(", ")}
                          </div>
                        ))}
                      </div>
                    )}

                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}



