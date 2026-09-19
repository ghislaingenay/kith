# React & Next.js Coding Standards

Architecture, state management, and coding conventions for the Kith frontend: Next.js 16 (App Router), React 19, Tailwind 4, shadcn/ui, TanStack Query. See `mvp-design.md` §6 for the settled stack and `CONTEXT.md` for domain vocabulary.

---

## 1. Project Architecture & Feature Module Pattern

Feature-driven, modular architecture. Routing lives in `app/` (owned by Next.js); everything else a route needs comes from a feature module.

### 1.1 Directory Structure

```text
frontend/
├── app/            # App Router: page.tsx, layout.tsx, route.ts only — no business logic
├── components/     # Shared presentation components (buttons, inputs, shadcn/ui wrappers)
├── config/         # Global configuration and validated environment variables
├── context/         # Project docs consumed by agents (this file, coding-standards.md)
├── features/       # Feature-based domain modules
├── hooks/          # Shared application-level custom hooks
├── lib/            # Preconfigured third-party instances (query client, api client)
├── stores/         # Zustand stores for global UI state
├── test/           # Mock servers, test setup, utility overrides
├── types/          # Global TypeScript types and interfaces
├── utils/          # Generic, domain-agnostic helper functions
└── proxy.ts        # Centralized route protection (§4.2) — the only auth gate in the app (Next 16 renamed "middleware" to "proxy")
```

A route segment's `page.tsx` is a thin adapter: it imports from a feature's public surface and renders it. It does not contain fetching logic, form state, or business rules itself.

### 1.2 Feature Module Boundaries

Each domain lives under `features/<feature-name>` with internal sub-directories:

```text
features/sign-in/
├── api/          # Feature-specific TanStack Query hooks and request functions
├── components/   # Scoped presentation components
├── hooks/        # Scoped custom hooks
├── stores/       # Feature-scoped Zustand slices, if any
├── types/        # Feature-specific TypeScript interfaces/types
├── utils/        # Scoped utility logic
└── index.ts      # Public API surface (module barrier)
```

No `pages/` or `routes/` subfolder — the App Router already owns routing; a feature is imported *by* a route, it doesn't define one.

### 1.3 Import Rules & Module Encapsulation

The `index.ts` file is the explicit public boundary for a feature.

- **Allowed:** import from the feature root:
  ```typescript
  import { SignInForm } from "@/features/sign-in";
  ```
- **Forbidden:** deep imports that bypass the public interface:
  ```typescript
  // BAD: violates feature isolation
  import { SignInForm } from "@/features/sign-in/components/sign-in-form";
  ```

---

## 2. Path Aliases (`tsconfig.json`)

```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["./*"]
    }
  }
}
```

(No `src/` directory in this project — aliases resolve from the frontend root.)

---

## 3. Naming Conventions

| Entity                            | Convention | Example                               |
| :--------------------------------- | :--------- | :------------------------------------ |
| Components & Interfaces           | PascalCase | `SignInForm`, `SignInFormProps`       |
| Variables, Functions, Hooks       | camelCase  | `getCurrentUser`, `useSession`        |
| Files & Directories               | snake_case | `onboarding_form.tsx`, `create_tenant.ts` |
| Constants & Environment Variables | UPPERCASE  | `MAX_RETRY_COUNT`, `NEXT_PUBLIC_API_URL` |

Avoid classes; use functional and declarative patterns throughout.

As of #11, new files use snake_case (previous kebab-case files, e.g. `sign-in-form.tsx`, are not retroactively renamed). Framework-mandated filenames (`page.tsx`, `layout.tsx`, `route.ts`, `proxy.ts`, `vitest.config.ts`, `playwright.config.ts`) keep their required spelling regardless of convention.

---

## 4. TypeScript, Zod, and Component Rules

### 4.1 Data Validation and Type Inference

Build data schemas with Zod, then infer static types from the schema. Enforce immutability with `readonly`.

```typescript
import { z } from "zod";

export const userSchema = z.object({
  id: z.string().uuid(),
  email: z.string().email(),
});

export type User = Readonly<z.infer<typeof userSchema>>;
```

### 4.2 Server vs. Client Components

- Default to Server Components. Add "use client" only where interactivity, browser APIs, or a hook that needs it (`useState`, TanStack Query, Zustand) actually requires it.
- Server Components and Route Handlers that call the API must forward the incoming request's cookie header explicitly — server-side `fetch` has no cookie jar, and only FastAPI ever sets or clears the session cookie (ADR-0006). A `Set-Cookie` on a response to a server-side fetch is dropped; only a browser-direct request refreshes the session's sliding expiry.
- Never read or write the session cookie from client-side JavaScript. It's httpOnly by design (ADR-0006) — there is nothing to read, and attempting to is a sign the request should have gone through a Server Component or Route Handler instead.
- Route protection (checking the session cookie before a protected route renders) lives in `proxy.ts` at the project root (Next 16's rename of "Middleware" — same file convention, same purpose) — a single centralized gate, not scattered per-route checks. It only checks the cookie's *presence*; actual validation happens where a route calls `lib/session_identity.ts`'s `getSessionIdentity`, since only the backend can say whether a session is still good.
### 4.3 Component Design

- Functional components with destructured props and default parameters.
- Structure files as: exported component, subcomponents, helpers, static content, types — in that order.

---

## 5. State Management Matrix

| Category               | Tool                          | Usage Guidelines                                                                        |
| :---------------------- | :----------------------------- | :---------------------------------------------------------------------------------------- |
| **Local Component**    | `useState`, `useReducer`      | Isolated to a single component or tight hierarchy. Lift up only when strictly required.  |
| **Form State**         | React Hook Form + Zod         | Input state, validation, submission errors, at form scope.                               |
| **Global UI State**    | Zustand                       | Small, app-wide client state only (e.g. active tenant id in memory). Reach for this last — most state belongs closer to where it's used. |
| **Server Cache State** | TanStack Query                | Client-driven server interaction only: mutations, polling, retry buttons, anything triggered by user action after the initial render. |
| **Initial page data**  | Server Component `fetch`      | The default for data a page needs to render. Fetch directly in the Server Component (forwarding the request's cookie header, see §4.2) rather than reaching for a client-side query on mount — this is the App Router's model, not an alternative to it. |
| **URL State**          | `next/navigation`              | `useRouter`, `usePathname`, `useSearchParams` — pagination, shareable UI state.           |
| **Session state**      | None (server-owned)           | The session lives in an httpOnly cookie and Redis, never in browser storage or a store. A Server Component reads identity by calling `GET /me` server-side; a Client Component that needs it receives it as a prop, or refetches via TanStack Query only when it must react to a client-side change (e.g. after a mutation). |
| **Per-viewer convenience** | `localStorage`             | Non-critical UI preferences only (e.g. a collapsed sidebar). Never identity or anything the server must trust. |

Redux Toolkit/RTK Query are not used on this project — TanStack Query owns client-driven server interaction, Server Components own initial data, and the app's actual global-state surface is small enough that Zustand covers it without Redux's boilerplate.

---

## 6. Performance & Optimization

- **State initializers:** pass a function to `useState` for expensive initial computation so it runs once on mount, not every render.
- **Code-splitting:** use `next/dynamic` for heavy, non-critical client components; Server Components are already code-split by route.
- **Images:** use `next/image` — it handles responsive sizing, format negotiation, and lazy loading; don't hand-roll `srcset`.
- **Core Web Vitals:** tracked via Lighthouse CI in the deploy pipeline.

---

## 7. Testing

- Unit/component tests: Vitest + React Testing Library (`pnpm test`). Config in `vitest.config.ts`; shared setup/mocks live in `test/`.
- End-to-end: Playwright (`pnpm test:e2e`), run locally against the compose stack (not yet wired into CI — pending more shakeout). Currently covers sign in → onboarding → landing; the eventual full flow (sign in → upload → search → ask) grows this same suite as those features land.
- Mock the API at the network boundary (MSW) in unit tests; feature `api/` modules should be the only thing that needs mocking.

---

## 8. Documentation & Commit Guidelines

### 8.1 Code Documentation

Document exported components, hooks, and utils with a short JSDoc comment when the *why* isn't obvious from the signature. Skip it when the name and types already say everything.

### 8.2 Inline Comments

Comment only what the code cannot say for itself — a non-obvious decision, a workaround, a gotcha. One short, plain sentence.

```tsx
// Radix portals this content, so clicks still bubble to the card's <Link>.
<div role="presentation" onClick={(e) => e.stopPropagation()}>
```

### 8.3 Commit Rules

Conventional Commits. Short head line, blank line, then body if the change needs explaining.

```text
feat: add magic-link sign-in form

Validates the work-email field with Zod before submit and shows the
"check your email" state on success, regardless of whether the address
has an account (ADR-0006's enumeration guard).
```
