import { useCallback, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

/** Navigate to the previous in-app route, or `fallback` when opened via direct link. */
export function useNavigateBack(fallback: string) {
  const navigate = useNavigate();
  const location = useLocation();

  return useCallback(() => {
    if (location.key !== "default") {
      navigate(-1);
    } else {
      navigate(fallback);
    }
  }, [navigate, location.key, fallback]);
}

interface BackButtonProps {
  fallback: string;
  className?: string;
  children?: ReactNode;
}

export function BackButton({ fallback, className, children = "Back" }: BackButtonProps) {
  const goBack = useNavigateBack(fallback);
  return (
    <button type="button" onClick={goBack} className={className ?? "btn-ghost -ml-2 text-sm"}>
      <ArrowLeft size={16} /> {children}
    </button>
  );
}
