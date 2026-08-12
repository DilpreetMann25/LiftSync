import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

// StrictMode deliberately double-invokes effects in development to
// surface bugs caused by missing cleanup. It does nothing in a
// production build.
createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>
);
