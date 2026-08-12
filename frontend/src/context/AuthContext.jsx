/**
 * Authentication state, shared across the whole app.
 *
 * Without context, the current user would have to be threaded through
 * every component as props -- the sidebar needs the name, the coach
 * page needs the id, and everything between them has to pass it along
 * without using it. Context lets any component ask for it directly.
 */

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, tokenStore } from "../lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  // Starts true: on load there may be a stored token, and we have to
  // ask the server whether it is still valid before deciding what to
  // render. Without this the login screen flashes on every refresh.
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = tokenStore.get();
    if (!token) {
      setLoading(false);
      return;
    }

    // A token in localStorage proves nothing -- it may be expired, or
    // belong to a deleted account. /me is the check.
    api
      .me()
      .then(setUser)
      .catch(() => tokenStore.clear())
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email, password) => {
    const { access_token } = await api.login(email, password);
    tokenStore.set(access_token);
    const profile = await api.me();
    setUser(profile);
    return profile;
  }, []);

  const register = useCallback(
    async (payload) => {
      await api.register(payload);
      // Log in immediately after registering. Making someone type
      // credentials again straight after choosing them is a pointless
      // extra step.
      return login(payload.email, payload.password);
    },
    [login]
  );

  const logout = useCallback(() => {
    tokenStore.clear();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  // Fails loudly and immediately if a component is rendered outside
  // the provider, instead of silently reading undefined and breaking
  // somewhere less obvious.
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
