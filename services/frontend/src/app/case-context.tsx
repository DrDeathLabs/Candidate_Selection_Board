import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { PropsWithChildren } from "react";

type ActiveCase = {
  id: string;
  title: string;
};

type CaseContextValue = {
  activeCase: ActiveCase | null;
  setActiveCase: (next: ActiveCase | null) => void;
};

const storageKey = "selection-board-active-case";
const CaseContext = createContext<CaseContextValue | undefined>(undefined);

export function CaseProvider({ children }: PropsWithChildren) {
  const [activeCase, setActiveCaseState] = useState<ActiveCase | null>(null);

  useEffect(() => {
    const stored = window.sessionStorage.getItem(storageKey);
    if (!stored) {
      return;
    }

    try {
      setActiveCaseState(JSON.parse(stored) as ActiveCase);
    } catch {
      window.sessionStorage.removeItem(storageKey);
    }
  }, []);

  const value = useMemo<CaseContextValue>(
    () => ({
      activeCase,
      setActiveCase(next) {
        setActiveCaseState(next);
        if (next) {
          window.sessionStorage.setItem(storageKey, JSON.stringify(next));
          return;
        }
        window.sessionStorage.removeItem(storageKey);
      },
    }),
    [activeCase],
  );

  return <CaseContext.Provider value={value}>{children}</CaseContext.Provider>;
}

export function useCaseContext() {
  const context = useContext(CaseContext);
  if (!context) {
    throw new Error("useCaseContext must be used within a CaseProvider.");
  }
  return context;
}

