import { cn } from "@/lib/utils";

interface StatusBadgeProps {
  status: string;
  className?: string;
}

const STYLES: Record<string, string> = {
  completed:  "bg-green-500/15  text-green-400  border-green-800/60",
  failed:     "bg-red-500/15    text-red-400    border-red-800/60",
  running:    "bg-blue-500/15   text-blue-400   border-blue-800/60",
  pending:    "bg-yellow-500/15 text-yellow-400 border-yellow-800/60",
  cancelled:  "bg-gray-500/15  text-gray-400   border-gray-700",
};

const DOT: Record<string, string> = {
  completed: "bg-green-400",
  failed:    "bg-red-400",
  running:   "bg-blue-400 animate-pulse",
  pending:   "bg-yellow-400 animate-pulse",
  cancelled: "bg-gray-500",
};

export default function StatusBadge({ status, className }: StatusBadgeProps) {
  const style = STYLES[status] ?? "bg-gray-800 text-gray-400 border-gray-700";
  const dot = DOT[status] ?? "bg-gray-500";

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full",
        "text-xs font-medium border",
        style,
        className
      )}
    >
      <span className={cn("w-1.5 h-1.5 rounded-full", dot)} />
      {status}
    </span>
  );
}
