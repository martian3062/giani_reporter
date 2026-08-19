import { Navigate, Route, Routes } from "react-router";
import { AppShell } from "./components/AppShell";
import { LibraryPage } from "./pages/LibraryPage";
import { OverviewPage } from "./pages/OverviewPage";
import { PostStudioPage } from "./pages/PostStudioPage";
import { ResearchPage } from "./pages/ResearchPage";
import { RunsPage } from "./pages/RunsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { StudioPage } from "./pages/StudioPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<OverviewPage />} />
        <Route path="research" element={<ResearchPage />} />
        <Route path="studio" element={<StudioPage />} />
        <Route path="posts" element={<PostStudioPage />} />
        <Route path="library" element={<LibraryPage />} />
        <Route path="runs" element={<RunsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
