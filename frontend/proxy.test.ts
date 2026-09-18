import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { SESSION_COOKIE_NAME } from "@/lib/session_identity";

import { proxy } from "./proxy";

describe("proxy", () => {
  it("redirects to /sign-in when the session cookie is missing", () => {
    const request = new NextRequest("http://localhost:3000/onboarding");

    const response = proxy(request);

    expect(response.headers.get("location")).toBe("http://localhost:3000/sign-in");
  });

  it("lets a request through when the session cookie is present", () => {
    const request = new NextRequest("http://localhost:3000/onboarding", {
      headers: { cookie: `${SESSION_COOKIE_NAME}=abc123` },
    });

    const response = proxy(request);

    expect(response.headers.get("location")).toBeNull();
  });
});
