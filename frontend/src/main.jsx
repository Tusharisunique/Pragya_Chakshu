import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App.jsx';
import { LangProvider, InvProvider, OnboardProvider } from './lib/context.jsx';

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <LangProvider>
      <InvProvider>
        <OnboardProvider>
          <App />
        </OnboardProvider>
      </InvProvider>
    </LangProvider>
  </StrictMode>,
);
