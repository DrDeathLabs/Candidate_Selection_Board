import { createBrowserRouter, Navigate, Outlet } from "react-router-dom";

import { useAuth } from "./auth-context";
import { App } from "./App";
import { AdminUsersPage } from "../pages/AdminUsersPage";
import { SocLogPage } from "../pages/SocLogPage";
import { SessionMonitorPage } from "../pages/SessionMonitorPage";
import { WorkspaceEntryPage } from "../pages/WorkspaceEntryPage";
import { AdjudicationPage } from "../pages/AdjudicationPage";
import { AgentConfigPage } from "../pages/AgentConfigPage";
import { AdminPage } from "../pages/AdminPage";
import { AISettingsPage } from "../pages/AISettingsPage";
import { AuditLogPage } from "../pages/AuditLogPage";
import { CandidateEvaluationPage } from "../pages/CandidateEvaluationPage";
import { CandidateProfilePage } from "../pages/CandidateProfilePage";
import { CandidateReconciliationPage } from "../pages/CandidateReconciliationPage";
import { ComparisonPage } from "../pages/ComparisonPage";
import { CreateCasePage } from "../pages/CreateCasePage";
import { DashboardPage } from "../pages/DashboardPage";
import { DocumentUploadPage } from "../pages/DocumentUploadPage";
import { ExpertCouncilPage } from "../pages/ExpertCouncilPage";
import { EngagementPrepPage } from "../pages/EngagementPrepPage";
import { EngagementDecisionPage } from "../pages/EngagementDecisionPage";
import { EngagementReviewPage } from "../pages/EngagementReviewPage";
import { EngagementsPage } from "../pages/EngagementsPage";
import { ExportCenterPage } from "../pages/ExportCenterPage";
import { InterviewPlanningPage } from "../pages/InterviewPlanningPage";
import { LoginPage } from "../pages/LoginPage";
import { OperationsCenterPage } from "../pages/OperationsCenterPage";
import { PDAnalysisPage } from "../pages/PDAnalysisPage";
import { ProcessingStatusPage } from "../pages/ProcessingStatusPage";
import { RubricBuilderPage } from "../pages/RubricBuilderPage";
import { SecurityCenterPage } from "../pages/SecurityCenterPage";
import { SelectionRecommendationPage } from "../pages/SelectionRecommendationPage";

function ProtectedRoute() {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) return null; // Wait for session check before redirecting
  return isAuthenticated ? <Outlet /> : <Navigate to="/login" replace />;
}

export const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    path: "/",
    element: <ProtectedRoute />,
    children: [
      {
        path: "/",
        element: <App />,
        children: [
          { index: true, element: <WorkspaceEntryPage /> },
          { path: "engagements", element: <EngagementsPage /> },
          { path: "engagements/:engagementId/prep", element: <EngagementPrepPage /> },
          { path: "engagements/:engagementId/review", element: <EngagementReviewPage /> },
          { path: "engagements/:engagementId/decision", element: <EngagementDecisionPage /> },
          { path: "cases/new", element: <CreateCasePage /> },
          { path: "documents/upload", element: <DocumentUploadPage /> },
          { path: "documents/status", element: <ProcessingStatusPage /> },
          { path: "candidates/reconciliation", element: <CandidateReconciliationPage /> },
          { path: "analysis/pd", element: <PDAnalysisPage /> },
          { path: "rubrics", element: <RubricBuilderPage /> },
          { path: "evaluations", element: <CandidateEvaluationPage /> },
          { path: "candidates/profile", element: <CandidateProfilePage /> },
          { path: "expert-council", element: <ExpertCouncilPage /> },
          { path: "comparison", element: <ComparisonPage /> },
          { path: "interviews", element: <InterviewPlanningPage /> },
          { path: "adjudication", element: <AdjudicationPage /> },
          { path: "selection", element: <SelectionRecommendationPage /> },
          { path: "exports", element: <ExportCenterPage /> },
          { path: "audit", element: <AuditLogPage /> },
          { path: "admin", element: <AdminPage /> },
          { path: "admin/operations", element: <OperationsCenterPage /> },
          { path: "admin/security", element: <SecurityCenterPage /> },
          { path: "admin/ai", element: <AISettingsPage /> },
          { path: "admin/agents", element: <AgentConfigPage /> },
          { path: "admin/users", element: <AdminUsersPage /> },
          { path: "admin/soc-log", element: <SocLogPage /> },
          { path: "admin/sessions", element: <SessionMonitorPage /> },
        ],
      },
    ],
  },
]);
