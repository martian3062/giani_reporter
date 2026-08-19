import { CheckCircle2, Info, TriangleAlert, X } from "lucide-react";
import { useDesk } from "../DeskContext";

export function Toasts() {
  const { toasts, dismissToast } = useDesk();

  return (
    <div className="toast-region" aria-live="polite" aria-label="Notifications">
      {toasts.map((toast) => {
        const Icon =
          toast.tone === "success"
            ? CheckCircle2
            : toast.tone === "error"
              ? TriangleAlert
              : Info;
        return (
          <div className={`toast toast-${toast.tone}`} key={toast.id}>
            <Icon size={18} aria-hidden="true" />
            <p>{toast.message}</p>
            <button
              className="icon-button"
              type="button"
              aria-label="Dismiss notification"
              onClick={() => dismissToast(toast.id)}
            >
              <X size={16} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
