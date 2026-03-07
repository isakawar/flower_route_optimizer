"use client";

import { formatMinutes } from "@/lib/utils";
import type { OptimizationResult } from "@/types";

interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
  accentColor?: string;
}

function StatCard({ icon, label, value, sub, accentColor = "rgba(212,165,191,0.12)" }: StatCardProps) {
  return (
    <div className="card-base p-5 flex items-start gap-4 group hover:shadow-card-hover transition-shadow duration-300">
      <div
        className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5"
        style={{ background: accentColor, border: "1px solid rgba(255,255,255,0.06)" }}
      >
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-text-muted text-xs uppercase tracking-wider mb-1">{label}</p>
        <p className="text-text-primary text-2xl font-semibold leading-none">{value}</p>
        {sub && <p className="text-text-muted text-xs mt-1">{sub}</p>}
      </div>
    </div>
  );
}

export default function StatsPanel({ stats }: { stats: OptimizationResult["stats"] }) {
  const { totalDeliveries, totalDriveMin, totalDistanceKm, numCouriers } = stats;

  const avgPerCourier =
    numCouriers > 0 ? Math.round(totalDeliveries / numCouriers) : 0;

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
      <StatCard
        icon={
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#d4a5bf" strokeWidth="1.75">
            <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" strokeLinecap="round" strokeLinejoin="round" />
            <circle cx="12" cy="10" r="3" />
          </svg>
        }
        label="Доставок"
        value={String(totalDeliveries)}
        sub={`~${avgPerCourier} на кур'єра`}
        accentColor="rgba(212,165,191,0.10)"
      />

      <StatCard
        icon={
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#c9a96e" strokeWidth="1.75">
            <circle cx="12" cy="12" r="10" />
            <polyline points="12 6 12 12 16 14" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        }
        label="Час у дорозі"
        value={formatMinutes(totalDriveMin)}
        sub="загалом усі кур'єри"
        accentColor="rgba(201,169,110,0.10)"
      />

      <StatCard
        icon={
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#8bd4c0" strokeWidth="1.75">
            <path d="M3 12h18M3 6l9-3 9 3M3 18l9 3 9-3" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        }
        label="Відстань"
        value={`${totalDistanceKm.toFixed(1)} км`}
        sub="загальний пробіг"
        accentColor="rgba(139,212,192,0.10)"
      />

      <StatCard
        icon={
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#a88bd4" strokeWidth="1.75">
            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" strokeLinecap="round" strokeLinejoin="round" />
            <circle cx="9" cy="7" r="4" />
            <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        }
        label="Кур'єрів"
        value={String(numCouriers)}
        sub="активних маршрутів"
        accentColor="rgba(168,139,212,0.10)"
      />
    </div>
  );
}
