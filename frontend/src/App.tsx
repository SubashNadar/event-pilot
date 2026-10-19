import { AgentProvider } from "./hooks/useAgentStream";
import AppShell from "./components/AppShell";

export default function App() {
  return (
    <AgentProvider>
      <AppShell />
    </AgentProvider>
  );
}
