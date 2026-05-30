import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { DEFAULT_DASHBOARD_THEME } from "./theme-config";
import "./themes.css";
import "./styles.css";

document.documentElement.dataset.theme = DEFAULT_DASHBOARD_THEME;

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
