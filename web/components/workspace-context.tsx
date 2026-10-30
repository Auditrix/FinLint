"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import * as api from "@/lib/api";
import type { Account, DataMode, FileSummary, Health, HistoryEntry, RunDetail } from "@/lib/types";

export type View = "findings" | "map" | "history" | "audit" | "evaluation";
export const VIEWS: readonly View[] = ["findings", "map", "history", "audit", "evaluation"];

/**
 * checking: asking the API who is signed in.
 * needed:   live, and nobody is signed in. The sign in screen shows.
 * ready:    signed in, or the saved sample, which has no accounts.
 */
export type AuthState = "checking" | "needed" | "ready";

interface WorkspaceState {
  mode: DataMode | null;
  health: Health | null;
  /** The person signed in. Always null for the saved sample. */
  account: Account | null;
  authState: AuthState;
  /** A message for the sign in screen, such as "no accounts exist yet". */
  authMessage: string | null;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  /** In the sample everything is allowed, since nothing is written anywhere. */
  canUpload: boolean;
  canDecide: boolean;
  files: FileSummary[];
  file: string | null;
  run: RunDetail | null;
  history: HistoryEntry[];
  loading: boolean;
  error: string | null;

  view: View;
  setView: (view: View) => void;
  /** The cell the inspector shows, as "Sheet!A1". */
  selected: string | null;
  select: (ref: string | null) => void;
  selectFile: (name: string) => void;

  /** Re-read the run, for example after an approval lands. */
  refresh: () => Promise<void>;
  /** Swap in a freshly checked run straight after an upload. */
  adoptRun: (run: RunDetail) => Promise<void>;

  paletteOpen: boolean;
  setPaletteOpen: (open: boolean) => void;
  uploadOpen: boolean;
  setUploadOpen: (open: boolean) => void;
}

const Context = React.createContext<WorkspaceState | null>(null);

export function useWorkspace(): WorkspaceState {
  const value = React.useContext(Context);
  if (!value) throw new Error("useWorkspace must sit inside WorkspaceProvider");
  return value;
}

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  const [mode, setMode] = React.useState<DataMode | null>(null);
  const [health, setHealth] = React.useState<Health | null>(null);
  const [account, setAccount] = React.useState<Account | null>(null);
  const [authState, setAuthState] = React.useState<AuthState>("checking");
  const [authMessage, setAuthMessage] = React.useState<string | null>(null);
  const [files, setFiles] = React.useState<FileSummary[]>([]);
  const [run, setRun] = React.useState<RunDetail | null>(null);
  const [history, setHistory] = React.useState<HistoryEntry[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [paletteOpen, setPaletteOpen] = React.useState(false);
  const [uploadOpen, setUploadOpen] = React.useState(false);

  // The URL is the source of truth for what is on screen, so a link to one
  // finding opens on that finding.
  const viewParam = params.get("view") as View | null;
  const view: View = viewParam && VIEWS.includes(viewParam) ? viewParam : "findings";
  const selected = params.get("cell");
  const fileParam = params.get("file");

  // Every change made in one handler is merged into a single URL update.
  // Building each change from the same snapshot let the last call overwrite
  // the earlier ones: "show findings, then select this cell" kept the cell and
  // lost the view.
  const pending = React.useRef<URLSearchParams | null>(null);
  const setParams = React.useCallback(
    (patch: Record<string, string | null>) => {
      if (!pending.current) {
        pending.current = new URLSearchParams(window.location.search);
        queueMicrotask(() => {
          const next = pending.current;
          pending.current = null;
          if (!next) return;
          const query = next.toString();
          router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
        });
      }
      for (const [key, value] of Object.entries(patch)) {
        if (value === null) pending.current.delete(key);
        else pending.current.set(key, value);
      }
    },
    [pathname, router],
  );

  const setView = React.useCallback((v: View) => setParams({ view: v }), [setParams]);
  const select = React.useCallback((ref: string | null) => setParams({ cell: ref }), [setParams]);
  const selectFile = React.useCallback((name: string) => setParams({ file: name, cell: null }), [setParams]);

  // Decide live or sample once, then find out who is signed in.
  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const connection = await api.connect();
        if (cancelled) return;
        // Recorded before anything else is fetched. If the API is up but a
        // later call fails, for example with the database down, the status
        // panel must still say the API is live and report the database as off.
        setMode(connection.mode);
        setHealth(connection.health);
        if (connection.mode === "sample") {
          setAuthState("ready");
          return;
        }
        const who = await api.getAccount();
        if (cancelled) return;
        setAccount(who);
        setAuthState(who ? "ready" : "needed");
      } catch (e) {
        if (cancelled) return;
        // Shown on the sign in screen: "no accounts exist yet", or the
        // database being down, are both things the person can act on.
        setAuthMessage(e instanceof Error ? e.message : "Could not reach FinLint.");
        setAuthState("needed");
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Each load gets a number, and only the newest one may write to state. Pick
  // file A then quickly file B, and A's slower answer would otherwise land
  // last and show A's findings under B's name. Signing out also bumps it, so
  // nothing loaded for the last person lands after they have gone.
  const latestLoad = React.useRef(0);

  const forget = React.useCallback(() => {
    latestLoad.current += 1;
    setAccount(null);
    setFiles([]);
    setRun(null);
    setHistory([]);
    setError(null);
    setLoading(true);
    // A dialog open when the session ended must not reopen for the next person.
    setUploadOpen(false);
    setPaletteOpen(false);
    setAuthState("needed");
  }, []);

  // A session can end while the page is open: it expires, or the person
  // signs out in another tab. Any 401 then brings back the sign in screen.
  React.useEffect(() => {
    api.whenSignedOut(forget);
    return () => api.whenSignedOut(null);
  }, [forget]);

  const signIn = React.useCallback(async (username: string, password: string) => {
    await api.signIn(username, password);
    // Ask again, to prove the browser kept the session cookie. It refuses to
    // when the page and the API look like different sites (127.0.0.1 versus
    // localhost), and signing in then looped back here with no message.
    const who = await api.getAccount();
    if (!who) {
      throw new Error(
        "Signed in, but this browser did not keep the session. Open FinLint at http://localhost:3000 or on the same address as the API.",
      );
    }
    setAuthMessage(null);
    setError(null);
    setLoading(true);
    setAccount(who);
    setAuthState("ready");
  }, []);

  const signOut = React.useCallback(async () => {
    try {
      await api.signOut();
    } catch {
      /* the cookie is gone either way once the server answers or expires */
    }
    forget();
  }, [forget]);

  // Load the list of files once someone may see them.
  React.useEffect(() => {
    if (authState !== "ready") return;
    let cancelled = false;
    (async () => {
      try {
        const list = await api.getFiles();
        if (cancelled) return;
        setFiles(list);
        if (list.length === 0) setLoading(false);
      } catch (e) {
        // A 401 has already sent everyone back to the sign in screen. Writing
        // its message here would leave it on screen for the next person.
        if (cancelled || (e instanceof api.ApiError && e.status === 401)) return;
        setError(e instanceof Error ? e.message : "Could not load FinLint.");
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [authState, account?.username]);

  const file = fileParam && files.some((f) => f.name === fileParam) ? fileParam : (files[0]?.name ?? null);

  const loadFile = React.useCallback(async (name: string) => {
    const ticket = ++latestLoad.current;
    // The previous workbook's run is cleared straight away. Leaving it on
    // screen while the next one loads, or after it fails, put one file's
    // findings under another file's name with no sign anything was wrong.
    setRun(null);
    setHistory([]);
    setLoading(true);
    setError(null);
    try {
      const [r, h] = await Promise.all([api.getRun(name), api.getHistory(name)]);
      if (ticket !== latestLoad.current) return;
      setRun(r);
      setHistory(h);
    } catch (e) {
      if (ticket !== latestLoad.current) return;
      setError(e instanceof Error ? e.message : "Could not load this workbook.");
    } finally {
      if (ticket === latestLoad.current) setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    if (file) void loadFile(file);
  }, [file, loadFile]);

  const refresh = React.useCallback(async () => {
    if (!file) return;
    // Same guard as loadFile: if the user switches workbook while this is in
    // flight, its answer belongs to the old one and is dropped.
    const ticket = latestLoad.current;
    const r = await api.getRun(file);
    if (ticket === latestLoad.current) setRun(r);
  }, [file]);

  const adoptRun = React.useCallback(
    async (fresh: RunDetail) => {
      // A fresh check outranks anything still loading.
      const ticket = ++latestLoad.current;
      const [list, h] = await Promise.all([api.getFiles(), api.getHistory(fresh.file)]);
      if (ticket !== latestLoad.current) return;
      // The list is updated BEFORE the URL points at the new file. In the
      // other order the new name is not in the list yet, the app falls back to
      // the first file, and that load cancels this one.
      setFiles(list);
      setRun(fresh);
      setHistory(h);
      setLoading(false);
      setError(null);
      setParams({ file: fresh.file, cell: null, view: "findings" });
    },
    [setParams],
  );

  // Command palette on Cmd or Ctrl + K.
  React.useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // The sample has no accounts and writes nothing, so it shows every action.
  const canUpload = mode !== "live" || Boolean(account?.can_upload);
  const canDecide = mode !== "live" || Boolean(account?.can_decide);

  const value: WorkspaceState = {
    mode,
    health,
    account,
    authState,
    authMessage,
    signIn,
    signOut,
    canUpload,
    canDecide,
    files,
    file,
    run,
    history,
    loading,
    error,
    view,
    setView,
    selected,
    select,
    selectFile,
    refresh,
    adoptRun,
    paletteOpen,
    setPaletteOpen,
    uploadOpen,
    setUploadOpen,
  };

  return <Context.Provider value={value}>{children}</Context.Provider>;
}
