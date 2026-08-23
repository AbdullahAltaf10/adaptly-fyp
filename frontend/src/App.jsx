import { AssistantPanel } from "./features/ai-assistant/AssistantPanel";
import { fallbackStudyContext } from "./features/ai-assistant/demoStudyContext";

function App() {
  return (
    <main className="app-shell">
      <AssistantPanel studyContext={fallbackStudyContext} />
    </main>
  );
}

export default App;
