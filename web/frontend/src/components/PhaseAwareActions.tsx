import type { ReactElement } from "react";

/**
 * Wrapper that disables its children when the contest is in the "upcoming"
 * phase (before start). Actions that would alter live state (add participant,
 * register team, edit problem set) are disabled until the contest starts.
 * Metadata edits are allowed anytime and are NOT wrapped.
 */
export default function PhaseAwareActions({
  phase,
  children,
}: {
  phase: string;
  children: ReactElement | ReactElement[];
}) {
  const disabled = phase === "upcoming";
  const items = Array.isArray(children) ? children : [children];
  return (
    <>
      {items.map((child, i) =>
        child
          ? {
              ...child,
              props: {
                ...child.props,
                disabled: disabled || child.props.disabled === true,
                key: child.key ?? i,
              },
            }
          : child,
      )}
    </>
  );
}
