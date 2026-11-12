import { useEffect, useSyncExternalStore } from "react";
import { startDemo, type Demo } from "./demo";
import { connect } from "./engine";
import { Stage } from "./features/Stage";
import { Widget } from "./features/Widget";
import { store } from "./store";

// The same page serves both windows: #/widget and #/main (optionally ?demo=...).
const [route, query = ""] = location.hash.replace(/^#\//, "").split("?");
const demo = new URLSearchParams(query).get("demo") as Demo | null;
const isWidget = route === "widget";

export function App() {
  const app = useSyncExternalStore(store.subscribe, store.get);

  useEffect(() => {
    document.body.classList.toggle("is-widget", isWidget);
    if (demo) startDemo(demo);
    else void connect();
  }, []);

  return isWidget ? <Widget app={app} /> : <Stage app={app} startWithHistory={demo === "history"} />;
}
