import { useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import type { CaseSummary } from "./api";
import { useCaseContext } from "../app/case-context";

export function useResolvedCaseId(cases: CaseSummary[] | undefined) {
  const [searchParams, setSearchParams] = useSearchParams();
  const { activeCase, setActiveCase } = useCaseContext();

  const caseId = searchParams.get("caseId") ?? activeCase?.id ?? cases?.[0]?.id ?? null;

  const selectedCase = useMemo(
    () => cases?.find((entry) => entry.id === caseId) ?? null,
    [caseId, cases],
  );

  useEffect(() => {
    if (!caseId || !selectedCase) {
      return;
    }

    if (activeCase?.id === caseId) {
      return;
    }

    setActiveCase({ id: selectedCase.id, title: selectedCase.title });
  }, [activeCase?.id, caseId, selectedCase, setActiveCase]);

  function selectCase(nextCaseId: string | null) {
    const nextParams = new URLSearchParams(searchParams);
    if (nextCaseId) {
      nextParams.set("caseId", nextCaseId);
      const match = cases?.find((entry) => entry.id === nextCaseId);
      if (match) {
        setActiveCase({ id: match.id, title: match.title });
      }
    } else {
      nextParams.delete("caseId");
      setActiveCase(null);
    }
    setSearchParams(nextParams, { replace: true });
  }

  return { caseId, selectedCase, selectCase };
}
