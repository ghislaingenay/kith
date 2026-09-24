import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { server } from "./mocks/server";
import { installImageLoadingStub, setImageLoadOutcome } from "./stub_image_loading";

// jsdom doesn't implement matchMedia — needed by the shadcn sidebar's
// useIsMobile hook (components/ui/sidebar.tsx via hooks/use-mobile.ts).
// Guarded: some test files opt into `@vitest-environment node`, where
// `window` doesn't exist at all.
if (typeof window !== "undefined") {
  window.matchMedia ??= (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
}

if (typeof window !== "undefined") installImageLoadingStub();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  setImageLoadOutcome("load");
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());
