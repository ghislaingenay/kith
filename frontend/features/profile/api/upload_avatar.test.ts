// @vitest-environment node
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/test/mocks/server";

import { uploadAvatar } from "./upload_avatar";

const API_URL = "http://localhost:8000/api/v1";

describe("uploadAvatar", () => {
  it("sends the image as multipart form data in a `file` field", async () => {
    let received: { contentType: string | null; file: File | null } | undefined;
    server.use(
      http.put(`${API_URL}/users/me/avatar`, async ({ request }) => {
        const form = await request.formData();
        received = {
          contentType: request.headers.get("content-type"),
          file: form.get("file") as File | null,
        };
        return HttpResponse.json({
          email: "jane@example.com",
          name: null,
          avatar_url: "https://cdn.example.com/avatar.png?signature=abc",
        });
      }),
    );

    const profile = await uploadAvatar(
      new File([new Uint8Array([1, 2, 3])], "me.png", { type: "image/png" }),
    );

    expect(received?.contentType).toMatch(/^multipart\/form-data; boundary=/);
    expect(received?.file?.name).toBe("me.png");
    expect(received?.file?.type).toBe("image/png");
    expect(received?.file?.size).toBe(3);
    expect(profile.avatar_url).toBe("https://cdn.example.com/avatar.png?signature=abc");
  });
});
