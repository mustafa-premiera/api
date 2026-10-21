import React from "react";
import { createRoot } from "react-dom/client";
import { AuthProvider } from "react-oidc-context";
import App from "./App.jsx";
import "./styles.css";

const root = createRoot(document.getElementById("root"));

fetch("/config.json")
  .then((r) => {
    if (!r.ok) throw new Error(`config.json: ${r.status}`);
    return r.json();
  })
  .then((config) => {
    const oidc = {
      authority: config.authority,
      client_id: config.clientId,
      redirect_uri: config.redirectUri,
      scope: "openid email profile",
      onSigninCallback: () => history.replaceState({}, "", "/"),
    };
    root.render(
      <React.StrictMode>
        <AuthProvider {...oidc}>
          <App config={config} />
        </AuthProvider>
      </React.StrictMode>
    );
  })
  .catch((err) => {
    root.render(<p className="fatal">Could not load app configuration: {err.message}</p>);
  });
