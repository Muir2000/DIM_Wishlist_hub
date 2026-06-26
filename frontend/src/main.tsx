import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { LanguageProvider } from "./i18n";
import { WishlistProvider } from "./store";
import "./theme.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <LanguageProvider>
      <WishlistProvider>
        <App />
      </WishlistProvider>
    </LanguageProvider>
  </React.StrictMode>,
);