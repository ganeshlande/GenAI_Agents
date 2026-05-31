import { cn } from "@/lib/utils";

interface StatsCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  accent?: "default" | "blue" | "green" | "yellow" | "red";
  className?: string;
}

const ACCENT = {
  default: "border-gray-800",
  blue:    "border-blue-800/60",
  green:   "border-green-800/60",
  yellow:  "border-yellow-800/60",
  red:     "border-red-800/60",
};

export default function StatsCard({
  title,
  value,
  subtitle,
  accent = "default",
  className,
}: StatsCardProps) {
  return (
    <div
      className={cn(
        "rounded-xl border bg-gray-900/60 px-5 py-4 space-y-1",
        ACCENT[accent],
        className
      )}
    >
      <p className="text-xs text-gray-500 uppercase tracking-wider font-medium">
        {title}
      </p>
      <p className="text-2xl font-bold text-white tabular-nums">{value}</p>
      {subtitle && (
        <p className="text-xs text-gray-600">{subtitle}</p>
      )}
    </div>
  );
}
