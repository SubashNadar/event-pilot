import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { AgentProvider } from './hooks/useAgentStream';
import './index.css';
import './run/run.css';
import './styles.css';
import './modal.css';
import './theme.css';

createRoot(document.getElementById('root')).render(<StrictMode><AgentProvider><App /></AgentProvider></StrictMode>);
