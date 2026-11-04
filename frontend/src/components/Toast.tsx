import React, { createContext, useContext, useState, useCallback } from 'react';
import { CheckCircle2, AlertCircle, Info, X } from 'lucide-react';

export type ToastType = 'success' | 'error' | 'info';

export interface ToastItem {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
  durationMs?: number;
}

interface ToastContextValue {
  showToast: (type: ToastType, title: string, message?: string, durationMs?: number) => void;
  showSuccess: (title: string, message?: string) => void;
  showError: (title: string, message?: string) => void;
  showInfo: (title: string, message?: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  const showToast = useCallback(
    (type: ToastType, title: string, message?: string, durationMs = 4500) => {
      const id = `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
      setToasts(prev => [...prev, { id, type, title, message, durationMs }]);

      if (durationMs > 0) {
        setTimeout(() => {
          removeToast(id);
        }, durationMs);
      }
    },
    [removeToast]
  );

  const showSuccess = useCallback((title: string, message?: string) => showToast('success', title, message), [showToast]);
  const showError = useCallback((title: string, message?: string) => showToast('error', title, message, 6500), [showToast]);
  const showInfo = useCallback((title: string, message?: string) => showToast('info', title, message), [showToast]);

  return (
    <ToastContext.Provider value={{ showToast, showSuccess, showError, showInfo }}>
      {children}
      {/* Toast Overlay Container */}
      <div
        className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm w-full pointer-events-none px-4 sm:px-0"
        aria-live="polite"
        aria-atomic="true"
      >
        {toasts.map(toast => {
          const isError = toast.type === 'error';
          const isSuccess = toast.type === 'success';

          return (
            <div
              key={toast.id}
              role="alert"
              className={`pointer-events-auto p-3.5 rounded-xl border shadow-xl flex items-start gap-3 transition-all transform duration-200 ${
                isError
                  ? 'bg-rose-950/95 border-rose-800/80 text-rose-100 shadow-rose-950/40'
                  : isSuccess
                  ? 'bg-emerald-950/95 border-emerald-800/80 text-emerald-100 shadow-emerald-950/40'
                  : 'bg-slate-900/95 border-slate-700/80 text-slate-100 shadow-slate-950/40'
              }`}
            >
              <div className="mt-0.5 flex-shrink-0">
                {isError && <AlertCircle className="w-4 h-4 text-rose-400" />}
                {isSuccess && <CheckCircle2 className="w-4 h-4 text-emerald-400" />}
                {!isError && !isSuccess && <Info className="w-4 h-4 text-sky-400" />}
              </div>

              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold leading-snug">{toast.title}</p>
                {toast.message && (
                  <p className="text-[11px] opacity-80 mt-0.5 leading-relaxed break-words font-mono">
                    {toast.message}
                  </p>
                )}
              </div>

              <button
                onClick={() => removeToast(toast.id)}
                className="text-slate-400 hover:text-white p-1 rounded-md transition focus:outline-none focus:ring-1 focus:ring-slate-400"
                aria-label="Close notification"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
};

export const useToast = (): ToastContextValue => {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
};

