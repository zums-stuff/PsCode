import { createContext, useCallback, useContext, useState } from "react";
import ConfirmDialog from "../components/ConfirmDialog";

/**
 * Programmatic confirm dialog (UX P0).
 *
 * Replaces `window.confirm()` with a proper modal — same call site,
 * promise-based API so existing async code stays the same:
 *
 *   const ok = await confirm({ title: "...", message: "..." });
 *   if (!ok) return;
 */

export interface ConfirmOptions {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "primary" | "danger";
}

interface ConfirmContextValue {
  confirm: (opts: ConfirmOptions) => Promise<boolean>;
}

const ConfirmContext = createContext<ConfirmContextValue | null>(null);

interface PendingConfirm extends ConfirmOptions {
  resolve: (value: boolean) => void;
}

export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const [pending, setPending] = useState<PendingConfirm | null>(null);

  const confirm = useCallback(
    (opts: ConfirmOptions) =>
      new Promise<boolean>((resolve) => {
        setPending({ ...opts, resolve });
      }),
    [],
  );

  return (
    <ConfirmContext.Provider value={{ confirm }}>
      {children}
      <ConfirmDialog
        open={pending !== null}
        title={pending?.title ?? ""}
        message={pending?.message ?? ""}
        confirmLabel={pending?.confirmLabel}
        cancelLabel={pending?.cancelLabel}
        variant={pending?.variant}
        onConfirm={() => {
          pending?.resolve(true);
          setPending(null);
        }}
        onCancel={() => {
          pending?.resolve(false);
          setPending(null);
        }}
      />
    </ConfirmContext.Provider>
  );
}

export function useConfirm(): (opts: ConfirmOptions) => Promise<boolean> {
  const ctx = useContext(ConfirmContext);
  if (ctx !== null) return ctx.confirm;
  // Fallback: return a function that resolves true so tests/standalone
  // renders don't crash. The real production path always wraps with
  // ConfirmProvider.
  return async () => true;
}
