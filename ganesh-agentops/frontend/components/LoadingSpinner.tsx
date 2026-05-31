import { Loader2 } from "lucide-react";

interface LoadingSpinnerProps {
  message?: string;
}

export default function LoadingSpinner({
  message = "Loading…",
}: LoadingSpinnerProps) {
  return (
    <div className="flex flex-col items-center justify-center py-24 gap-3 text-gray-500">
      <Loader2 size={28} className="animate-spin text-blue-500" />
      <p className="text-sm">{message}</p>
    </div>
  );
}
